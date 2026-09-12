"""Manual LAN refresh and reconnection actions."""

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import EntityCategory

from .entity import HisenseEntity


async def async_setup_entry(hass, entry, async_add_entities):
  controller = entry.runtime_data
  async_add_entities(HisenseButton(controller, device, action)
                     for device in controller.devices for action in ('refresh', 'reconnect'))


class HisenseButton(HisenseEntity, ButtonEntity):
  """An action that also works while the physical device is unavailable."""

  _attr_entity_category = EntityCategory.DIAGNOSTIC

  def __init__(self, controller, device, action):
    super().__init__(controller, device)
    self._action = action
    self._attr_unique_id = f'{device.mac_address}_lan_{action}'
    self._attr_translation_key = action
    self._attr_icon = 'mdi:refresh' if action == 'refresh' else 'mdi:lan-connect'
    self._update_properties.clear()

  @property
  def available(self):
    return True

  async def async_press(self):
    if self._action == 'refresh':
      self.device.queue_status()
    else:
      self.controller.reconnect_device(self.device)
