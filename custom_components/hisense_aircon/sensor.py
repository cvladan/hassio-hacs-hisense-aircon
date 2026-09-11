"""Sensor platform for read-only Hisense properties."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfElectricPotential, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .controller import HisenseConfigEntry, HisenseController
from .entity import HisensePropertyEntity, property_fields


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HisenseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
  """Set up sensor entities."""
  controller: HisenseController = entry.runtime_data
  entities = []
  for device in controller.devices:
    for field in property_fields(device):
      if field.metadata["read_only"] and field.type is not bool:
        entities.append(HisensePropertySensor(controller, device, field))
  async_add_entities(entities)


class HisensePropertySensor(HisensePropertyEntity, SensorEntity):
  """A read-only device property."""

  _attr_should_poll = False

  def __init__(self, controller, device, field) -> None:
    super().__init__(controller, device, field)
    if "temp" in field.name:
      self._attr_device_class = SensorDeviceClass.TEMPERATURE
      self._attr_native_unit_of_measurement = (
          UnitOfTemperature.FAHRENHEIT if device.is_fahrenheit else UnitOfTemperature.CELSIUS)
      self._attr_state_class = SensorStateClass.MEASUREMENT
    elif "humi" in field.name or "humidity" in field.name:
      self._attr_device_class = SensorDeviceClass.HUMIDITY
      self._attr_native_unit_of_measurement = PERCENTAGE
      self._attr_state_class = SensorStateClass.MEASUREMENT
    elif "voltage" in field.name:
      self._attr_device_class = SensorDeviceClass.VOLTAGE
      self._attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
      self._attr_state_class = SensorStateClass.MEASUREMENT
