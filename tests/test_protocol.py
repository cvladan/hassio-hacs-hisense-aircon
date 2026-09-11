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
    from dataclasses import fields
    for field in fields(ac().get_all_properties()):
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
    names = [c.command['properties'][0]['property']['name'] for c in unit.commands_queue.queue]
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
