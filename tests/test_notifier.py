"""Availability and notifier lifecycle regression checks."""

import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch
from custom_components.hisense_aircon.notifier import Notifier
from custom_components.hisense_aircon.aircon import Device
from test_config_flow import device


class NotifierTests(unittest.IsolatedAsyncioTestCase):
  async def test_transient_failure_offline_and_recovery(self):
    notifier = Notifier(8123, '192.0.2.100')
    unit = Device.create(device(), lambda: None)
    notifier.register_device(unit)
    unit.available = True
    config = notifier._configurations[0]
    response = Mock(status=500, text=AsyncMock(return_value='error'))
    session = Mock(request=Mock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=response))))
    for index in range(3):
      with patch('custom_components.hisense_aircon.notifier.time.monotonic', return_value=100 + index * 20):
        await notifier._perform_request(session, config)
      self.assertEqual(unit.available, index < 2)
      self.assertEqual(session.request.call_args.args[0], 'PUT' if index == 0 else 'POST')
    response.status = 202
    with patch('custom_components.hisense_aircon.notifier.time.monotonic', return_value=200):
      await notifier._perform_request(session, config)
    self.assertTrue(unit.available)
    self.assertEqual(config.failures, 0)

  async def test_device_payloads_and_stop_with_pending_commands(self):
    notifier = Notifier(8123, '192.0.2.100')
    units = [Device.create(device(ip=f'192.0.2.{i}'), lambda: None) for i in (1, 2)]
    for unit in units:
      notifier.register_device(unit)
    units[0].queue_status()
    response = Mock(status=202)
    session = Mock(request=Mock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=response))))
    await asyncio.gather(*(notifier._perform_request(session, conf) for conf in notifier._configurations))
    payloads = [call.kwargs['json'] for call in session.request.call_args_list]
    self.assertEqual([p['local_reg']['notify'] for p in payloads], [1, 0])
    with patch.object(notifier, '_perform_request', AsyncMock(return_value=50)):
      task = asyncio.create_task(notifier.start(session))
      await asyncio.sleep(0)
      await asyncio.wait_for(notifier.stop(), timeout=0.5)
      await asyncio.wait_for(task, timeout=0.5)
