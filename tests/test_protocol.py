"""Ayla command and status regressions, without a device or network."""

import unittest
from unittest.mock import AsyncMock, Mock, patch

from custom_components.hisense_aircon.aircon import Device
from custom_components.hisense_aircon import control_value
from custom_components.hisense_aircon.properties import Power, AcWorkMode, Quiet
from custom_components.hisense_aircon.query_handlers import QueryHandlers
from test_config_flow import device


def ac():
  result = Device.create(device(), lambda: None)
  value = control_value.set_power(0, Power.ON)
  value = control_value.set_work_mode(value, AcWorkMode.COOL)
  value = control_value.set_temp(value, 24)
  result.update_property('t_control_value', value)
  return result


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
  async def test_quiet_packets_do_not_drop_other_fields(self):
    for value in (808715331, 540279874):
      unit = ac()
      unit.update_property('t_control_value', value)
      self.assertEqual(unit.get_property('t_fan_mute'), Quiet.ON)
      self.assertEqual(unit.get_property('t_temp'), control_value.get_temp(value))
      self.assertIsNone(unit.get_property('t_fan_speed'))
      unit.queue_command('t_temp', 23)
      self.assertFalse(unit.commands_queue.empty())
    unit.update_property('t_control_value', value | (7 << 9))
    self.assertIsNone(unit.get_property('t_work_mode'))
    self.assertEqual(unit.get_property('t_fan_mute'), Quiet.ON)

  async def test_unknown_properties_are_ignored(self):
    unit = ac()
    handlers = QueryHandlers([unit])
    request = Mock(remote=unit.ip_address)
    request.clone.return_value.json = AsyncMock(return_value={})
    for index, name in enumerate(('version', 't_swing_direction', 't_temp')):
      update = {'seq_no': index, 'data': {'name': name, 'value': 23}}
      with patch.object(handlers, '_decrypt_and_validate', return_value=update):
        response = await handlers.property_update_handler(request)
      self.assertEqual(response.status, 200)
    self.assertEqual(unit.get_property('t_temp'), 23)

  async def test_pending_commands_survive_an_older_report(self):
    unit = ac()
    old = unit.get_property('t_control_value')
    unit.queue_command('t_temp', 22)
    unit.update_property('t_control_value', old)
    unit.queue_command('t_fan_speed', 'HIGH')
    values = []
    while not unit.commands_queue.empty():
      command = unit.commands_queue.get_nowait()
      values.append(command.command['properties'][0]['property']['value'])
      command.updater()
    self.assertEqual([control_value.get_temp(value) for value in values], [22, 22])
    self.assertIsNone(unit._pending_control)
    self.assertEqual(unit.get_property('t_temp'), 22)

  async def test_all_writable_properties_can_queue_with_packed_control(self):
    for field in ac().get_property_fields():
      if field.metadata['read_only']:
        continue
      unit = ac()
      with self.subTest(property=field.name):
        value = unit.get_property(field.name)
        unit.queue_command(field.name, 0 if value is None else value)
        self.assertFalse(unit.commands_queue.empty())

  async def test_turbo_and_swing_keep_all_queued_changes(self):
    unit = ac()
    unit.queue_command('t_temp_heatcold', 'ON')
    unit.queue_command('t_fan_power', 'ON')
    unit.queue_command('t_fan_leftright', 'ON')
    packed = unit._command_control()
    self.assertEqual(control_value.get_heat_cold(packed).name, 'ON')
    self.assertEqual(control_value.get_fan_mute(packed).name, 'OFF')
    self.assertEqual(control_value.get_fan_power(packed).name, 'ON')
    self.assertEqual(control_value.get_fan_lr(packed).name, 'ON')
    names = [c.command['properties'][0]['property']['name'] for c in (unit.commands_queue.get_nowait() for _ in range(unit.commands_queue.qsize()))]
    self.assertIn('t_temp_eight', names)

  async def test_home_assistant_temperature_conversion_boundaries(self):
    from types import SimpleNamespace
    from homeassistant.components.climate import async_service_temperature_set
    from homeassistant.core import ServiceCall
    from homeassistant.exceptions import ServiceValidationError
    from custom_components.hisense_aircon.climate import HisenseClimate
    for native, display, value, expected in [('F', '°C', 16, 61), ('F', '°C', 30, 86),
                                             ('C', '°F', 61, 16), ('C', '°F', 86, 30)]:
      unit = Device.create({**device(), 'temp_type': native}, lambda: None)
      climate = HisenseClimate(SimpleNamespace(), unit)
      climate.hass = SimpleNamespace(config=SimpleNamespace(units=SimpleNamespace(temperature_unit=display)))
      climate.async_write_ha_state = lambda: None
      await async_service_temperature_set(climate, ServiceCall(climate.hass, 'climate', 'set_temperature',
                                                               {'temperature': value}))
      queued = unit.commands_queue.get_nowait().command['properties'][0]['property']['value']
      self.assertEqual(queued, expected)
    with self.assertRaises(ServiceValidationError):
      await async_service_temperature_set(climate, ServiceCall(climate.hass, 'climate', 'set_temperature',
                                                               {'temperature': 40}))

  async def test_native_swing_services_change_only_the_requested_axis(self):
    from homeassistant.components.climate import ClimateEntityFeature
    from custom_components.hisense_aircon.climate import HisenseClimate
    from custom_components.hisense_aircon.properties import AirFlow
    unit = ac()
    climate = HisenseClimate(Mock(), unit)
    climate.async_write_ha_state = Mock()
    self.assertIn(ClimateEntityFeature.SWING_HORIZONTAL_MODE, climate.supported_features)
    for axis, other, service in [('t_fan_power', 't_fan_leftright', climate.async_handle_set_swing_mode_service),
                                 ('t_fan_leftright', 't_fan_power', climate.async_handle_set_swing_horizontal_mode_service)]:
      for value in ('on', 'off'):
        before = unit.get_property(other)
        await service(value)
        command = unit.commands_queue.get_nowait()
        command.updater()
        self.assertEqual(unit.get_property(axis), AirFlow[value.upper()])
        self.assertEqual(unit.get_property(other), before)
    unit = Device.create(device(), lambda: None)
    climate = HisenseClimate(Mock(), unit)
    unit.update_property('t_fan_leftright', AirFlow.ON)
    self.assertIsNone(climate.swing_mode)
    self.assertEqual(climate.swing_horizontal_mode, 'on')
    for model, vertical in [('AP-WA1E', True), ('AP-WB1E', False)]:
      climate = HisenseClimate(Mock(), Device.create({**device(), 'model': model}, lambda: None))
      self.assertEqual(ClimateEntityFeature.SWING_MODE in climate.supported_features, vertical)
      self.assertNotIn(ClimateEntityFeature.SWING_HORIZONTAL_MODE, climate.supported_features)

  async def test_turn_on_does_not_select_auto(self):
    from custom_components.hisense_aircon.climate import HisenseClimate
    for packed in (False, True):
      unit = ac() if packed else Device.create(device(), lambda: None)
      unit.update_property('t_work_mode', AcWorkMode.COOL)
      unit.update_property('t_power', Power.OFF)
      climate = HisenseClimate(Mock(), unit)
      climate.async_write_ha_state = Mock()
      await climate.async_turn_on()
      self.assertEqual(unit.commands_queue.qsize(), 1)
      command = unit.commands_queue.get_nowait()
      prop = command.command['properties'][0]['property']
      if packed:
        self.assertEqual(control_value.get_work_mode(prop['value']), AcWorkMode.COOL)
      else:
        self.assertEqual((prop['name'], prop['value']), ('t_power', 1))
      command.updater()
      self.assertEqual(unit.get_property('t_work_mode'), AcWorkMode.COOL)
    for model in ('AP-WA1E', 'AP-WB1E'):
      unit = Device.create({**device(), 'model': model}, lambda: None)
      climate = HisenseClimate(Mock(), unit)
      climate.async_write_ha_state = Mock()
      await climate.async_turn_on()
      prop = unit.commands_queue.get_nowait().command['properties'][0]['property']
      self.assertEqual((prop['name'], prop['value']), ('operation_mode', 1))

  async def test_crypto_matches_previous_library_across_messages_and_session_reset(self):
    from custom_components.hisense_aircon.config import Encryption
    # Golden vectors generated with pycryptodome 3.23.0 before removing that dependency.
    vectors = [
        (b'{"seq_no":0,"data":{}}',
         '454e3b81cbf7bb01064ff875db22f963c0abef82531eb80281ab3626a081fc65',
         '5eb8732561bcd9309fdefa97a829c25cdc97c17693573cd58163a5a3a2da243c'),
        (b'{"seq_no":1,"data":{"name":"t_temp","value":23}}',
         'c5d2f24eac87370234fb81a7527eaabc241f0ac7dd9020370fa8c9e1a69923555495d4648b948ad82cfb6b3ab3844a39',
         '480e81d97f3eb6b0c7ffbe3773eadf3841744b1e394ec9d9cd2ca05bd8cf6d67'),
        (b'{"seq_no":2,"data":{"name":"f_voltage","value":230}}',
         '6f368d5a66ca87d2d78242bdfce791f5b764d2693a7caeb3f9a724ff328515e5e2d450b65a20b4a0e0c0963d1cbac39963bcdaa4b5652cd09b874f342d63cf8e',
         'bf908144a84b315d33097fd15952ce291dd51a54acb12ffa321880f43c653b94'),
    ]
    for _ in range(2):
      encryption = Encryption(b'testkey', b'firstsecond100200')
      for text, encrypted, signature in vectors:
        padded = QueryHandlers.pad(text)
        self.assertEqual(encryption.encryptor.update(padded).hex(), encrypted)
        self.assertEqual(encryption.decryptor.update(bytes.fromhex(encrypted)), padded)
        self.assertEqual(Encryption.hmac_digest(encryption.sign_key, text).hex(), signature)
    for size in (0, 1, 15, 16, 17, 32):
      text = b'x' * size
      self.assertEqual(QueryHandlers.unpad(QueryHandlers.pad(text)), text)
      self.assertEqual(len(QueryHandlers.pad(text)) % 16, 0)

  async def test_command_fifo_does_not_depend_on_clock_and_keeps_user_priority(self):
    unit = Device.create(device(), lambda: None)
    unit.queue_status()
    with patch('time.time_ns', return_value=1):
      for value in range(20):
        unit.queue_command('t_temp', value)
    for value in range(20):
      command = unit.commands_queue.get_nowait()
      self.assertEqual(command.priority, 10)
      self.assertEqual(command.command['properties'][0]['property']['value'], value)
    self.assertEqual(unit.commands_queue.get_nowait().priority, 100)
