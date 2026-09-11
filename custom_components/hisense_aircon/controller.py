"""Runtime controller for Hisense LAN devices."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Coroutine

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.components.network import async_get_source_ip
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .aircon import Device
from .const import (
    CONF_CALLBACK_PORT,
    CONF_DEVICES,
    CONF_LOCAL_IP,
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

_LOGGER = logging.getLogger(__name__)

type HisenseConfigEntry = ConfigEntry[HisenseController]

_WAIT_FOR_EMPTY_QUEUE = 10.0


class HisenseController:
  """Own the LAN server endpoints, notifier and device update loops."""

  def __init__(self, hass: HomeAssistant, entry: HisenseConfigEntry) -> None:
    self.hass = hass
    self.entry = entry
    self.devices = [
        Device.create(self._device_config(device_config), self._notify_device)
        for device_config in entry.data[CONF_DEVICES]
    ]
    self.devices_by_mac = {device.mac_address: device for device in self.devices}
    self.handlers = QueryHandlers(self.devices)
    self._tasks: list[asyncio.Task[Any]] = []
    self._notifier = Notifier(
        self._option(CONF_CALLBACK_PORT, DEFAULT_CALLBACK_PORT),
        self._option(CONF_LOCAL_IP),
        loop=hass.loop,
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

  def get_device(self, mac_address: str) -> Device | None:
    """Return a device by MAC address."""
    return self.devices_by_mac.get(mac_address)

  def _notify_device(self) -> None:
    self._notifier.notify()

  @callback
  def _handle_property_update(
      self,
      mac_address: str,
      prop_name: str,
      value: Any,
      retain: bool = False,
  ) -> None:
    async_dispatcher_send(
        self.hass,
        signal_device_update(self.entry.entry_id, mac_address),
        prop_name,
        value,
    )

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
