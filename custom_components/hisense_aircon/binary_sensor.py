"""Binary sensor platform for read-only Hisense boolean properties."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .controller import HisenseConfigEntry, HisenseController
from .entity import HisensePropertyEntity, property_fields


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HisenseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
  """Set up binary sensor entities."""
  controller: HisenseController = entry.runtime_data
  entities = []
  for device in controller.devices:
    for field in property_fields(device):
      if field.metadata["read_only"] and field.type is bool:
        entities.append(HisensePropertyBinarySensor(controller, device, field))
  async_add_entities(entities)


class HisensePropertyBinarySensor(HisensePropertyEntity, BinarySensorEntity):
  """A read-only boolean property."""


  def __init__(self, controller, device, field) -> None:
    super().__init__(controller, device, field)
    if field.name.startswith("f_e_") or field.name == "f_filterclean":
      self._attr_device_class = BinarySensorDeviceClass.PROBLEM

  @property
  def is_on(self) -> bool | None:
    """Return true if the binary property is active."""
    value = self.device.get_known_property(self.prop_name)
    if value is None:
      return None
    return bool(value)
