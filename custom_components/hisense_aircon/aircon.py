from dataclasses import dataclass, field, fields
from functools import partial
import enum
import logging
import random
import re
import string
from typing import Callable, Dict
import asyncio
from datetime import datetime, timezone
from itertools import count

from . import control_value
from .config import Config, Encryption
from .error import Error, KeyIdReplaced
from .properties import (AcProperties, FglProperties, FglBProperties,
                         HumidifierProperties, Properties, Power, TemperatureUnit)

_LOGGER = logging.getLogger(__name__)

_CONTROL_FIELDS = {
    't_power': (control_value.set_power, control_value.get_power),
    't_fan_speed': (control_value.set_fan_speed, control_value.get_fan_speed),
    't_work_mode': (control_value.set_work_mode, control_value.get_work_mode),
    't_temp_heatcold': (control_value.set_heat_cold, control_value.get_heat_cold),
    't_eco': (control_value.set_eco, control_value.get_eco),
    't_temp': (control_value.set_temp, control_value.get_temp),
    't_fan_power': (control_value.set_fan_power, control_value.get_fan_power),
    't_fan_leftright': (control_value.set_fan_lr, control_value.get_fan_lr),
    't_fan_mute': (control_value.set_fan_mute, control_value.get_fan_mute),
    't_temptype': (control_value.set_temptype, control_value.get_temptype),
}


@dataclass(order=True)
class Command:
  priority: int
  order: int  # Preserve FIFO independently of wall clock changes.
  command: Dict = field(compare=False)
  updater: Callable = field(compare=False)


class Device:
  """Device state and commands, owned by the Home Assistant event loop."""

  _FGL_DEVICES = re.compile(r'AP-W[ACDF]\dE')
  _FGLB_DEVICES = re.compile(r'AP-WB\dE')
  _HUMI_DEVICES = re.compile(r'0001-0401-000[12]')

  def __init__(self, config: Dict[str, str], properties: Properties, notifier: Callable[[], None]):
    self.name = config['name']
    self.app = config['app']
    self.model = config['model']
    self.sw_version = config['sw_version']
    self.mac_address = config['mac_address']
    self.ip_address = config['ip_address']
    self.temp_type = (TemperatureUnit.CELSIUS
                      if config.get('temp_type') == 'C' else TemperatureUnit.FAHRENHEIT)
    self._config = Config(config['lanip_key'], config['lanip_key_id'])
    self._properties = properties
    self._reported_properties = {}
    self._known_properties = set()
    self._pending_control = None
    self._pending_control_count = 0
    self._queue_listener = notifier
    self._available = None
    self.topics = {}
    self.fan_modes = []

    self._next_command_id = 0
    self._pending_status = set()

    self.commands_queue = asyncio.PriorityQueue()
    self._command_order = count()
    self.diagnostics = {"last_message": None, "last_registration": None, "failures": 0}
    self.lan_key_invalid = False
    self._commands_seq_no = 0

    self._updates_seq_no = 0

    self._property_change_listeners: list[Callable[[str, set[str]], None]] = []

  @classmethod
  def create(cls, config: Dict[str, str], notifier: Callable[[], None]):
    model = config['model']
    if cls._FGL_DEVICES.fullmatch(model):
      return FglDevice(config, notifier)
    if cls._FGLB_DEVICES.fullmatch(model):
      return FglBDevice(config, notifier)
    if cls._HUMI_DEVICES.fullmatch(model):
      return HumidifierDevice(config, notifier)
    return AcDevice(config, notifier)

  @property
  def is_fahrenheit(self) -> bool:
    return self.temp_type == TemperatureUnit.FAHRENHEIT

  @property
  def available(self) -> bool:
    # Return False if was not set yet.
    return self._available or False

  @available.setter
  def available(self, value: bool):
    if self._available != value:
      self._available = value
      self._notify_listeners({'available'})

  def add_property_change_listener(self, listener: Callable[[str, set[str]], None]):
    self._property_change_listeners.append(listener)

  def remove_property_change_listener(self, listener: Callable[[str, set[str]], None]):
    if listener in self._property_change_listeners:
      self._property_change_listeners.remove(listener)

  def _notify_listeners(self, changed: set[str]):
    if changed:
      for listener in tuple(self._property_change_listeners):
        listener(self.mac_address, changed)

  def update_diagnostics(self, **values):
    changed = {name for name, value in values.items() if self.diagnostics[name] != value}
    self.diagnostics.update(values)
    self._notify_listeners(changed)

  def record_message(self):
    self.update_diagnostics(last_message=datetime.now(timezone.utc))

  def get_property_fields(self):
    return fields(self._properties)

  def get_property(self, name: str):
    """Get a stored property, or None if it does not exist."""
    return getattr(self._properties, name, None)

  def get_reported_property(self, name: str):
    """Return the last value received from the device, without protocol defaults."""
    return self._reported_properties.get(name)

  def get_known_property(self, name: str):
    """Return received or sent state, excluding initialization defaults."""
    return self.get_property(name) if name in self._known_properties else None

  def get_property_type(self, name: str):
    return (self._properties.get_type(name)
            if name in self._properties.__dataclass_fields__ else None)

  def parse_property(self, name: str, value):
    return self._properties.parse_attr(name, value)

  def get_temp_precision(self) -> float:
    prop_name = self.topics.get('temp')
    if not prop_name:
      return 1.0
    return float(self._properties.get_precision(prop_name))

  def update_property(self, name: str, value, *, reported=True, notify=True) -> set[str]:
    """Apply a complete update before notifying entities about its changed fields."""
    if value is not None and self._properties.get_type(name) is int:
      scale = self._properties.get_scale(name)
      precision = self._properties.get_precision(name)
      value = round(value * scale / precision) * precision

    changed = {name} if (name not in self._known_properties
                        or getattr(self._properties, name) != value
                        or (reported and name not in self._reported_properties)) else set()
    self._known_properties.add(name)
    if reported:
      self._reported_properties[name] = value
    setattr(self._properties, name, value)
    if name == 't_control_value':
      changed.update(self._update_controlled_properties(value, reported=reported))
    if notify:
      self._notify_listeners(changed)
    return changed

  def _update_controlled_properties(self, control: int, *, reported=True):
    raise NotImplementedError()

  def get_command_seq_no(self) -> int:
    seq_no = self._commands_seq_no
    self._commands_seq_no += 1
    return seq_no

  def is_update_valid(self, cur_update_no: int) -> bool:
    # Some devices reset the sequence number to zero during a session.
    if self._updates_seq_no > cur_update_no and cur_update_no > 0:
      _LOGGER.error('Stale update found %d. Last update used is %d.', cur_update_no,
                    self._updates_seq_no)
      return False
    self._updates_seq_no = cur_update_no
    return True

  def queue_command(self, name: str, value) -> None:
    if self._properties.get_read_only(name):
      raise Error('Cannot update read-only property "{}".'.format(name))
    data_type = self._properties.get_type(name)

    if issubclass(data_type, enum.Enum):
      data_value = value if isinstance(value, data_type) else data_type[str(value).upper()]
    elif data_type is int:
      float_val = float(value)
      precision = self._properties.get_precision(name)
      scale = self._properties.get_scale(name)
      float_val = (round(float_val / precision) * precision) / scale
      data_value = round(float_val)
    else:
      data_value = data_type(value)

    # If device has set t_control_value it is being controlled by this field.
    if name in _CONTROL_FIELDS and self._command_control():
      self._convert_to_control_value(name, data_value)
      return

    if issubclass(data_type, enum.Enum):
      typed_value = data_value
      data_value = data_value.value
    else:
      typed_value = data_value

    command = self._build_command(name, data_value)
    # There are (usually) no acks on commands, so also queue an update to the
    # property, to be run once the command is sent.
    if name == 't_control_value':
      self._pending_control = typed_value
      self._pending_control_count += 1

    def property_updater():
      if name == 't_control_value':
        self._pending_control_count -= 1
        if self._pending_control_count == 0:
          self._pending_control = None
      self.update_property(name, typed_value, reported=False)
    # Add as a high priority command.
    self.commands_queue.put_nowait(Command(10, next(self._command_order), command, property_updater))

    self._queue_listener()
    self._notify_listeners({"queued_commands"})

  def _command_control(self):
    """Merge writes into the last unsent command, even after an older status arrives."""
    if self._pending_control is not None:
      return self._pending_control
    return self.get_property('t_control_value')

  def _build_command(self, name: str, data_value: int):
    base_type = self._properties.get_base_type(name)
    return {
        'properties': [{
            'property': {
                'base_type': base_type,
                'name': name,
                'value': data_value,
                'id': ''.join(random.choices(string.ascii_letters + string.digits, k=8)),
            }
        }]
    }

  def _convert_to_control_value(self, name: str, value) -> None:
    raise NotImplementedError()

  def queue_status(self) -> None:
    queued = False
    for data_field in self.get_property_fields():
      if data_field.name in self._pending_status:
        continue
      self._pending_status.add(data_field.name)
      queued = True
      command = {
          'cmds': [{
              'cmd': {
                  'method': 'GET',
                  'resource': 'property.json?name=' + data_field.name,
                  'uri': '/local_lan/property/datapoint.json',
                  'data': '',
                  'cmd_id': self._next_command_id,
              }
          }]
      }
      self._next_command_id += 1
      # Add as a lower-priority command.
      self.commands_queue.put_nowait(Command(
          100, next(self._command_order), command, partial(self._pending_status.discard, data_field.name)))
    if queued:
      self._queue_listener()
      self._notify_listeners({"queued_commands"})

  def update_key(self, key: dict) -> dict:
    try:
      result = self._config.update(key)
    except KeyIdReplaced:
      if not self.lan_key_invalid:
        self.lan_key_invalid = True
        self._notify_listeners({'lan_key_invalid'})
      raise
    self.lan_key_invalid = False
    self._notify_listeners({'lan_key_invalid'})
    return result

  def get_app_encryption(self) -> Encryption:
    return self._config.app

  def get_dev_encryption(self) -> Encryption:
    return self._config.dev


class AcDevice(Device):

  def __init__(self, config: Dict[str, str], notifier: Callable[[], None]):
    super().__init__(config, AcProperties(), notifier)
    self.topics = {
        'env_temp': 'f_temp_in',
        'fan_speed': 't_fan_speed',
        'work_mode': 't_work_mode',
        'power': 't_power',
        'swing_mode': 't_fan_power',
        'swing_horizontal_mode': 't_fan_leftright',
        'temp': 't_temp'
    }
    self.fan_modes = ['auto', 'lower', 'low', 'medium', 'high', 'higher']

  # @override to add special support for t_power.
  def queue_command(self, name: str, value) -> None:
    # Home Assistant climate commands do not always include a separate power command.
    # Furthermore, turn_on doesn't send the right command...
    if name == 't_work_mode':
      if value == 'OFF':
        # Pass the command to t_power instead of t_work_mode.
        name = 't_power'
      else:
        # Also turn on the AC (if it hasn't already).
        super().queue_command('t_power', 'ON')

    # Run base.
    super().queue_command(name, value)

    # Handle turning on FastColdHeat
    if name == 't_temp_heatcold' and value == 'ON':
      super().queue_command('t_fan_speed', 'AUTO')
      super().queue_command('t_fan_mute', 'OFF')
      super().queue_command('t_sleep', 'STOP')
      super().queue_command('t_temp_eight', 'OFF')

  def _convert_to_control_value(self, name: str, value) -> None:
    control = control_value.clear_up_change_flags(self._command_control())
    if name == 't_work_mode' and control_value.get_power(control) == Power.OFF:
      control = control_value.set_power(control, Power.ON)
    setter, _ = _CONTROL_FIELDS[name]
    self.queue_command('t_control_value', setter(control, value))

  def _update_controlled_properties(self, control: int, *, reported=True):
    changed = set()
    for name, (_, decoder) in _CONTROL_FIELDS.items():
      try:
        value = decoder(control)
      except ValueError:
        _LOGGER.debug('Unknown %s in control value %s', name, control)
        value = None
      changed.update(self.update_property(name, value, reported=reported, notify=False))
    return changed


class FglDevice(Device):

  def __init__(self, config: Dict[str, str], notifier: Callable[[], None]):
    super().__init__(config, FglProperties(), notifier)
    self.topics = {
        'fan_speed': 'fan_speed',
        'work_mode': 'operation_mode',
        'swing_mode': 'af_vertical_swing',
        'temp': 'adjust_temperature',
        'display_temperature': 'display_temperature',
        'outdoor_temperature': 'outdoor_temperature'
    }
    self.fan_modes = ['auto', 'diffuse', 'low', 'medium', 'high']


class FglBDevice(Device):

  def __init__(self, config: Dict[str, str], notifier: Callable[[], None]):
    super().__init__(config, FglBProperties(), notifier)
    self.topics = {
        'fan_speed': 'fan_speed',
        'work_mode': 'operation_mode',
        'temp': 'adjust_temperature',
        'display_temperature': 'display_temperature'
    }
    self.fan_modes = ['auto', 'diffuse', 'low', 'medium', 'high']


class HumidifierDevice(Device):

  def __init__(self, config: Dict[str, str], notifier: Callable[[], None]):
    super().__init__(config, HumidifierProperties(), notifier)
    self.topics = {'env_temp': 'temp', 'power': 'switch', 'humidity': 'humi'}
