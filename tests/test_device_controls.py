"""Manual actions, optional diagnostics, and native humidifier controls."""

import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity import EntityCategory

from custom_components.hisense_aircon.aircon import Device
from custom_components.hisense_aircon.button import HisenseButton
from custom_components.hisense_aircon.diagnostics import async_get_config_entry_diagnostics
from custom_components.hisense_aircon.humidifier import HisenseHumidifier
from custom_components.hisense_aircon.query_handlers import QueryHandlers
from custom_components.hisense_aircon.sensor import HisenseDiagnosticSensor
from test_config_flow import device


class DeviceControlTests(unittest.IsolatedAsyncioTestCase):
  async def test_refresh_is_deduplicated_and_reconnect_targets_only_one_device(self):
    unit = Device.create(device(), lambda: None)
    controller = Mock()
    refresh = HisenseButton(controller, unit, 'refresh')
    reconnect = HisenseButton(controller, unit, 'reconnect')
    self.assertFalse(unit.available)
    self.assertTrue(refresh.available)
    self.assertTrue(reconnect.available)
    unit.queue_command('t_temp', 23)
    await refresh.async_press()
    size = unit.commands_queue.qsize()
    await refresh.async_press()
    self.assertEqual(unit.commands_queue.qsize(), size)
    await reconnect.async_press()
    controller.reconnect_device.assert_called_once_with(unit)
    self.assertEqual(unit.commands_queue.qsize(), size)
    self.assertEqual(unit.commands_queue.get_nowait().priority, 10)

  async def test_diagnostics_track_valid_messages_and_remain_visible_offline(self):
    unit = Device.create(device(), lambda: None)
    sensors = {key: HisenseDiagnosticSensor(Mock(), unit, key)
               for key in ('last_message', 'last_registration', 'failures', 'queued_commands')}
    for sensor in sensors.values():
      self.assertTrue(sensor.available)
      self.assertFalse(sensor.entity_registry_enabled_default)
      self.assertEqual(sensor.entity_category, EntityCategory.DIAGNOSTIC)
    self.assertIsNone(sensors['last_message'].native_value)
    self.assertIsNone(sensors['last_registration'].native_value)
    handlers = QueryHandlers([unit])
    request = Mock(remote=unit.ip_address)
    request.clone.return_value.json = AsyncMock(return_value={})
    with patch.object(handlers, '_decrypt_and_validate', return_value={'seq_no': 5, 'data': {}}):
      await handlers.property_update_handler(request)
    last_message = sensors['last_message'].native_value
    self.assertIsNotNone(last_message.tzinfo)
    with patch.object(handlers, '_decrypt_and_validate', return_value={'seq_no': 4, 'data': {}}):
      await handlers.property_update_handler(request)
    self.assertEqual(sensors['last_message'].native_value, last_message)
    # No real encrypted envelope: must not advance the timestamp.
    self.assertEqual((await handlers.property_update_handler(request)).status, 400)
    self.assertEqual(sensors['last_message'].native_value, last_message)
    self.assertIsNone(sensors['last_registration'].native_value)
    unit.queue_command('t_temp', 23)
    self.assertEqual(sensors['queued_commands'].native_value, 1)
    await handlers.command_handler(request)
    self.assertEqual(sensors['queued_commands'].native_value, 0)
    unit.update_diagnostics(failures=3)
    self.assertEqual(sensors['failures'].native_value, 3)
    entry = SimpleNamespace(runtime_data=SimpleNamespace(devices=[unit]))
    export = await async_get_config_entry_diagnostics(None, entry)
    self.assertEqual(export['devices'][0]['last_message'], last_message.isoformat())
    serialized = json.dumps(export)
    for secret in ('testkey', unit.mac_address, unit.ip_address, 'test-dsn'):
      self.assertNotIn(secret, serialized)

  async def test_native_humidifier_state_commands_and_validation(self):
    for model in ('0001-0401-0001', '0001-0401-0002'):
      unit = Device.create({**device(), 'model': model}, lambda: None)
      entity = HisenseHumidifier(Mock(), unit)
      self.assertIsNone(entity.is_on)
      self.assertIsNone(entity.current_humidity)
      self.assertIsNone(entity.target_humidity)
      self.assertIsNone(entity.mode)
      unit.update_property('realhumi', 45)
      self.assertEqual(entity.current_humidity, 45)
      for method, args, name, expected in (
          (entity.async_turn_on, (), 'switch', 1),
          (entity.async_set_humidity, (55,), 'humi', 55),
          (entity.async_set_mode, ('nightlight',), 'workmode', 1),
          (entity.async_turn_off, (), 'switch', 0),
          (entity.async_set_mode, ('sleep',), 'workmode', 2),
          (entity.async_set_mode, ('normal',), 'workmode', 0),
      ):
        await method(*args)
        command = unit.commands_queue.get_nowait()
        prop = command.command['properties'][0]['property']
        self.assertEqual((prop['name'], prop['value']), (name, expected))
        command.updater()
      self.assertFalse(entity.is_on)
      self.assertEqual(entity.target_humidity, 55)
      self.assertEqual(entity.mode, 'normal')
      for invalid in (29, 100, 40.5, True, float('nan')):
        with self.assertRaises(ServiceValidationError):
          await entity.async_set_humidity(invalid)
      with self.assertRaises(ServiceValidationError):
        await entity.async_set_mode('unknown')
      self.assertTrue(unit.commands_queue.empty())
