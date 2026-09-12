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

  async def test_registration_refresh_is_deduplicated_and_preserves_user_priority(self):
    from custom_components.hisense_aircon.query_handlers import QueryHandlers
    from types import SimpleNamespace
    notifier = Notifier(8123, '192.0.2.100')
    unit = Device.create(device(), lambda: None)
    notifier.register_device(unit)
    response = Mock(status=202)
    session = Mock(request=Mock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=response))))
    config = notifier._configurations[0]
    with patch('custom_components.hisense_aircon.notifier.time.monotonic', return_value=100):
      await notifier._perform_request(session, config)
    size = unit.commands_queue.qsize()
    self.assertGreater(size, 0)
    unit.queue_status()
    self.assertEqual(unit.commands_queue.qsize(), size)
    unit.queue_command('t_temp', 23)
    self.assertEqual(unit.commands_queue.get_nowait().priority, 10)
    handler = QueryHandlers([unit])
    await handler.command_handler(SimpleNamespace(remote=unit.ip_address))
    self.assertEqual(len(unit._pending_status), size - 1)
    # Reconnect while the earlier refresh is still queued; refill only the sent read.
    unit.available = False
    with patch('custom_components.hisense_aircon.notifier.time.monotonic', return_value=200):
      await notifier._perform_request(session, config)
    self.assertEqual(unit.commands_queue.qsize(), size)
    for _ in range(size):
      await handler.command_handler(SimpleNamespace(remote=unit.ip_address))
    self.assertFalse(unit._pending_status)
    with patch('custom_components.hisense_aircon.notifier.time.monotonic', return_value=220):
      await notifier._perform_request(session, config)
    self.assertEqual(session.request.call_args.args[0], 'PUT')
    self.assertEqual(unit.commands_queue.qsize(), 0)
    self.assertIsNone(unit.get_reported_property('t_temp'))

  async def test_slow_device_does_not_delay_healthy_device_and_cancellation_cleans_up(self):
    notifier = Notifier(8123, '192.0.2.100')
    for i in (1, 2):
      notifier.register_device(Device.create(device(mac=f'00000000000{i}', ip=f'192.0.2.{i}'), lambda: None))
    slow_started, slow_cancelled, healthy_repeated = [asyncio.Event() for _ in range(3)]
    calls = []

    class Request:
      def __init__(self, url):
        self.url = url

      async def __aenter__(self):
        if '192.0.2.2/' in self.url:
          slow_started.set()
          try:
            await asyncio.Event().wait()
          finally:
            slow_cancelled.set()
        calls.append(self.url)
        if len(calls) >= 2:
          healthy_repeated.set()
        return Mock(status=202)

      async def __aexit__(self, *args):
        pass

    session = Mock(request=lambda method, url, **kwargs: Request(url))
    task = asyncio.create_task(notifier.start(session))
    try:
      await asyncio.wait_for(slow_started.wait(), 1)
      await asyncio.wait_for(healthy_repeated.wait(), 1)
      self.assertFalse(slow_cancelled.is_set())
    finally:
      await notifier.stop()
      task.cancel()
      await asyncio.gather(task, return_exceptions=True)
    self.assertTrue(slow_cancelled.is_set())

  async def test_retry_deadlines_and_targeted_reconnect_preserve_queued_commands(self):
    notifier = Notifier(8123, '192.0.2.100')
    units = [Device.create(device(mac=f'00000000000{i}', ip=f'192.0.2.{i}'), lambda: None) for i in (1, 2)]
    for unit in units:
      notifier.register_device(unit)
    config = notifier._configurations[0]
    response = Mock(status=500)
    session = Mock(request=Mock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=response))))
    now = 100
    for delay in (2, 4, 8, 10, 10):
      with patch('custom_components.hisense_aircon.notifier.time.monotonic', return_value=now):
        await notifier._perform_request(session, config)
      self.assertEqual(config.next_attempt, now + delay)
      count = session.request.call_count
      with patch('custom_components.hisense_aircon.notifier.time.monotonic', return_value=now + delay - 0.1):
        await notifier._perform_request(session, config)
      self.assertEqual(session.request.call_count, count)
      now += delay
    units[0].queue_command('t_temp', 23)
    notifier.notify(units[0].mac_address, reconnect=True)
    self.assertTrue(config.notification.is_set())
    self.assertFalse(notifier._configurations[1].notification.is_set())
    response.status = 202
    with patch('custom_components.hisense_aircon.notifier.time.monotonic', return_value=now):
      await notifier._perform_request(session, config)
    self.assertEqual(session.request.call_args.args[0], 'POST')
    self.assertEqual(config.failures, 0)
    self.assertIsNotNone(units[0].diagnostics['last_registration'])
    self.assertEqual(units[0].commands_queue.get_nowait().command['properties'][0]['property']['value'], 23)
    self.assertTrue(units[1].commands_queue.empty())

  async def test_reconnect_requested_during_an_inflight_request_is_not_lost(self):
    notifier = Notifier(8123, '192.0.2.100')
    unit = Device.create(device(), lambda: None)
    unit.available = True
    notifier.register_device(unit)
    config = notifier._configurations[0]
    started, finish = asyncio.Event(), asyncio.Event()

    async def enter():
      started.set()
      await finish.wait()
      return Mock(status=202)

    session = Mock(request=Mock(return_value=AsyncMock(__aenter__=AsyncMock(side_effect=enter))))
    task = asyncio.create_task(notifier._perform_request(session, config))
    await asyncio.wait_for(started.wait(), 1)
    notifier.notify(unit.mac_address, reconnect=True)
    finish.set()
    await task
    self.assertTrue(config.reconnect)
    with patch('custom_components.hisense_aircon.notifier.time.monotonic', return_value=config.last_timestamp + 1):
      await notifier._perform_request(session, config)
    self.assertEqual(session.request.call_args.args[0], 'POST')
    self.assertFalse(config.reconnect)
