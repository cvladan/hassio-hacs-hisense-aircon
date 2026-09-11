"""Select platform for writable Hisense enum properties."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .controller import HisenseConfigEntry, HisenseController
from .entity import (
    HisensePropertyEntity,
    enum_options,
    is_binary_enum,
    is_enum_type,
    property_fields,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HisenseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
  """Set up select entities."""
  controller: HisenseController = entry.runtime_data
  entities = []
  for device in controller.devices:
    for field in property_fields(device):
      if field.metadata["read_only"]:
        continue
      if is_enum_type(field.type) and not is_binary_enum(field.type):
        entities.append(HisensePropertySelect(controller, device, field))
  async_add_entities(entities)


class HisensePropertySelect(HisensePropertyEntity, SelectEntity):
  """A writable enum property."""

  _attr_should_poll = False

  @property
  def options(self) -> list[str]:
    """Return available options."""
    return enum_options(self.field.type)

  @property
  def current_option(self) -> str | None:
    """Return current selected option."""
    return self.native_value

  async def async_select_option(self, option: str) -> None:
    """Select an option."""
    self.device.queue_command(self.prop_name, option.upper())
    self.async_write_ha_state()
