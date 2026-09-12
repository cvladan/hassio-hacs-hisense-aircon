"""Initial state and model compatibility checks."""

from types import SimpleNamespace
import unittest
from custom_components.hisense_aircon.aircon import Device
from custom_components.hisense_aircon.climate import HisenseClimate, HVACMode
from custom_components.hisense_aircon.entity import HisensePropertyEntity
from custom_components.hisense_aircon.properties import FglOperationMode
from test_config_flow import device


class EntityTests(unittest.TestCase):
  def test_defaults_are_not_measurements_and_equal_first_report_is_visible(self):
    for model in ('AEH-W4E1', 'AP-WA1E', 'AP-WB1E', '0001-0401-0001'):
      unit = Device.create({**device(), 'model': model}, lambda: None)
      controller = SimpleNamespace(entry=SimpleNamespace(entry_id='test'))
      for field in unit.get_property_fields():
        entity = HisensePropertyEntity(controller, unit, field)
        self.assertIsNone(entity.native_value, (model, field.name))
      if model == 'AEH-W4E1':
        self.assertIsNone(HisenseClimate(controller, unit).target_temperature)
        unit.update_property('f_electricity', 100)
        self.assertEqual(unit.get_reported_property('f_electricity'), 100)
        unit.update_property('f_voltage', 0)
        self.assertEqual(unit.get_reported_property('f_voltage'), 0)
        unit.queue_command('t_temp', 23)
        self.assertIsNone(unit.get_reported_property('t_temp'))
        unit.commands_queue.get_nowait().updater()
        self.assertIsNone(unit.get_reported_property('t_temp'))
        self.assertEqual(unit.get_known_property('t_temp'), 23)

  def test_fujitsu_mode_does_not_require_hisense_power_property(self):
    for model in ('AP-WA1E', 'AP-WB1E'):
      unit = Device.create({**device(), 'model': model}, lambda: None)
      climate = HisenseClimate(SimpleNamespace(), unit)
      self.assertIsNone(climate.hvac_mode)
      unit.update_property('operation_mode', FglOperationMode.COOL)
      self.assertEqual(climate.hvac_mode, HVACMode.COOL)
      unit.queue_command('adjust_temperature', 22.5)
      command = unit.commands_queue.get_nowait()
      self.assertEqual(command.command['properties'][0]['property']['value'], 225)
      command.updater()
      self.assertEqual(climate.target_temperature, 22.5)

  def test_only_actual_climate_duplicates_are_removed(self):
    from custom_components.hisense_aircon.entity import primary_managed_properties, property_fields
    unit = Device.create(device(), lambda: None)
    removed = primary_managed_properties(unit)
    self.assertEqual(removed, {'t_power', 't_work_mode', 't_temp', 't_fan_speed',
                               't_fan_power', 't_fan_leftright'})
    remaining = {field.name for field in property_fields(unit)}
    self.assertTrue({'t_temptype', 't_sleep', 't_swing_angle', 't_run_mode'} <= remaining)
    fgl = Device.create({**device(), 'model': 'AP-WA1E'}, lambda: None)
    self.assertNotIn('af_horizontal_swing', primary_managed_properties(fgl))
    humidifier = Device.create({**device(), 'model': '0001-0401-0001'}, lambda: None)
    self.assertEqual(primary_managed_properties(humidifier), {'switch', 'humi', 'workmode'})

  def test_unchanged_reports_notify_once_but_first_actual_report_is_kept(self):
    from unittest.mock import Mock
    from custom_components.hisense_aircon.properties import FanSpeed
    from custom_components.hisense_aircon import control_value
    unit = Device.create(device(), lambda: None)
    listener = Mock()
    unit.add_property_change_listener(listener)
    unit.update_property('f_electricity', 100)
    unit.update_property('f_electricity', 100)
    self.assertEqual(listener.call_count, 1)
    listener.reset_mock()
    unit.update_property('t_temp', 23, reported=False)
    unit.update_property('t_temp', 23)
    unit.update_property('t_temp', 23)
    self.assertEqual(listener.call_count, 2)
    self.assertEqual(unit.get_reported_property('t_temp'), 23)
    listener.reset_mock()
    unit.update_property('t_fan_speed', None)
    unit.update_property('t_fan_speed', None)
    unit.update_property('t_fan_speed', FanSpeed.AUTO)
    self.assertEqual(listener.call_count, 2)
    packed = control_value.set_temp(0, 24)
    unit.update_property('t_control_value', packed)
    unit.update_property('t_temp', 22)
    unit.update_property('t_control_value', packed)
    self.assertEqual(unit.get_reported_property('t_temp'), 24)
