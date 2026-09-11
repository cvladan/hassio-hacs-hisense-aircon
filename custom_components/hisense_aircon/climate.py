"""Climate platform for Hisense Air Conditioner."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ATTR_TEMPERATURE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    SWING_BOTH,
    SWING_HORIZONTAL,
    SWING_OFF,
    SWING_ON,
    SWING_VERTICAL,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .aircon import Device
from .const import DOMAIN
from .controller import HisenseController
from .entity import HisenseEntity
from .properties import AcWorkMode, AirFlow, FglOperationMode, Power

HVAC_TO_DEVICE = {
    HVACMode.AUTO: "AUTO",
    HVACMode.COOL: "COOL",
    HVACMode.DRY: "DRY",
    HVACMode.FAN_ONLY: "FAN",
    HVACMode.HEAT: "HEAT",
}

AC_TO_HVAC = {
    AcWorkMode.AUTO: HVACMode.AUTO,
    AcWorkMode.COOL: HVACMode.COOL,
    AcWorkMode.DRY: HVACMode.DRY,
    AcWorkMode.FAN: HVACMode.FAN_ONLY,
    AcWorkMode.HEAT: HVACMode.HEAT,
}

FGL_TO_HVAC = {
    FglOperationMode.AUTO: HVACMode.AUTO,
    FglOperationMode.COOL: HVACMode.COOL,
    FglOperationMode.DRY: HVACMode.DRY,
    FglOperationMode.FAN_ONLY: HVACMode.FAN_ONLY,
    FglOperationMode.HEAT: HVACMode.HEAT,
    FglOperationMode.OFF: HVACMode.OFF,
    FglOperationMode.ON: HVACMode.AUTO,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
  """Set up climate entities."""
  controller: HisenseController = hass.data[DOMAIN][entry.entry_id]
  async_add_entities(
      HisenseClimate(controller, device)
      for device in controller.devices
      if "work_mode" in device.topics and "temp" in device.topics)


class HisenseClimate(HisenseEntity, ClimateEntity):
  """Hisense air conditioner climate entity."""

  _attr_name = None
  _attr_should_poll = False
  _attr_target_temperature_step = 1.0

  def __init__(self, controller: HisenseController, device: Device) -> None:
    super().__init__(controller, device)
    self._attr_unique_id = device.mac_address

  @property
  def supported_features(self) -> ClimateEntityFeature:
    """Return supported features."""
    features = ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
    if "temp" in self.device.topics:
      features |= ClimateEntityFeature.TARGET_TEMPERATURE
    if "fan_speed" in self.device.topics:
      features |= ClimateEntityFeature.FAN_MODE
    if self._supports_swing:
      features |= ClimateEntityFeature.SWING_MODE
    return features

  @property
  def temperature_unit(self) -> str:
    """Return the temperature unit."""
    return UnitOfTemperature.FAHRENHEIT if self.device.is_fahrenheit else UnitOfTemperature.CELSIUS

  @property
  def min_temp(self) -> float:
    """Return minimum target temperature."""
    # Home Assistant converts its displayed 16 C lower bound back to 60.8 F.
    # Command precision rounds that value to the supported 61 F setpoint.
    return 60.8 if self.device.is_fahrenheit else 16

  @property
  def max_temp(self) -> float:
    """Return maximum target temperature."""
    return 86 if self.device.is_fahrenheit else 30

  @property
  def target_temperature_step(self) -> float:
    """Return target temperature step."""
    return self.device.get_temp_precision()

  @property
  def current_temperature(self) -> float | None:
    """Return current room temperature."""
    prop = self.device.topics.get("env_temp") or self.device.topics.get("display_temperature")
    return self.device.get_known_property(prop) if prop else None

  @property
  def current_humidity(self) -> int | None:
    """Return current humidity."""
    return self.device.get_known_property("f_humidity")

  @property
  def target_temperature(self) -> float | None:
    """Return target temperature."""
    return self.device.get_known_property(self.device.topics["temp"])

  @property
  def hvac_modes(self) -> list[HVACMode]:
    """Return available HVAC modes."""
    return [
        HVACMode.OFF,
        HVACMode.FAN_ONLY,
        HVACMode.HEAT,
        HVACMode.COOL,
        HVACMode.DRY,
        HVACMode.AUTO,
    ]

  @property
  def hvac_mode(self) -> HVACMode | None:
    """Return current HVAC mode."""
    if power_prop := self.device.topics.get("power"):
      power = self.device.get_known_property(power_prop)
      if power is None:
        return None
      if power == Power.OFF:
        return HVACMode.OFF
    mode = self.device.get_known_property(self.device.topics["work_mode"])
    if isinstance(mode, AcWorkMode):
      return AC_TO_HVAC.get(mode)
    if isinstance(mode, FglOperationMode):
      return FGL_TO_HVAC.get(mode)
    return None

  @property
  def fan_modes(self) -> list[str] | None:
    """Return supported fan modes."""
    return self.device.fan_modes or None

  @property
  def fan_mode(self) -> str | None:
    """Return current fan mode."""
    prop = self.device.topics.get("fan_speed")
    value = self.device.get_known_property(prop) if prop else None
    return value.name.lower() if value is not None else None

  @property
  def swing_modes(self) -> list[str] | None:
    """Return supported swing modes."""
    if not self._supports_swing:
      return None
    if self._supports_horizontal_swing:
      return [SWING_OFF, SWING_VERTICAL, SWING_HORIZONTAL, SWING_BOTH]
    return [SWING_OFF, SWING_ON]

  @property
  def swing_mode(self) -> str | None:
    """Return current swing mode."""
    vertical = self.device.get_known_property("t_fan_power")
    horizontal = self.device.get_known_property("t_fan_leftright")
    if isinstance(vertical, AirFlow) or isinstance(horizontal, AirFlow):
      vertical_on = vertical == AirFlow.ON
      horizontal_on = horizontal == AirFlow.ON
      if vertical_on and horizontal_on:
        return SWING_BOTH
      if vertical_on:
        return SWING_VERTICAL
      if horizontal_on:
        return SWING_HORIZONTAL
      return SWING_OFF

    prop = self.device.topics.get("swing_mode")
    value = self.device.get_known_property(prop) if prop else None
    if value == AirFlow.ON:
      return SWING_ON
    if value == AirFlow.OFF:
      return SWING_OFF
    return None

  @property
  def _supports_swing(self) -> bool:
    return "swing_mode" in self.device.topics or self._supports_horizontal_swing

  @property
  def _supports_horizontal_swing(self) -> bool:
    return self.device.get_property_type("t_fan_leftright") is not None

  async def async_set_temperature(self, **kwargs: Any) -> None:
    """Set target temperature."""
    if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
      self.device.queue_command(self.device.topics["temp"], temperature)
    if (hvac_mode := kwargs.get("hvac_mode")) is not None:
      await self.async_set_hvac_mode(hvac_mode)
    self.async_write_ha_state()

  async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
    """Set HVAC mode."""
    if hvac_mode == HVACMode.OFF:
      self.device.queue_command(self.device.topics["work_mode"], "OFF")
    else:
      self.device.queue_command(self.device.topics["work_mode"], HVAC_TO_DEVICE[hvac_mode])
    self.async_write_ha_state()

  async def async_turn_on(self) -> None:
    """Turn the device on."""
    await self.async_set_hvac_mode(HVACMode.AUTO)

  async def async_turn_off(self) -> None:
    """Turn the device off."""
    await self.async_set_hvac_mode(HVACMode.OFF)

  async def async_set_fan_mode(self, fan_mode: str) -> None:
    """Set fan mode."""
    self.device.queue_command(self.device.topics["fan_speed"], fan_mode.upper())
    self.async_write_ha_state()

  async def async_set_swing_mode(self, swing_mode: str) -> None:
    """Set swing mode."""
    if self._supports_horizontal_swing:
      vertical = AirFlow.ON if swing_mode in (SWING_VERTICAL, SWING_BOTH) else AirFlow.OFF
      horizontal = AirFlow.ON if swing_mode in (SWING_HORIZONTAL, SWING_BOTH) else AirFlow.OFF
      self.device.queue_command("t_fan_power", vertical.name)
      self.device.queue_command("t_fan_leftright", horizontal.name)
    else:
      self.device.queue_command(
          self.device.topics["swing_mode"],
          "ON" if swing_mode == SWING_ON else "OFF",
      )
    self.async_write_ha_state()
