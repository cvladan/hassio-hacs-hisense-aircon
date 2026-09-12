"""Climate platform for Hisense Air Conditioner."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ATTR_TEMPERATURE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    SWING_OFF,
    SWING_ON,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .aircon import Device
from .controller import HisenseConfigEntry, HisenseController
from .entity import HisenseEntity
from .properties import AcWorkMode, FglOperationMode, Power

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
    entry: HisenseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
  """Set up climate entities."""
  controller: HisenseController = entry.runtime_data
  async_add_entities(
      HisenseClimate(controller, device)
      for device in controller.devices
      if "work_mode" in device.topics and "temp" in device.topics)


class HisenseClimate(HisenseEntity, ClimateEntity):
  """Hisense air conditioner climate entity."""

  _attr_name = None
  _attr_hvac_modes = [HVACMode.OFF, HVACMode.FAN_ONLY, HVACMode.HEAT,
                      HVACMode.COOL, HVACMode.DRY, HVACMode.AUTO]

  def __init__(self, controller: HisenseController, device: Device) -> None:
    super().__init__(controller, device)
    self._attr_unique_id = device.mac_address
    self._attr_supported_features = ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
    for topic, feature in (
        ("temp", ClimateEntityFeature.TARGET_TEMPERATURE),
        ("fan_speed", ClimateEntityFeature.FAN_MODE),
        ("swing_mode", ClimateEntityFeature.SWING_MODE),
        ("swing_horizontal_mode", ClimateEntityFeature.SWING_HORIZONTAL_MODE),
    ):
      if topic in device.topics:
        self._attr_supported_features |= feature
    self._attr_temperature_unit = UnitOfTemperature.FAHRENHEIT if device.is_fahrenheit else UnitOfTemperature.CELSIUS
    # HA converts its displayed 16 C lower bound to 60.8 F, which rounds to 61 F.
    self._attr_min_temp = 60.8 if device.is_fahrenheit else 16
    self._attr_max_temp = 86 if device.is_fahrenheit else 30
    self._attr_target_temperature_step = device.get_temp_precision()
    self._attr_fan_modes = device.fan_modes or None
    self._attr_swing_modes = [SWING_OFF, SWING_ON] if "swing_mode" in device.topics else None
    self._attr_swing_horizontal_modes = [SWING_OFF, SWING_ON] if "swing_horizontal_mode" in device.topics else None
    self._update_properties.update(device.topics[key] for key in (
        "power", "work_mode", "temp", "fan_speed", "swing_mode",
        "swing_horizontal_mode", "env_temp", "display_temperature") if key in device.topics)
    self._update_properties.add("f_humidity")

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
  def fan_mode(self) -> str | None:
    """Return current fan mode."""
    prop = self.device.topics.get("fan_speed")
    value = self.device.get_known_property(prop) if prop else None
    return value.name.lower() if value is not None else None

  @property
  def swing_mode(self) -> str | None:
    """Return vertical swing without inferring the other axis."""
    prop = self.device.topics.get("swing_mode")
    value = self.device.get_known_property(prop) if prop else None
    return value.name.lower() if value is not None else None

  @property
  def swing_horizontal_mode(self) -> str | None:
    """Return horizontal swing independently of vertical swing."""
    prop = self.device.topics.get("swing_horizontal_mode")
    value = self.device.get_known_property(prop) if prop else None
    return value.name.lower() if value is not None else None

  async def async_set_temperature(self, **kwargs: Any) -> None:
    """Set target temperature."""
    if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
      self.device.queue_command(self.device.topics["temp"], temperature)
    if (hvac_mode := kwargs.get("hvac_mode")) is not None:
      await self.async_set_hvac_mode(hvac_mode)

  async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
    """Set HVAC mode."""
    if hvac_mode == HVACMode.OFF:
      self.device.queue_command(self.device.topics["work_mode"], "OFF")
    else:
      self.device.queue_command(self.device.topics["work_mode"], HVAC_TO_DEVICE[hvac_mode])

  async def async_turn_on(self) -> None:
    """Turn the device on."""
    prop = self.device.topics.get("power") or self.device.topics["work_mode"]
    self.device.queue_command(prop, "ON")

  async def async_turn_off(self) -> None:
    """Turn the device off."""
    await self.async_set_hvac_mode(HVACMode.OFF)

  async def async_set_fan_mode(self, fan_mode: str) -> None:
    """Set fan mode."""
    self.device.queue_command(self.device.topics["fan_speed"], fan_mode.upper())

  async def async_set_swing_mode(self, swing_mode: str) -> None:
    """Set vertical swing without changing horizontal swing."""
    self.device.queue_command(self.device.topics["swing_mode"], swing_mode.upper())

  async def async_set_swing_horizontal_mode(self, swing_horizontal_mode: str) -> None:
    """Set horizontal swing without changing vertical swing."""
    self.device.queue_command(self.device.topics["swing_horizontal_mode"], swing_horizontal_mode.upper())
