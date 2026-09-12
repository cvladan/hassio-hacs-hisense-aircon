"""Sensor platform for read-only Hisense properties."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfElectricPotential, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .controller import HisenseConfigEntry, HisenseController
from homeassistant.helpers.entity import EntityCategory

from .entity import HisenseEntity, HisensePropertyEntity, property_fields


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
    entities.extend(HisenseDiagnosticSensor(controller, device, key)
                    for key in ('last_message', 'last_registration', 'failures', 'queued_commands'))
  async_add_entities(entities)


class HisensePropertySensor(HisensePropertyEntity, SensorEntity):
  """A read-only device property."""


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


class HisenseDiagnosticSensor(HisenseEntity, SensorEntity):
  """Optional connection measurements that remain readable while a device is offline."""

  _attr_entity_category = EntityCategory.DIAGNOSTIC
  _attr_entity_registry_enabled_default = False

  def __init__(self, controller, device, key):
    super().__init__(controller, device)
    self._key = key
    self._attr_unique_id = f"{device.mac_address}_diagnostic_{key}"
    self._attr_translation_key = key
    self._update_properties = {key}
    if key.startswith('last_'):
      self._attr_device_class = SensorDeviceClass.TIMESTAMP

  @property
  def available(self):
    return True

  @property
  def native_value(self):
    if self._key == 'queued_commands':
      return self.device.commands_queue.qsize()
    return self.device.diagnostics[self._key]
