"""Config flow for Hisense Air Conditioner."""

from __future__ import annotations

from ipaddress import IPv4Address
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
from homeassistant.data_entry_flow import section
from homeassistant.helpers import device_registry as dr, entity_registry as er
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

  async def async_step_reconfigure(self, user_input=None):
    """Manage devices without replacing the configuration."""
    return self.async_show_menu(
        step_id="reconfigure", menu_options=["cloud", "manual", "manage_devices", "edit_device"])

  async def async_step_manage_devices(self, user_input=None):
    """Choose which configured devices to keep."""
    self._cloud_setup = dict(self._get_reconfigure_entry().data)
    return await self.async_step_select_devices(user_input)

  async def async_step_edit_device(self, user_input=None):
    """Select the device whose IP address changed."""
    devices = self._get_reconfigure_entry().data[CONF_DEVICES]
    if user_input is not None:
      self._edit_mac = user_input[CONF_MAC_ADDRESS]
      return await self.async_step_edit_ip()
    return self.async_show_form(step_id="edit_device", data_schema=vol.Schema({
        vol.Required(CONF_MAC_ADDRESS): SelectSelector(SelectSelectorConfig(
            options=[_device_option(d) for d in devices], mode=SelectSelectorMode.DROPDOWN)),
    }))

  async def async_step_edit_ip(self, user_input=None):
    """Change only the selected device; reload rebuilds its callback and notifier maps."""
    entry = self._get_reconfigure_entry()
    devices = entry.data[CONF_DEVICES]
    current = next(d for d in devices if d[CONF_MAC_ADDRESS] == self._edit_mac)
    errors = {}
    if user_input is not None:
      try:
        address = str(IPv4Address(user_input[CONF_HOST]))
      except ValueError:
        errors["base"] = "invalid_manual_config"
      else:
        updated = [{**d, "ip_address": address} if d[CONF_MAC_ADDRESS] == self._edit_mac
                   else d for d in devices]
        if self._conflicts(updated):
          errors["base"] = "duplicate_device"
        else:
          return self._save_devices(updated, entry.data)
    return self.async_show_form(step_id="edit_ip", errors=errors, data_schema=vol.Schema({
        vol.Required(CONF_HOST, default=current["ip_address"]): str,
    }))

  def _conflicts(self, devices):
    """Reject duplicate devices and ambiguous source IP routing."""
    own_id = self.context.get("entry_id") if self.source == "reconfigure" else None
    others = [device for entry in self.hass.config_entries.async_entries(DOMAIN)
              if entry.entry_id != own_id for device in entry.data[CONF_DEVICES]]
    for key in ("mac_address", "ip_address"):
      values = [device[key] for device in devices]
      if len(values) != len(set(values)) or set(values) & {d[key] for d in others}:
        return True
    return False

  def _save_devices(self, devices, data):
    """Save selection; the existing update listener performs one reload."""
    if self.source != "reconfigure":
      return self.async_create_entry(
          title=", ".join(d["name"] for d in devices), data={**data, CONF_DEVICES: devices})
    entry = self._get_reconfigure_entry()
    removed = {d["mac_address"] for d in entry.data[CONF_DEVICES]} - {
        d["mac_address"] for d in devices}
    result = self.async_update_and_abort(
        entry, unique_id=_unique_id(devices), data_updates={CONF_DEVICES: devices},
        title=", ".join(d["name"] for d in devices), reason="reconfigure_successful")
    device_registry = dr.async_get(self.hass)
    entity_registry = er.async_get(self.hass)
    for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
      if not any((DOMAIN, mac) in device.identifiers for mac in removed):
        continue
      for entity in er.async_entries_for_config_entry(entity_registry, entry.entry_id):
        if entity.device_id == device.id:
          entity_registry.async_remove(entity.entity_id)
      if hasattr(device, "config_entry_id"):
        device_registry.async_remove_device(device.id)
      else:
        device_registry.async_update_device(device.id, remove_config_entry_id=entry.entry_id)
    return result

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
        temp_type = advanced_settings.get(CONF_TEMP_TYPE, CONF_TEMP_TYPE_AUTO)
        devices = [
            _device_config_from_cloud(
                user_input[CONF_APP],
                device,
                _ha_temp_type(self.hass),
                temp_type,
            ) for device in discovered
        ]
      except Exception:
        _LOGGER.exception("Hisense cloud discovery failed")
        errors["base"] = "cannot_connect"
      else:
        if not discovered:
          errors["base"] = "device_not_found"
        else:
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
          if self.source == "reconfigure":
            existing = self._get_reconfigure_entry().data[CONF_DEVICES]
            by_mac = {d["mac_address"]: d for d in existing}
            by_mac.update({d["mac_address"]: d for d in devices})
            self._cloud_setup[CONF_DEVICES] = list(by_mac.values())
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
                        vol.Optional(CONF_LOCAL_IP, default=""): vol.Any(str, None),
                        vol.Optional(CONF_CALLBACK_PORT, default=DEFAULT_CALLBACK_PORT): vol.All(int, vol.Range(min=1, max=65535)),
                        vol.Optional(CONF_STATUS_INTERVAL, default=DEFAULT_STATUS_INTERVAL): vol.All(int, vol.Range(min=1)),
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
      elif self._conflicts(selected_devices):
        errors["base"] = "duplicate_device"
      else:
        if self.source != "reconfigure":
          await self.async_set_unique_id(_unique_id(selected_devices))
          self._abort_if_unique_id_configured()
        return self._save_devices(selected_devices, cloud_setup)

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
        devices = [device]
        if self.source == "reconfigure":
          devices = [*self._get_reconfigure_entry().data[CONF_DEVICES], device]
        if self._conflicts(devices):
          errors["base"] = "duplicate_device"
        else:
          if self.source != "reconfigure":
            await self.async_set_unique_id(_unique_id(devices))
            self._abort_if_unique_id_configured()
          return self._save_devices(devices, {
              CONF_APP: device["app"],
              CONF_LOCAL_IP: _blank_to_none(user_input.get(CONF_LOCAL_IP)),
              CONF_CALLBACK_PORT: user_input.get(CONF_CALLBACK_PORT, DEFAULT_CALLBACK_PORT),
              CONF_STATUS_INTERVAL: user_input.get(CONF_STATUS_INTERVAL, DEFAULT_STATUS_INTERVAL),
              CONF_TEMP_TYPE: user_input[CONF_TEMP_TYPE],
          })

    schema = {
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
            vol.Optional(CONF_LOCAL_IP, default=""): vol.Any(str, None),
            vol.Required(CONF_CALLBACK_PORT, default=DEFAULT_CALLBACK_PORT): vol.All(int, vol.Range(min=1, max=65535)),
            vol.Required(CONF_STATUS_INTERVAL, default=DEFAULT_STATUS_INTERVAL): vol.All(int, vol.Range(min=1)),
        }
    if self.source == "reconfigure":
      schema = {key: value for key, value in schema.items()
                if key.schema not in (CONF_LOCAL_IP, CONF_CALLBACK_PORT, CONF_STATUS_INTERVAL)}
    return self.async_show_form(step_id="manual", data_schema=vol.Schema(schema), errors=errors)


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
              CONF_CALLBACK_PORT: user_input.get(CONF_CALLBACK_PORT, DEFAULT_CALLBACK_PORT),
              CONF_STATUS_INTERVAL: user_input.get(CONF_STATUS_INTERVAL, DEFAULT_STATUS_INTERVAL),
              CONF_TEMP_TYPE: user_input[CONF_TEMP_TYPE],
          },
      )

    return self.async_show_form(
        step_id="init",
        data_schema=vol.Schema({
            vol.Optional(
                CONF_LOCAL_IP,
                default=self._entry.options.get(
                    CONF_LOCAL_IP, self._entry.data.get(CONF_LOCAL_IP)) or "",
            ):
                vol.Any(str, None),
            vol.Required(
                CONF_CALLBACK_PORT,
                default=self._entry.options.get(
                    CONF_CALLBACK_PORT,
                    self._entry.data.get(CONF_CALLBACK_PORT, DEFAULT_CALLBACK_PORT),
                ),
            ):
                vol.All(int, vol.Range(min=1, max=65535)),
            vol.Required(
                CONF_STATUS_INTERVAL,
                default=self._entry.options.get(
                    CONF_STATUS_INTERVAL,
                    self._entry.data.get(CONF_STATUS_INTERVAL, DEFAULT_STATUS_INTERVAL),
                ),
            ):
                vol.All(int, vol.Range(min=1)),
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
  normalized = mac_address.strip().replace(":", "").replace("-", "").lower()
  if len(normalized) != 12 or any(c not in "0123456789abcdef" for c in normalized):
    raise ValueError("Invalid MAC address")
  return normalized


def _device_option(device: dict[str, Any]) -> dict[str, str]:
  label = f"{device['name']} ({device['ip_address']})"
  return {"value": device["mac_address"], "label": label}


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
      "ip_address": str(IPv4Address(device["lan_ip"])),
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
      "ip_address": str(IPv4Address(user_input[CONF_HOST])),
      "lanip_key": user_input[CONF_LANIP_KEY],
      "lanip_key_id": user_input[CONF_LANIP_KEY_ID],
  }


def _unique_id(devices: list[dict[str, Any]]) -> str:
  return ",".join(sorted(device["mac_address"] for device in devices))
