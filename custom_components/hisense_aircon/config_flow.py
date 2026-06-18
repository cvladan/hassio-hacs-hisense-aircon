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
from homeassistant.core import callback
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
_RECONFIGURE_ADD_MANUAL = "add_manual"
_RECONFIGURE_MANAGE = "manage"
_DEFAULT_ADVANCED_SETTINGS = {
    CONF_DEVICE_NAME: "",
    CONF_LOCAL_IP: "",
    CONF_CALLBACK_PORT: DEFAULT_CALLBACK_PORT,
    CONF_STATUS_INTERVAL: DEFAULT_STATUS_INTERVAL,
    CONF_TEMP_TYPE: CONF_TEMP_TYPE_AUTO,
}


class HisenseConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
  """Handle a config flow for Hisense Air Conditioner."""

  VERSION = 1

  @staticmethod
  @callback
  def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> HisenseOptionsFlow:
    """Return the options flow."""
    return HisenseOptionsFlow(config_entry)

  async def async_step_user(self, user_input: dict[str, Any] | None = None):
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

  async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> FlowResult:
    """Choose how to update devices on an existing config entry."""
    if user_input is not None:
      action = user_input[_RECONFIGURE_ACTION]
      if action == _RECONFIGURE_REDISCOVER:
        return await self.async_step_reconfigure_cloud()
      if action == _RECONFIGURE_ADD_MANUAL:
        return await self.async_step_reconfigure_manual()
      return await self._async_step_reconfigure_manage()

    return self.async_show_form(
        step_id="reconfigure",
        data_schema=vol.Schema({
            vol.Required(_RECONFIGURE_ACTION):
                SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            _RECONFIGURE_REDISCOVER,
                            _RECONFIGURE_ADD_MANUAL,
                            _RECONFIGURE_MANAGE,
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )),
        }),
    )

  async def _async_step_reconfigure_manage(self) -> FlowResult:
    """Prepare device selection for removing devices from the current list."""
    entry = self._get_reconfigure_entry()
    self._reconfigure_entry = entry
    self._reconfigure_candidates = list(entry.data[CONF_DEVICES])
    self._reconfigure_preselected = [
        device["mac_address"] for device in entry.data[CONF_DEVICES]
    ]
    self._reconfigure_data_updates = {}
    return await self.async_step_reconfigure_select_devices()

  async def async_step_reconfigure_cloud(
      self, user_input: dict[str, Any] | None = None) -> FlowResult:
    """Rediscover devices through the Hisense/Ayla account."""
    entry = self._get_reconfigure_entry()
    errors: dict[str, str] = {}
    default_app = entry.data.get(CONF_APP, "hisense-eu")
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
        _LOGGER.exception("Hisense cloud discovery failed during reconfigure")
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
          self._reconfigure_entry = entry
          self._reconfigure_candidates = _merge_device_lists(entry.data[CONF_DEVICES], devices)
          self._reconfigure_preselected = [
              device["mac_address"] for device in entry.data[CONF_DEVICES]
          ]
          self._reconfigure_data_updates = {
              CONF_APP: user_input[CONF_APP],
              CONF_LOCAL_IP: _blank_to_none(advanced_settings.get(CONF_LOCAL_IP)),
              CONF_CALLBACK_PORT: advanced_settings.get(CONF_CALLBACK_PORT,
                                                         DEFAULT_CALLBACK_PORT),
              CONF_STATUS_INTERVAL: advanced_settings.get(CONF_STATUS_INTERVAL,
                                                            DEFAULT_STATUS_INTERVAL),
              CONF_TEMP_TYPE: temp_type,
          }
          return await self.async_step_reconfigure_select_devices()

    return self.async_show_form(
        step_id="reconfigure_cloud",
        data_schema=vol.Schema({
            vol.Required(CONF_APP, default=default_app):
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

  async def async_step_reconfigure_manual(
      self, user_input: dict[str, Any] | None = None) -> FlowResult:
    """Append a manually configured device to the existing config entry."""
    entry = self._get_reconfigure_entry()
    errors: dict[str, str] = {}
    default_app = entry.data.get(CONF_APP, "hisense-eu")
    if user_input is not None:
      try:
        device = _device_config_from_manual(user_input)
      except (KeyError, ValueError):
        errors["base"] = "invalid_manual_config"
      else:
        existing_macs = {configured["mac_address"] for configured in entry.data[CONF_DEVICES]}
        if device["mac_address"] in existing_macs:
          errors["base"] = "duplicate_mac"
        else:
          selected_devices = list(entry.data[CONF_DEVICES]) + [device]
          return await self._async_apply_device_selection(entry, selected_devices)

    return self.async_show_form(
        step_id="reconfigure_manual",
        data_schema=vol.Schema({
            vol.Required(CONF_NAME): str,
            vol.Required(CONF_APP, default=default_app):
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
        }),
        errors=errors,
    )

  async def async_step_reconfigure_select_devices(
      self, user_input: dict[str, Any] | None = None) -> FlowResult:
    """Select which devices to keep on an existing config entry."""
    entry = getattr(self, "_reconfigure_entry", None)
    if entry is None:
      return await self.async_step_reconfigure()

    candidates = self._reconfigure_candidates
    preselected = self._reconfigure_preselected
    data_updates = getattr(self, "_reconfigure_data_updates", {})

    errors: dict[str, str] = {}
    if user_input is not None:
      selected = set(user_input.get(_SELECTED_DEVICES, []))
      selected_devices = [
          device for device in candidates if device["mac_address"] in selected
      ]
      if not selected_devices:
        errors["base"] = "no_device_selected"
      else:
        return await self._async_apply_device_selection(
            entry,
            selected_devices,
            data_updates,
        )

    return self.async_show_form(
        step_id="reconfigure_select_devices",
        data_schema=vol.Schema({
            vol.Required(_SELECTED_DEVICES, default=preselected):
                SelectSelector(
                    SelectSelectorConfig(
                        options=[_device_option(device) for device in candidates],
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )),
        }),
        errors=errors,
    )

  async def _async_apply_device_selection(
      self,
      entry: config_entries.ConfigEntry,
      selected_devices: list[dict[str, Any]],
      data_updates: dict[str, Any] | None = None,
  ) -> FlowResult:
    """Update the config entry device list and reload."""
    old_macs = {device["mac_address"] for device in entry.data[CONF_DEVICES]}
    new_macs = {device["mac_address"] for device in selected_devices}
    _remove_orphaned_devices(self.hass, old_macs - new_macs)

    updates: dict[str, Any] = {CONF_DEVICES: selected_devices}
    if data_updates:
      updates.update(data_updates)

    await self.async_set_unique_id(_unique_id(selected_devices))
    return self.async_update_reload_and_abort(
        entry,
        data_updates=updates,
        title=", ".join(device["name"] for device in selected_devices),
    )

  async def async_step_cloud(self, user_input: dict[str, Any] | None = None):
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
              CONF_APP: user_input[CONF_APP],
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

  async def async_step_select_devices(self, user_input: dict[str, Any] | None = None):
    """Select one or more discovered devices."""
    cloud_setup = getattr(self, "_cloud_setup", None)
    if cloud_setup is None:
      return await self.async_step_cloud()

    errors: dict[str, str] = {}
    devices = cloud_setup[CONF_DEVICES]
    if user_input is not None:
      selected = set(user_input.get(_SELECTED_DEVICES, []))
      selected_devices = [device for device in devices if device["mac_address"] in selected]
      if not selected_devices:
        errors["base"] = "no_device_selected"
      else:
        await self.async_set_unique_id(_unique_id(selected_devices))
        self._abort_if_unique_id_configured()
        title = ", ".join(device["name"] for device in selected_devices)
        return self.async_create_entry(
            title=title,
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

  async def async_step_manual(self, user_input: dict[str, Any] | None = None):
    """Set up a device from an existing LAN key."""
    errors: dict[str, str] = {}
    if user_input is not None:
      try:
        device = _device_config_from_manual(user_input)
      except (KeyError, ValueError):
        errors["base"] = "invalid_manual_config"
      else:
        await self.async_set_unique_id(_unique_id([device]))
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=device["name"],
            data={
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


class HisenseOptionsFlow(config_entries.OptionsFlow):
  """Handle Hisense options."""

  def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
    self._entry = config_entry

  async def async_step_init(self, user_input: dict[str, Any] | None = None):
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


def _merge_device_lists(
    existing: list[dict[str, Any]],
    discovered: list[dict[str, Any]],
) -> list[dict[str, Any]]:
  """Union device lists by MAC address; discovered cloud data wins for matches."""
  by_mac = {device["mac_address"]: dict(device) for device in existing}
  for device in discovered:
    by_mac[device["mac_address"]] = device
  return list(by_mac.values())


def _remove_orphaned_devices(hass, removed_macs: set[str]) -> None:
  """Remove device registry entries for devices no longer configured."""
  if not removed_macs:
    return
  registry = dr.async_get(hass)
  for mac in removed_macs:
    if device := registry.async_get_device(identifiers={(DOMAIN, mac)}):
      registry.async_remove_device(device.id)


def _ha_temp_type(hass) -> str:
  """Return the Home Assistant configured temperature unit as Hisense temp_type."""
  return "F" if hass.config.units.temperature_unit == UnitOfTemperature.FAHRENHEIT else "C"


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


def _unique_id(devices: list[dict[str, Any]]) -> str:
  return ",".join(sorted(device["mac_address"] for device in devices))
