"""Switch platform for writable Hisense ON/OFF properties."""

from __future__ import annotations

import enum

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .controller import HisenseConfigEntry, HisenseController
from .entity import HisensePropertyEntity, is_binary_enum, is_enum_type, property_fields


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HisenseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
  """Set up switch entities."""
  controller: HisenseController = entry.runtime_data
  entities = []
  for device in controller.devices:
    for field in property_fields(device):
      if field.metadata["read_only"]:
        continue
      value_type = field.type
      if value_type is bool or (is_enum_type(value_type) and is_binary_enum(value_type)):
        entities.append(HisensePropertySwitch(controller, device, field))
  async_add_entities(entities)


class HisensePropertySwitch(HisensePropertyEntity, SwitchEntity):
  """A writable ON/OFF property."""

  _attr_should_poll = False

  @property
  def is_on(self) -> bool | None:
    """Return true if the property is on."""
    value = self.device.get_known_property(self.prop_name)
    if isinstance(value, enum.Enum):
      return value.name == "ON"
    if value is None:
      return None
    return bool(value)

  async def async_turn_on(self, **kwargs) -> None:
    """Turn the property on."""
    if is_enum_type(self.field.type):
      self.device.queue_command(self.prop_name, "ON")
    else:
      self.device.queue_command(self.prop_name, True)
    self.async_write_ha_state()

  async def async_turn_off(self, **kwargs) -> None:
    """Turn the property off."""
    if is_enum_type(self.field.type):
      self.device.queue_command(self.prop_name, "OFF")
    else:
      self.device.queue_command(self.prop_name, False)
    self.async_write_ha_state()
