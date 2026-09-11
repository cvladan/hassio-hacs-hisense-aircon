"""Shared entity helpers for Hisense Air Conditioner."""

from __future__ import annotations

from dataclasses import Field, fields
import enum
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .aircon import Device
from .const import DOMAIN, signal_device_update
from .controller import HisenseController

_PROPERTY_INFO = {
    "f_electricity": ("Electricity", "Current electricity or power-related value reported by the device."),
    "f_e_arkgrille": ("Cabinet Grille Fault", "Alarm from cabinet grille protection."),
    "f_e_incoiltemp": ("Indoor Coil Temperature Fault", "Indoor coil temperature sensor fault."),
    "f_e_incom": ("Indoor Outdoor Communication Fault",
                   "Communication fault between the indoor and outdoor units."),
    "f_e_indisplay": ("Display Communication Fault",
                      "Communication fault between the indoor control panel and display panel."),
    "f_e_ineeprom": ("Indoor EEPROM Fault", "Indoor control panel EEPROM fault."),
    "f_e_inele": ("Indoor Power Board Communication Fault",
                  "Communication fault between the indoor control panel and indoor power panel."),
    "f_e_infanmotor": ("Indoor Fan Motor Fault", "Indoor fan motor fault."),
    "f_e_inhumidity": ("Indoor Humidity Sensor Fault", "Indoor humidity sensor fault."),
    "f_e_inkeys": ("Keyboard Communication Fault",
                   "Communication fault between the indoor control panel and keyboard plate."),
    "f_e_inlow": ("Indoor Low Voltage Fault", "Indoor low-voltage protection or fault flag."),
    "f_e_intemp": ("Indoor Temperature Sensor Fault", "Indoor temperature sensor fault."),
    "f_e_invzero": ("Zero Crossing Detection Fault", "Indoor voltage zero-crossing detection fault."),
    "f_e_outcoiltemp": ("Outdoor Coil Temperature Fault", "Outdoor coil temperature sensor fault."),
    "f_e_outeeprom": ("Outdoor EEPROM Fault", "Outdoor EEPROM fault."),
    "f_e_outgastemp": ("Outdoor Exhaust Temperature Fault", "Outdoor exhaust temperature sensor fault."),
    "f_e_outmachine2": ("Outdoor Unit Fault 2", "Secondary outdoor unit fault flag."),
    "f_e_outmachine": ("Outdoor Unit Fault", "Outdoor unit fault flag."),
    "f_e_outtemp": ("Outdoor Temperature Sensor Fault", "Outdoor ambient temperature sensor fault."),
    "f_e_outtemplow": ("Outdoor Low Temperature Fault", "Outdoor low-temperature protection or fault flag."),
    "f_e_push": ("WiFi Panel Communication Fault",
                 "Communication fault between the WiFi control panel and indoor control panel."),
    "f_filterclean": ("Filter Cleaning Required", "The indoor filter should be cleaned."),
    "f_humidity": ("Humidity", "Relative humidity reported by the indoor unit."),
    "f_power_display": ("Power Display", "Read-only display power state reported by the device."),
    "f_temp_in": ("Indoor Temperature", "Indoor ambient temperature reported by the device."),
    "f_voltage": ("Voltage", "Voltage value reported by the device."),
    "t_backlight": ("Backlight", "Turn the indoor unit display or backlight on or off."),
    "t_device_info": ("Device Info", "Device information request/control flag."),
    "t_display_power": ("Display Power", "Turn the indoor unit display power on or off."),
    "t_eco": ("Eco", "Economy mode."),
    "t_fan_leftright": ("Horizontal Swing", "Turn left/right air flow swing on or off."),
    "t_fan_mute": ("Quiet", "Quiet mode."),
    "t_fan_power": ("Vertical Swing", "Turn up/down air flow swing on or off."),
    "t_fan_speed": ("Fan Speed", "Fan speed."),
    "t_swing_angle": ("Vertical Swing Angle", "Vertical louver angle or sweep mode."),
    "t_ftkt_start": ("Self Clean Start", "Starts or controls the freeze-clean/self-clean cycle."),
    "t_power": ("Power", "Power on or off."),
    "t_run_mode": ("Double Frequency", "Double-frequency run mode."),
    "t_setmulti_value": ("Multi Control Value", "Packed device control value used by some models."),
    "t_sleep": ("Sleep", "Sleep mode."),
    "t_temp": ("Target Temperature", "Target temperature setpoint."),
    "t_temptype": ("Temperature Unit", "Displayed temperature unit."),
    "t_temp_eight": ("8 Degree Heat", "8 C heat / frost protection mode."),
    "t_temp_heatcold": ("Super", "Fast cool/heat mode, also known as Super or Turbo."),
    "t_work_mode": ("Work Mode", "Operating mode: fan, heat, cool, dry, or auto."),
}


class HisenseEntity(Entity):
  """Base entity for a Hisense device property."""

  _attr_has_entity_name = True

  def __init__(self, controller: HisenseController, device: Device) -> None:
    self.controller = controller
    self.device = device
    self._attr_device_info = DeviceInfo(
        identifiers={(DOMAIN, device.mac_address)},
        manufacturer=f"Hisense ({device.app})",
        model=device.model,
        name=device.name,
        sw_version=device.sw_version,
    )

  @property
  def available(self) -> bool:
    """Return if entity is available."""
    return self.device.available

  async def async_added_to_hass(self) -> None:
    """Subscribe to device updates."""
    await super().async_added_to_hass()
    self.async_on_remove(
        async_dispatcher_connect(
            self.hass,
            signal_device_update(self.controller.entry.entry_id, self.device.mac_address),
            self._handle_device_update,
        ))

  def _handle_device_update(self, prop_name: str, value: Any) -> None:
    self.hass.loop.call_soon_threadsafe(self.async_write_ha_state)


class HisensePropertyEntity(HisenseEntity):
  """Base entity for a single device property."""

  def __init__(self, controller: HisenseController, device: Device, field: Field[Any]) -> None:
    super().__init__(controller, device)
    self.field = field
    self.prop_name = field.name
    if field.name in {"t_eco", "t_fan_mute", "t_temp_heatcold", "t_backlight",
                      "t_display_power", "f_temp_in", "f_humidity", "f_filterclean", "t_sleep"}:
      self._attr_translation_key = "sleep_mode" if field.name == "t_sleep" else field.name
    else:
      self._attr_name = property_friendly_name(field.name)
    self._attr_unique_id = f"{device.mac_address}_{field.name}"

  @property
  def native_value(self) -> Any:
    """Return the current property value."""
    return property_to_native_value(self.device.get_known_property(self.prop_name))

  @property
  def extra_state_attributes(self) -> dict[str, Any]:
    """Return extra details for explaining protocol-derived entities."""
    attrs: dict[str, Any] = {"hisense_property": self.prop_name}
    if description := property_description(self.prop_name):
      attrs["description"] = description
    return attrs

  def _handle_device_update(self, prop_name: str, value: Any) -> None:
    if prop_name in (self.prop_name, "available"):
      self.hass.loop.call_soon_threadsafe(self.async_write_ha_state)


def climate_managed_properties(device: Device) -> set[str]:
  """Return only controls actually provided by this device's climate entity."""
  if not {"work_mode", "temp"} <= device.topics.keys():
    return set()
  names = {device.topics[key] for key in ("power", "work_mode", "temp", "fan_speed", "swing_mode")
           if key in device.topics}
  if device.get_property_type("t_fan_leftright") is not None:
    names.add("t_fan_leftright")
  return names


def property_fields(device: Device) -> list[Field[Any]]:
  """Return dataclass fields for a device."""
  return [field for field in fields(device.get_all_properties())
          if field.name not in climate_managed_properties(device)]


def property_to_native_value(value: Any) -> Any:
  """Convert protocol values to HA-friendly values."""
  if isinstance(value, enum.Enum):
    return value.name.lower()
  return value


def is_enum_type(value_type: type[Any]) -> bool:
  """Return if a dataclass field type is an enum."""
  return isinstance(value_type, type) and issubclass(value_type, enum.Enum)


def enum_options(value_type: type[enum.Enum]) -> list[str]:
  """Return lower-case enum options."""
  return [option.name.lower() for option in value_type]


def is_binary_enum(value_type: type[enum.Enum]) -> bool:
  """Return if enum is an ON/OFF style switch."""
  return {option.name for option in value_type} == {"OFF", "ON"}


def property_friendly_name(prop_name: str) -> str:
  """Return a Home Assistant friendly name for a protocol property."""
  if info := _PROPERTY_INFO.get(prop_name):
    return info[0]
  return _strip_protocol_prefix(prop_name).replace("_", " ").title()


def property_description(prop_name: str) -> str | None:
  """Return a short explanation for a protocol property."""
  if info := _PROPERTY_INFO.get(prop_name):
    return info[1]
  if prop_name.startswith("f_e_"):
    return "Device fault flag reported by the air conditioner."
  if prop_name.startswith("f_"):
    return "Read-only status value reported by the air conditioner."
  if prop_name.startswith("t_"):
    return "Writable control value sent to the air conditioner."
  return None


def _strip_protocol_prefix(prop_name: str) -> str:
  if prop_name.startswith("f_e_"):
    return prop_name[4:]
  if prop_name.startswith(("f_", "t_")):
    return prop_name[2:]
  return prop_name
