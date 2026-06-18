"""Config flow for Hisense Air Conditioner."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_USERNAME,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult, section
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .app_mappings import SECRET_MAP
from .const import (
    CONF_APP,
    CONF_CALLBACK_PORT,
    CONF_DEVICE_NAME,
    CONF_DEVICES,
    CONF_HUB_TYPE,
    CONF_LANIP_KEY,
    CONF_LANIP_KEY_ID,
    CONF_LOCAL_IP,
    CONF_MAC_ADDRESS,
    CONF_MODEL,
    CONF_SETUP_METHOD,
    CONF_STATUS_INTERVAL,
    CONF_SW_VERSION,
    CONF_TEMP_TYPE,
    CONF_TEMP_TYPE_AUTO,
    DEFAULT_CALLBACK_PORT,
    DEFAULT_STATUS_INTERVAL,
    DOMAIN,
    HUB_TYPE_CLOUD,
    HUB_TYPE_MANUAL,
    SETUP_METHOD_CLOUD,
    SETUP_METHOD_MANUAL,
    TEMP_TYPE_OPTIONS,
)
from .discovery import perform_discovery

_LOGGER = logging.getLogger(__name__)

_ADVANCED_SETTINGS = "advanced_settings"
_SELECTED_DEVICES = "selected_devices"
_RECONFIGURE_ACTION = "reconfigure_action"
_RECONFIGURE_REDISCOVER = "rediscover"
_RECONFIGURE_REMOVE = "remove_devices"
_DEFAULT_ADVANCED_SETTINGS = {
    CONF_DEVICE_NAME: "",
    CONF_LOCAL_IP: "",
    CONF_CALLBACK_PORT: DEFAULT_CALLBACK_PORT,
    CONF_STATUS_INTERVAL: DEFAULT_STATUS_INTERVAL,
    CONF_TEMP_TYPE: CONF_TEMP_TYPE_AUTO,
}


class HisenseConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
  """Handle a config flow for Hisense Air Conditioner."""

  VERSION = 2

  def __init__(self) -> None:
    self._cloud_setup: dict[str, Any] | None = None
    self._device_candidates: list[dict[str, Any]] | None = None
    self._preselected_macs: list[str] | None = None

  @staticmethod
  @callback
  def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> HisenseOptionsFlow:
    """Return the options flow."""
    return HisenseOptionsFlow(config_entry)

  @staticmethod
  @callback
  def async_migrate_entry(hass: HomeAssistant, entry: config_entries.ConfigEntry) -> bool:
    """Migrate config entry to the latest version."""
    if entry.version > 2:
      return False

    if entry.version == 1:
      data = dict(entry.data)
      devices = data.get(CONF_DEVICES, [])
      if CONF_USERNAME in data:
        hub_type = HUB_TYPE_CLOUD
        unique_id = _cloud_unique_id(data[CONF_APP], data[CONF_USERNAME])
      elif len(devices) == 1:
        hub_type = HUB_TYPE_MANUAL
        unique_id = _manual_unique_id(devices[0]["mac_address"])
      else:
        hub_type = HUB_TYPE_CLOUD
        unique_id = entry.unique_id
      data[CONF_HUB_TYPE] = hub_type
      data[CONF_SETUP_METHOD] = hub_type
      hass.config_entries.async_update_entry(
          entry,
          data=data,
          unique_id=unique_id,
          version=2,
      )

    return True

  async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
    """Choose setup method."""
    if user_input is not None:
      if user_input[CONF_SETUP_METHOD] == SETUP_METHOD_MANUAL:
        return await self.async_step_manual()
      return await self.async_step_cloud()

    return self.async_show_form(
        step_id="user",
        data_schema=vol.Schema({
            vol.Required(CONF_SETUP_METHOD, default=SETUP_METHOD_CLOUD):
                SelectSelector(
                    SelectSelectorConfig(
                        options=[SETUP_METHOD_CLOUD, SETUP_METHOD_MANUAL],
                        mode=SelectSelectorMode.DROPDOWN,
                    ))
        }),
    )

  async def async_step_cloud(self, user_input: dict[str, Any] | None = None) -> FlowResult:
    """Discover devices through the Hisense/Ayla account."""
    errors: dict[str, str] = {}
    if user_input is not None:
      advanced_settings = user_input.get(_ADVANCED_SETTINGS, {})
      try:
        session = async_get_clientsession(self.hass)
        discovered = await perform_discovery(
            session,
            user_input[CONF_APP],
            user_input[CONF_USERNAME],
            user_input[CONF_PASSWORD],
            _blank_to_none(advanced_settings.get(CONF_DEVICE_NAME)),
            False,
        )
      except Exception:
        _LOGGER.exception("Hisense cloud discovery failed")
        errors["base"] = "cannot_connect"
      else:
        if not discovered:
          errors["base"] = "device_not_found"
        else:
          temp_type = advanced_settings.get(CONF_TEMP_TYPE, CONF_TEMP_TYPE_AUTO)
          devices = [
              _device_config_from_cloud(
                  user_input[CONF_APP],
                  device,
                  _ha_temp_type(self.hass),
                  temp_type,
              ) for device in discovered
          ]
          self._cloud_setup = {
              CONF_HUB_TYPE: HUB_TYPE_CLOUD,
              CONF_SETUP_METHOD: SETUP_METHOD_CLOUD,
              CONF_APP: user_input[CONF_APP],
              CONF_USERNAME: user_input[CONF_USERNAME],
              CONF_PASSWORD: user_input[CONF_PASSWORD],
              CONF_DEVICES: devices,
              CONF_LOCAL_IP: _blank_to_none(advanced_settings.get(CONF_LOCAL_IP)),
              CONF_CALLBACK_PORT: advanced_settings.get(CONF_CALLBACK_PORT,
                                                        DEFAULT_CALLBACK_PORT),
              CONF_STATUS_INTERVAL: advanced_settings.get(CONF_STATUS_INTERVAL,
                                                          DEFAULT_STATUS_INTERVAL),
              CONF_TEMP_TYPE: temp_type,
          }
          return await self.async_step_select_devices()

    return self.async_show_form(
        step_id="cloud",
        data_schema=vol.Schema({
            vol.Required(CONF_APP, default="hisense-eu"):
                SelectSelector(
                    SelectSelectorConfig(
                        options=sorted(SECRET_MAP),
                        mode=SelectSelectorMode.DROPDOWN,
                    )),
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD):
                TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
            vol.Required(_ADVANCED_SETTINGS, default=_DEFAULT_ADVANCED_SETTINGS):
                section(
                    vol.Schema({
                        vol.Optional(CONF_DEVICE_NAME, default=""): str,
                        vol.Optional(CONF_LOCAL_IP, default=""): str,
                        vol.Optional(CONF_CALLBACK_PORT, default=DEFAULT_CALLBACK_PORT): int,
                        vol.Optional(CONF_STATUS_INTERVAL, default=DEFAULT_STATUS_INTERVAL): int,
                        vol.Optional(CONF_TEMP_TYPE, default=CONF_TEMP_TYPE_AUTO):
                            SelectSelector(
                                SelectSelectorConfig(
                                    options=TEMP_TYPE_OPTIONS,
                                    mode=SelectSelectorMode.DROPDOWN,
                                )),
                    }),
                    {"collapsed": True},
                ),
        }),
        errors=errors,
    )

  async def async_step_select_devices(self, user_input: dict[str, Any] | None = None) -> FlowResult:
    """Select one or more discovered devices."""
    cloud_setup = self._cloud_setup
    if cloud_setup is None:
      return await self.async_step_cloud()

    errors: dict[str, str] = {}
    devices = cloud_setup[CONF_DEVICES]
    if user_input is not None:
      selected = set(user_input.get(_SELECTED_DEVICES, []))
      selected_devices = [device for device in devices if device["mac_address"] in selected]
      if not selected_devices:
        errors["base"] = "no_device_selected"
      elif conflicting := _conflicting_macs(self.hass, selected_devices):
        errors["base"] = "duplicate_mac"
        _LOGGER.warning("Device MAC(s) already configured: %s", conflicting)
      else:
        await self.async_set_unique_id(
            _cloud_unique_id(cloud_setup[CONF_APP], cloud_setup[CONF_USERNAME]))
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=_cloud_entry_title(cloud_setup),
            data={
                **cloud_setup,
                CONF_DEVICES: selected_devices,
            },
        )

    return self.async_show_form(
        step_id="select_devices",
        data_schema=vol.Schema({
            vol.Required(
                _SELECTED_DEVICES,
                default=[device["mac_address"] for device in devices],
            ):
                SelectSelector(
                    SelectSelectorConfig(
                        options=[_device_option(device) for device in devices],
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )),
        }),
        errors=errors,
    )

  async def async_step_manual(self, user_input: dict[str, Any] | None = None) -> FlowResult:
    """Set up a device from an existing LAN key."""
    errors: dict[str, str] = {}
    if user_input is not None:
      try:
        device = _device_config_from_manual(user_input)
      except (KeyError, ValueError):
        errors["base"] = "invalid_manual_config"
      else:
        if _mac_in_use(self.hass, device["mac_address"]):
          errors["base"] = "duplicate_mac"
        else:
          await self.async_set_unique_id(_manual_unique_id(device["mac_address"]))
          self._abort_if_unique_id_configured()
          return self.async_create_entry(
              title=device["name"],
              data={
                  CONF_HUB_TYPE: HUB_TYPE_MANUAL,
                  CONF_SETUP_METHOD: SETUP_METHOD_MANUAL,
                  CONF_APP: device["app"],
                  CONF_DEVICES: [device],
                  CONF_LOCAL_IP: _blank_to_none(user_input.get(CONF_LOCAL_IP)),
                  CONF_CALLBACK_PORT: user_input[CONF_CALLBACK_PORT],
                  CONF_STATUS_INTERVAL: user_input[CONF_STATUS_INTERVAL],
                  CONF_TEMP_TYPE: user_input[CONF_TEMP_TYPE],
              },
          )

    return self.async_show_form(
        step_id="manual",
        data_schema=vol.Schema({
            vol.Required(CONF_NAME): str,
            vol.Required(CONF_APP, default="hisense-eu"):
                SelectSelector(
                    SelectSelectorConfig(
                        options=sorted(SECRET_MAP),
                        mode=SelectSelectorMode.DROPDOWN,
                    )),
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_MAC_ADDRESS): str,
            vol.Required(CONF_LANIP_KEY): str,
            vol.Required(CONF_LANIP_KEY_ID): int,
            vol.Required(CONF_MODEL, default="AEH-W4E1"): str,
            vol.Optional(CONF_SW_VERSION, default=""): str,
            vol.Required(CONF_TEMP_TYPE, default=_ha_temp_type(self.hass)): vol.In(["C", "F"]),
            vol.Optional(CONF_LOCAL_IP, default=""): str,
            vol.Required(CONF_CALLBACK_PORT, default=DEFAULT_CALLBACK_PORT): int,
            vol.Required(CONF_STATUS_INTERVAL, default=DEFAULT_STATUS_INTERVAL): int,
        }),
        errors=errors,
    )

  async def async_step_reconfigure(
      self, user_input: dict[str, Any] | None = None, errors: dict[str, str] | None = None
  ) -> FlowResult:
    """Reconfigure an existing hub."""
    entry = self._get_reconfigure_entry()
    if entry.data.get(CONF_HUB_TYPE) == HUB_TYPE_MANUAL:
      return await self.async_step_reconfigure_manual()

    if user_input is not None:
      action = user_input[_RECONFIGURE_ACTION]
      if action == _RECONFIGURE_REDISCOVER:
        return await self.async_step_reconfigure_rediscover()
      return await self.async_step_reconfigure_remove_devices()

    return self.async_show_form(
        step_id="reconfigure",
        data_schema=vol.Schema({
            vol.Required(_RECONFIGURE_ACTION):
                SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {
                                "value": _RECONFIGURE_REDISCOVER,
                                "label": "Rediscover devices from cloud account",
                            },
                            {
                                "value": _RECONFIGURE_REMOVE,
                                "label": "Remove configured devices",
                            },
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )),
        }),
        errors=errors or {},
    )

  async def async_step_reconfigure_rediscover(
      self, user_input: dict[str, Any] | None = None) -> FlowResult:
    """Rediscover devices for a cloud hub."""
    entry = self._get_reconfigure_entry()
    errors: dict[str, str] = {}

    if CONF_USERNAME not in entry.data or CONF_PASSWORD not in entry.data:
      return await self.async_step_reauth()

    if user_input is None:
      try:
        session = async_get_clientsession(self.hass)
        discovered = await perform_discovery(
            session,
            entry.data[CONF_APP],
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
            None,
            False,
        )
      except Exception:
        _LOGGER.exception("Hisense cloud rediscovery failed")
        errors["base"] = "cannot_connect"
      else:
        if not discovered:
          errors["base"] = "device_not_found"
        else:
          temp_type = entry.data.get(CONF_TEMP_TYPE, CONF_TEMP_TYPE_AUTO)
          cloud_devices = [
              _device_config_from_cloud(
                  entry.data[CONF_APP],
                  device,
                  _ha_temp_type(self.hass),
                  temp_type,
              ) for device in discovered
          ]
          self._device_candidates = _merge_device_lists(
              entry.data.get(CONF_DEVICES, []),
              cloud_devices,
          )
          self._preselected_macs = [
              device["mac_address"] for device in entry.data.get(CONF_DEVICES, [])
          ]
          return await self.async_step_reconfigure_select_devices()

      return await self.async_step_reconfigure(errors=errors)

    return await self.async_step_reconfigure_select_devices(user_input)

  async def async_step_reconfigure_select_devices(
      self, user_input: dict[str, Any] | None = None) -> FlowResult:
    """Select devices after cloud rediscovery."""
    entry = self._get_reconfigure_entry()
    candidates = self._device_candidates
    if candidates is None:
      return await self.async_step_reconfigure_rediscover()

    errors: dict[str, str] = {}
    preselected = self._preselected_macs or [
        device["mac_address"] for device in entry.data.get(CONF_DEVICES, [])
    ]

    if user_input is not None:
      selected = set(user_input.get(_SELECTED_DEVICES, []))
      selected_devices = [device for device in candidates if device["mac_address"] in selected]
      if not selected_devices:
        errors["base"] = "no_device_selected"
      elif conflicting := _conflicting_macs(
          self.hass,
          selected_devices,
          exclude_entry_id=entry.entry_id,
      ):
        errors["base"] = "duplicate_mac"
        _LOGGER.warning("Device MAC(s) already configured: %s", conflicting)
      else:
        old_macs = {device["mac_address"] for device in entry.data.get(CONF_DEVICES, [])}
        new_macs = {device["mac_address"] for device in selected_devices}
        _remove_orphaned_devices(self.hass, old_macs, new_macs)
        return self.async_update_reload_and_abort(
            entry,
            data_updates={CONF_DEVICES: selected_devices},
            title=_cloud_entry_title(entry.data),
        )

    return self.async_show_form(
        step_id="reconfigure_select_devices",
        data_schema=vol.Schema({
            vol.Required(
                _SELECTED_DEVICES,
                default=preselected,
            ):
                SelectSelector(
                    SelectSelectorConfig(
                        options=[_device_option(device) for device in candidates],
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )),
        }),
        errors=errors,
    )

  async def async_step_reconfigure_remove_devices(
      self, user_input: dict[str, Any] | None = None) -> FlowResult:
    """Remove devices from a cloud hub."""
    entry = self._get_reconfigure_entry()
    devices = entry.data.get(CONF_DEVICES, [])
    errors: dict[str, str] = {}

    if user_input is not None:
      selected = set(user_input.get(_SELECTED_DEVICES, []))
      selected_devices = [device for device in devices if device["mac_address"] in selected]
      if not selected_devices:
        errors["base"] = "no_device_selected"
      else:
        old_macs = {device["mac_address"] for device in devices}
        new_macs = {device["mac_address"] for device in selected_devices}
        _remove_orphaned_devices(self.hass, old_macs, new_macs)
        return self.async_update_reload_and_abort(
            entry,
            data_updates={CONF_DEVICES: selected_devices},
            title=_cloud_entry_title(entry.data),
        )

    return self.async_show_form(
        step_id="reconfigure_remove_devices",
        data_schema=vol.Schema({
            vol.Required(
                _SELECTED_DEVICES,
                default=[device["mac_address"] for device in devices],
            ):
                SelectSelector(
                    SelectSelectorConfig(
                        options=[_device_option(device) for device in devices],
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )),
        }),
        errors=errors,
    )

  async def async_step_reconfigure_manual(
      self, user_input: dict[str, Any] | None = None) -> FlowResult:
    """Edit the single device on a manual hub."""
    entry = self._get_reconfigure_entry()
    devices = entry.data.get(CONF_DEVICES, [])
    if len(devices) != 1:
      return self.async_abort(reason="manual_single_device")

    current = devices[0]
    errors: dict[str, str] = {}

    if user_input is not None:
      try:
        device = _device_config_from_manual(user_input)
      except (KeyError, ValueError):
        errors["base"] = "invalid_manual_config"
      else:
        if (
            device["mac_address"] != current["mac_address"]
            and _mac_in_use(self.hass, device["mac_address"], exclude_entry_id=entry.entry_id)
        ):
          errors["base"] = "duplicate_mac"
        else:
          old_macs = {current["mac_address"]}
          new_macs = {device["mac_address"]}
          _remove_orphaned_devices(self.hass, old_macs, new_macs)
          updates: dict[str, Any] = {
              CONF_DEVICES: [device],
              CONF_APP: device["app"],
              CONF_LOCAL_IP: _blank_to_none(user_input.get(CONF_LOCAL_IP)),
              CONF_CALLBACK_PORT: user_input[CONF_CALLBACK_PORT],
              CONF_STATUS_INTERVAL: user_input[CONF_STATUS_INTERVAL],
              CONF_TEMP_TYPE: user_input[CONF_TEMP_TYPE],
          }
          reload_kwargs: dict[str, Any] = {
              "data_updates": updates,
              "title": device["name"],
          }
          if device["mac_address"] != current["mac_address"]:
            await self.async_set_unique_id(_manual_unique_id(device["mac_address"]))
            self._abort_if_unique_id_configured()
          return self.async_update_reload_and_abort(entry, **reload_kwargs)

    return self.async_show_form(
        step_id="reconfigure_manual",
        data_schema=vol.Schema({
            vol.Required(CONF_NAME, default=current["name"]): str,
            vol.Required(CONF_APP, default=current["app"]):
                SelectSelector(
                    SelectSelectorConfig(
                        options=sorted(SECRET_MAP),
                        mode=SelectSelectorMode.DROPDOWN,
                    )),
            vol.Required(CONF_HOST, default=current["ip_address"]): str,
            vol.Required(CONF_MAC_ADDRESS, default=current["mac_address"]): str,
            vol.Required(CONF_LANIP_KEY, default=current["lanip_key"]): str,
            vol.Required(CONF_LANIP_KEY_ID, default=current["lanip_key_id"]): int,
            vol.Required(CONF_MODEL, default=current.get("model", "AEH-W4E1")): str,
            vol.Optional(CONF_SW_VERSION, default=current.get("sw_version") or ""): str,
            vol.Required(CONF_TEMP_TYPE, default=current["temp_type"]): vol.In(["C", "F"]),
            vol.Optional(
                CONF_LOCAL_IP,
                default=entry.options.get(
                    CONF_LOCAL_IP,
                    entry.data.get(CONF_LOCAL_IP) or "",
                ),
            ):
                str,
            vol.Required(
                CONF_CALLBACK_PORT,
                default=entry.options.get(
                    CONF_CALLBACK_PORT,
                    entry.data.get(CONF_CALLBACK_PORT, DEFAULT_CALLBACK_PORT),
                ),
            ):
                int,
            vol.Required(
                CONF_STATUS_INTERVAL,
                default=entry.options.get(
                    CONF_STATUS_INTERVAL,
                    entry.data.get(CONF_STATUS_INTERVAL, DEFAULT_STATUS_INTERVAL),
                ),
            ):
                int,
        }),
        errors=errors,
    )

  async def async_step_reauth(self, user_input: dict[str, Any] | None = None) -> FlowResult:
    """Update cloud account credentials."""
    entry = self._get_reauth_entry()
    errors: dict[str, str] = {}

    if user_input is not None:
      username = user_input[CONF_USERNAME].strip()
      if username.lower() != entry.data.get(CONF_USERNAME, "").lower():
        errors["base"] = "account_mismatch"
      else:
        try:
          session = async_get_clientsession(self.hass)
          await perform_discovery(
              session,
              user_input[CONF_APP],
              username,
              user_input[CONF_PASSWORD],
              None,
              False,
          )
        except Exception:
          _LOGGER.exception("Hisense cloud reauthentication failed")
          errors["base"] = "cannot_connect"
        else:
          await self.async_set_unique_id(_cloud_unique_id(user_input[CONF_APP], username))
          self._abort_if_unique_id_mismatch()
          return self.async_update_reload_and_abort(
              entry,
              data_updates={
                  CONF_APP: user_input[CONF_APP],
                  CONF_USERNAME: username,
                  CONF_PASSWORD: user_input[CONF_PASSWORD],
              },
              title=_cloud_entry_title({
                  CONF_APP: user_input[CONF_APP],
                  CONF_USERNAME: username,
              }),
          )

    defaults = entry.data
    return self.async_show_form(
        step_id="reauth",
        data_schema=vol.Schema({
            vol.Required(CONF_APP, default=defaults.get(CONF_APP, "hisense-eu")):
                SelectSelector(
                    SelectSelectorConfig(
                        options=sorted(SECRET_MAP),
                        mode=SelectSelectorMode.DROPDOWN,
                    )),
            vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
            vol.Required(CONF_PASSWORD):
                TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
        }),
        errors=errors,
    )


class HisenseOptionsFlow(config_entries.OptionsFlow):
  """Handle Hisense options."""

  def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
    self._entry = config_entry

  async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
    """Manage runtime options."""
    if user_input is not None:
      return self.async_create_entry(
          title="",
          data={
              CONF_LOCAL_IP: _blank_to_none(user_input.get(CONF_LOCAL_IP)),
              CONF_CALLBACK_PORT: user_input[CONF_CALLBACK_PORT],
              CONF_STATUS_INTERVAL: user_input[CONF_STATUS_INTERVAL],
              CONF_TEMP_TYPE: user_input[CONF_TEMP_TYPE],
          },
      )

    return self.async_show_form(
        step_id="init",
        data_schema=vol.Schema({
            vol.Optional(
                CONF_LOCAL_IP,
                default=self._entry.options.get(
                    CONF_LOCAL_IP,
                    self._entry.data.get(CONF_LOCAL_IP) or "",
                ),
            ):
                str,
            vol.Required(
                CONF_CALLBACK_PORT,
                default=self._entry.options.get(
                    CONF_CALLBACK_PORT,
                    self._entry.data.get(CONF_CALLBACK_PORT, DEFAULT_CALLBACK_PORT),
                ),
            ):
                int,
            vol.Required(
                CONF_STATUS_INTERVAL,
                default=self._entry.options.get(
                    CONF_STATUS_INTERVAL,
                    self._entry.data.get(CONF_STATUS_INTERVAL, DEFAULT_STATUS_INTERVAL),
                ),
            ):
                int,
            vol.Required(
                CONF_TEMP_TYPE,
                default=self._entry.options.get(
                    CONF_TEMP_TYPE,
                    self._entry.data.get(CONF_TEMP_TYPE, CONF_TEMP_TYPE_AUTO),
                ),
            ):
                SelectSelector(
                    SelectSelectorConfig(
                        options=TEMP_TYPE_OPTIONS,
                        mode=SelectSelectorMode.DROPDOWN,
                    )),
        }),
    )


def _blank_to_none(value: str | None) -> str | None:
  if value is None:
    return None
  value = value.strip()
  return value or None


def _normalize_mac(mac_address: str) -> str:
  return mac_address.replace(":", "").replace("-", "").lower()


def _device_option(device: dict[str, Any]) -> dict[str, str]:
  label = f"{device['name']} ({device['ip_address']})"
  return {"value": device["mac_address"], "label": label}


def _ha_temp_type(hass: HomeAssistant) -> str:
  """Return the Home Assistant configured temperature unit as Hisense temp_type."""
  return "F" if hass.config.units.temperature_unit == UnitOfTemperature.FAHRENHEIT else "C"


def _cloud_unique_id(app: str, username: str) -> str:
  return f"{app}:{username.strip().lower()}"


def _manual_unique_id(mac_address: str) -> str:
  return f"manual:{_normalize_mac(mac_address)}"


def _cloud_entry_title(data: dict[str, Any]) -> str:
  return f"{data[CONF_APP]} — {data[CONF_USERNAME]}"


def _configured_macs(
    hass: HomeAssistant,
    *,
    exclude_entry_id: str | None = None,
) -> set[str]:
  macs: set[str] = set()
  for entry in hass.config_entries.async_entries(DOMAIN):
    if entry.entry_id == exclude_entry_id:
      continue
    for device in entry.data.get(CONF_DEVICES, []):
      macs.add(_normalize_mac(device["mac_address"]))
  return macs


def _mac_in_use(
    hass: HomeAssistant,
    mac_address: str,
    *,
    exclude_entry_id: str | None = None,
) -> bool:
  return _normalize_mac(mac_address) in _configured_macs(
      hass, exclude_entry_id=exclude_entry_id)


def _conflicting_macs(
    hass: HomeAssistant,
    devices: list[dict[str, Any]],
    *,
    exclude_entry_id: str | None = None,
) -> list[str]:
  configured = _configured_macs(hass, exclude_entry_id=exclude_entry_id)
  return [
      device["mac_address"] for device in devices
      if _normalize_mac(device["mac_address"]) in configured
  ]


def _merge_device_lists(
    existing: list[dict[str, Any]],
    discovered: list[dict[str, Any]],
) -> list[dict[str, Any]]:
  """Union device lists by MAC address; discovered cloud data wins."""
  by_mac = {device["mac_address"]: device for device in existing}
  for device in discovered:
    by_mac[device["mac_address"]] = device
  return list(by_mac.values())


def _remove_orphaned_devices(
    hass: HomeAssistant,
    old_macs: set[str],
    new_macs: set[str],
) -> None:
  """Remove device registry entries for MACs no longer configured."""
  removed_macs = old_macs - new_macs
  if not removed_macs:
    return
  device_registry = dr.async_get(hass)
  for mac in removed_macs:
    if device := device_registry.async_get_device(identifiers={(DOMAIN, mac)}):
      device_registry.async_remove_device(device.id)


def _device_config_from_cloud(
    app: str,
    device: dict[str, Any],
    fallback_temp_type: str,
    temp_type_override: str,
) -> dict[str, Any]:
  temp_type = (
      temp_type_override
      if temp_type_override in ("C", "F") else device.get("temp_type") or fallback_temp_type)
  return {
      "name": device["product_name"],
      "app": app,
      "model": device.get("oem_model") or device.get("model") or "unknown",
      "sw_version": device.get("sw_version") or "",
      "dsn": device.get("dsn"),
      "temp_type": temp_type,
      "mac_address": _normalize_mac(device["mac"]),
      "ip_address": device["lan_ip"],
      "lanip_key": device["lanip_key"],
      "lanip_key_id": device["lanip_key_id"],
  }


def _device_config_from_manual(user_input: dict[str, Any]) -> dict[str, Any]:
  return {
      "name": user_input[CONF_NAME],
      "app": user_input[CONF_APP],
      "model": user_input[CONF_MODEL],
      "sw_version": user_input.get(CONF_SW_VERSION) or "",
      "dsn": None,
      "temp_type": user_input[CONF_TEMP_TYPE],
      "mac_address": _normalize_mac(user_input[CONF_MAC_ADDRESS]),
      "ip_address": user_input[CONF_HOST],
      "lanip_key": user_input[CONF_LANIP_KEY],
      "lanip_key_id": user_input[CONF_LANIP_KEY_ID],
  }
