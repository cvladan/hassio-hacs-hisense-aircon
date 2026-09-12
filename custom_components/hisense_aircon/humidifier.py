"""Native controls for supported Ayla humidifiers."""

from homeassistant.components.humidifier import (
    HumidifierDeviceClass, HumidifierEntity, HumidifierEntityFeature,
)
from homeassistant.exceptions import ServiceValidationError

from .aircon import HumidifierDevice
from .entity import HisenseEntity
from .properties import HumidifierWorkMode, Power


async def async_setup_entry(hass, entry, async_add_entities):
  controller = entry.runtime_data
  async_add_entities(HisenseHumidifier(controller, device) for device in controller.devices
                     if isinstance(device, HumidifierDevice))


class HisenseHumidifier(HisenseEntity, HumidifierEntity):
  """Humidity and mode controls backed by reported or sent device state."""

  _attr_name = None
  _attr_translation_key = "humidifier"
  _attr_device_class = HumidifierDeviceClass.HUMIDIFIER
  _attr_supported_features = HumidifierEntityFeature.MODES
  _attr_available_modes = [mode.name.lower() for mode in HumidifierWorkMode]
  _attr_min_humidity = 30
  _attr_max_humidity = 99
  _attr_target_humidity_step = 1

  def __init__(self, controller, device):
    super().__init__(controller, device)
    self._attr_unique_id = device.mac_address
    self._update_properties.update({'switch', 'humi', 'realhumi', 'workmode'})

  @property
  def is_on(self):
    value = self.device.get_known_property('switch')
    return None if value is None else value == Power.ON

  @property
  def current_humidity(self):
    return self.device.get_known_property('realhumi')

  @property
  def target_humidity(self):
    return self.device.get_known_property('humi')

  @property
  def mode(self):
    value = self.device.get_known_property('workmode')
    return value.name.lower() if value is not None else None

  async def async_turn_on(self, **kwargs):
    self.device.queue_command('switch', 'ON')

  async def async_turn_off(self, **kwargs):
    self.device.queue_command('switch', 'OFF')

  async def async_set_humidity(self, humidity):
    if type(humidity) is not int or not self.min_humidity <= humidity <= self.max_humidity:
      raise ServiceValidationError('Humidity must be a whole number from 30 to 99.')
    self.device.queue_command('humi', humidity)

  async def async_set_mode(self, mode):
    if mode not in self.available_modes:
      raise ServiceValidationError('Unsupported humidifier mode.')
    self.device.queue_command('workmode', mode.upper())
