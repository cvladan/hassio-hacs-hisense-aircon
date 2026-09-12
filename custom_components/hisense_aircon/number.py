"""Number platform for writable numeric Hisense properties."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .controller import HisenseConfigEntry, HisenseController
from .entity import HisensePropertyEntity, property_fields

_INTERNAL_NUMBERS = {"t_control_value"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HisenseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
  """Set up number entities."""
  controller: HisenseController = entry.runtime_data
  entities = []
  for device in controller.devices:
    for field in property_fields(device):
      if field.metadata["read_only"] or field.name in _INTERNAL_NUMBERS:
        continue
      if field.type in (int, float):
        entities.append(HisensePropertyNumber(controller, device, field))
  async_add_entities(entities)


class HisensePropertyNumber(HisensePropertyEntity, NumberEntity):
  """A writable numeric property."""

  _attr_native_step = 1

  def __init__(self, controller, device, field) -> None:
    super().__init__(controller, device, field)
    if "temp" in field.name:
      self._attr_native_min_value = 61 if device.is_fahrenheit else 16
      self._attr_native_max_value = 86 if device.is_fahrenheit else 30
      self._attr_native_unit_of_measurement = (
          UnitOfTemperature.FAHRENHEIT if device.is_fahrenheit else UnitOfTemperature.CELSIUS)
    elif "humi" in field.name:
      self._attr_native_min_value = 30
      self._attr_native_max_value = 99
      self._attr_native_unit_of_measurement = PERCENTAGE

  async def async_set_native_value(self, value: float) -> None:
    """Set numeric value."""
    data_value = int(value) if self.field.type is int else value
    self.device.queue_command(self.prop_name, data_value)
