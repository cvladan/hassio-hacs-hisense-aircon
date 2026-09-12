"""Runtime controller for Hisense LAN devices."""

from __future__ import annotations

import asyncio
from functools import partial
from typing import Any, Coroutine

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.components.network import async_get_source_ip
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady, HomeAssistantError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers import issue_registry as ir

from .aircon import Device
from .const import (
    CONF_CALLBACK_PORT,
    CONF_DEVICES,
    CONF_LOCAL_IP,
    CONF_SEPARATE_HTTP_PORT,
    CONF_STATUS_INTERVAL,
    CONF_TEMP_TYPE,
    CONF_TEMP_TYPE_AUTO,
    DEFAULT_CALLBACK_PORT,
    DEFAULT_STATUS_INTERVAL,
    DOMAIN,
    VIEWS_REGISTERED,
    signal_device_update,
)
from .notifier import Notifier
from .query_handlers import QueryHandlers

type HisenseConfigEntry = ConfigEntry[HisenseController]

_WAIT_FOR_EMPTY_QUEUE = 10.0


def callback_error(hass: HomeAssistant, settings: dict) -> str | None:
  """Detect local port conflicts and direct callbacks to an HTTPS server."""
  http = getattr(hass, "http", None)
  ha_port = getattr(http, "server_port", DEFAULT_CALLBACK_PORT)
  port = settings.get(CONF_SEPARATE_HTTP_PORT, 0)
  if port:
    if port == ha_port:
      return "listener_port_conflict"
  elif (getattr(http, "ssl_certificate", None)
        and settings.get(CONF_CALLBACK_PORT, DEFAULT_CALLBACK_PORT) == ha_port
        and not (settings.get(CONF_LOCAL_IP) or "").strip()):
    # An explicit address or different port may point to a plain HTTP proxy.
    return "https_callback"
  return None


class HisenseController:
  """Own the LAN server endpoints, notifier and device update loops."""

  def __init__(self, hass: HomeAssistant, entry: HisenseConfigEntry) -> None:
    self.hass = hass
    self.entry = entry
    self.devices = [
        Device.create(self._device_config(device_config),
                      partial(self._notify_device, device_config["mac_address"]))
        for device_config in entry.data[CONF_DEVICES]
    ]
    self.handlers = QueryHandlers(self.devices)
    self._tasks: list[asyncio.Task[Any]] = []
    self._http_runner: web.AppRunner | None = None
    self._notifier = Notifier(
        self._option(CONF_SEPARATE_HTTP_PORT, 0) or self._option(CONF_CALLBACK_PORT, DEFAULT_CALLBACK_PORT),
        self._option(CONF_LOCAL_IP),
    )

  def _option(self, key: str, default: Any | None = None) -> Any:
    return self.entry.options.get(key, self.entry.data.get(key, default))

  def _device_config(self, device_config: dict[str, Any]) -> dict[str, Any]:
    config = dict(device_config)
    temp_type = self._option(CONF_TEMP_TYPE, CONF_TEMP_TYPE_AUTO)
    if temp_type in ("C", "F"):
      config[CONF_TEMP_TYPE] = temp_type
    return config

  async def async_start(self) -> None:
    """Start the LAN bridge."""
    if error := callback_error(self.hass, {**self.entry.data, **self.entry.options}):
      raise ConfigEntryError(translation_domain=DOMAIN, translation_key=error)
    if self._option(CONF_SEPARATE_HTTP_PORT, 0):
      await self._async_start_http_listener()
    else:
      self._register_views()

    for device in self.devices:
      try:
        local_ip = self._option(CONF_LOCAL_IP) or await async_get_source_ip(
            self.hass, target_ip=device.ip_address)
      except (HomeAssistantError, OSError) as ex:
        raise ConfigEntryNotReady("Could not determine the callback IP address.") from ex
      self._notifier.register_device(device, local_ip)
      device.add_property_change_listener(self._handle_property_update)

    session = async_get_clientsession(self.hass)
    self._tasks.append(
        self._create_background_task(
            self._notifier.start(session),
            "hisense_aircon notifier",
        )
    )
    for device in self.devices:
      self._tasks.append(
          self._create_background_task(
              self._query_status_device(device),
              f"hisense_aircon status poll {device.mac_address}",
          )
      )

  def _create_background_task(
      self, coro: Coroutine[Any, Any, Any], name: str
  ) -> asyncio.Task[Any]:
    """Create long-running work without holding up Home Assistant startup."""
    return self.entry.async_create_background_task(self.hass, coro, name)

  async def async_stop(self) -> None:
    """Stop background work."""
    await self._notifier.stop()
    for device in self.devices:
      device.remove_property_change_listener(self._handle_property_update)
    for task in self._tasks:
      task.cancel()
    if self._tasks:
      await asyncio.gather(*self._tasks, return_exceptions=True)
    self._tasks.clear()
    if self._http_runner is not None:
      await self._http_runner.cleanup()
      self._http_runner = None

  async def _async_start_http_listener(self) -> None:
    """Serve only this entry's device protocol over plain IPv4 HTTP."""
    app = web.Application(client_max_size=QueryHandlers._MAX_REQUEST_BODY)
    app.router.add_post("/local_lan/key_exchange.json", self.handlers.key_exchange_handler)
    app.router.add_get("/local_lan/commands.json", self.handlers.command_handler)
    for path in ("property/datapoint.json", "property/datapoint/ack.json",
                 "node/property/datapoint.json", "node/property/datapoint/ack.json"):
      app.router.add_post(f"/local_lan/{path}", self.handlers.property_update_handler)
    self._http_runner = web.AppRunner(app, access_log=None)
    port = self._option(CONF_SEPARATE_HTTP_PORT)
    try:
      await self._http_runner.setup()
      await web.TCPSite(self._http_runner, "0.0.0.0", port).start()
    except OSError as ex:
      await self._http_runner.cleanup()
      self._http_runner = None
      raise ConfigEntryNotReady(
          translation_domain=DOMAIN, translation_key="listener_bind_failed",
          translation_placeholders={"port": str(port)},
      ) from ex

  def _notify_device(self, mac_address: str) -> None:
    self._notifier.notify(mac_address)

  def reconnect_device(self, device: Device) -> None:
    """Request a fresh registration without resetting other devices or queued writes."""
    self._notifier.notify(device.mac_address, reconnect=True)

  @callback
  def _handle_property_update(self, mac_address: str, changed: set[str]) -> None:
    if 'lan_key_invalid' in changed:
      device = next(d for d in self.devices if d.mac_address == mac_address)
      issue_id = f"{self.entry.entry_id}_{mac_address}_lan_key"
      if device.lan_key_invalid:
        ir.async_create_issue(
            self.hass, DOMAIN, issue_id, is_fixable=False, is_persistent=True,
            severity=ir.IssueSeverity.ERROR, translation_key="lan_key_changed",
            translation_placeholders={"device": device.name},
            learn_more_url="https://github.com/cvladan/hassio-hacs-hisense-aircon#managing-devices-after-setup",
        )
      else:
        ir.async_delete_issue(self.hass, DOMAIN, issue_id)
    async_dispatcher_send(
        self.hass, signal_device_update(self.entry.entry_id, mac_address), changed)

  async def _query_status_device(self, device: Device) -> None:
    status_interval = self._option(CONF_STATUS_INTERVAL, DEFAULT_STATUS_INTERVAL)
    while True:
      while device.commands_queue.qsize() > 10:
        await asyncio.sleep(_WAIT_FOR_EMPTY_QUEUE)
      device.queue_status()
      await asyncio.sleep(status_interval)

  def _register_views(self) -> None:
    domain_data = self.hass.data.setdefault(DOMAIN, {})
    if domain_data.get(VIEWS_REGISTERED):
      return
    self.hass.http.register_view(HisenseKeyExchangeView())
    self.hass.http.register_view(HisenseKeyExchangeRootView())
    self.hass.http.register_view(HisenseCommandsView())
    self.hass.http.register_view(HisenseCommandsRootView())
    self.hass.http.register_view(HisensePropertyDatapointView())
    self.hass.http.register_view(HisensePropertyDatapointAckView())
    self.hass.http.register_view(HisenseNodePropertyDatapointView())
    self.hass.http.register_view(HisenseNodePropertyDatapointAckView())
    domain_data[VIEWS_REGISTERED] = True


def _controller_from_request(request: web.Request) -> HisenseController:
  hass = request.app["hass"]
  for entry in hass.config_entries.async_entries(DOMAIN):
    controller = getattr(entry, "runtime_data", None)
    if isinstance(controller, HisenseController) and request.remote in controller.handlers.device_ips:
      return controller
  raise web.HTTPNotFound(reason="No configured Hisense device matches the request source.")


def _endpoint_info(url: str, protocol_methods: list[str]) -> web.Response:
  return web.json_response({
      "ok": True,
      "endpoint": url,
      "protocol_methods": protocol_methods,
      "message": (
          "Hisense Air Conditioner endpoint is registered. This browser response is only "
          "a connectivity hint; the air conditioner uses the listed protocol method(s) "
          "with Ayla LAN JSON payloads."
      ),
      "read_more": (
          "The real device protocol path is intentionally kept under /local_lan because "
          "Hisense/Ayla devices are registered with that callback URI."
      ),
  })


class HisenseKeyExchangeView(HomeAssistantView):
  """Ayla LAN key exchange endpoint."""

  url = "/local_lan/key_exchange.json"
  name = "api:hisense_aircon:key_exchange"
  requires_auth = False

  async def get(self, request: web.Request) -> web.Response:
    return _endpoint_info(self.url, ["POST"])

  async def post(self, request: web.Request) -> web.Response:
    return await _controller_from_request(request).handlers.key_exchange_handler(request)


class HisenseKeyExchangeRootView(HisenseKeyExchangeView):
  """Compatibility alias for manual endpoint checks."""

  url = "/key_exchange.json"
  name = "api:hisense_aircon:key_exchange_root"


class HisenseCommandsView(HomeAssistantView):
  """Ayla LAN command endpoint."""

  url = "/local_lan/commands.json"
  name = "api:hisense_aircon:commands"
  requires_auth = False

  async def get(self, request: web.Request) -> web.Response:
    try:
      controller = _controller_from_request(request)
    except web.HTTPNotFound:
      return _endpoint_info(self.url, ["GET"])
    return await controller.handlers.command_handler(request)


class HisenseCommandsRootView(HisenseCommandsView):
  """Compatibility alias for manual endpoint checks."""

  url = "/commands.json"
  name = "api:hisense_aircon:commands_root"


class HisensePropertyDatapointView(HomeAssistantView):
  """Ayla LAN property update endpoint."""

  url = "/local_lan/property/datapoint.json"
  name = "api:hisense_aircon:property_datapoint"
  requires_auth = False

  async def get(self, request: web.Request) -> web.Response:
    return _endpoint_info(self.url, ["POST"])

  async def post(self, request: web.Request) -> web.Response:
    return await _controller_from_request(request).handlers.property_update_handler(request)


class HisensePropertyDatapointAckView(HisensePropertyDatapointView):
  """Ayla LAN property update ack endpoint."""

  url = "/local_lan/property/datapoint/ack.json"
  name = "api:hisense_aircon:property_datapoint_ack"


class HisenseNodePropertyDatapointView(HisensePropertyDatapointView):
  """Ayla LAN node property update endpoint."""

  url = "/local_lan/node/property/datapoint.json"
  name = "api:hisense_aircon:node_property_datapoint"


class HisenseNodePropertyDatapointAckView(HisensePropertyDatapointView):
  """Ayla LAN node property update ack endpoint."""

  url = "/local_lan/node/property/datapoint/ack.json"
  name = "api:hisense_aircon:node_property_datapoint_ack"
