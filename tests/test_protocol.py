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
    request = Mock(remote=unit.ip_address, text=AsyncMock(return_value='{}'))
    for index, name in enumerate(('version', 't_swing_direction', 't_temp')):
      update = {'seq_no': index, 'data': {'name': name, 'value': 23}}
      with patch.object(handlers, '_decrypt_and_validate', return_value=update):
        response = await handlers.property_update_handler(request)
      self.assertEqual(response.status, 200)
    self.assertEqual(unit.get_property('t_temp'), 23)
