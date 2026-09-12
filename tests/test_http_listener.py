"""Exercise callback listeners, isolation, HTTPS coexistence, and cleanup."""

import asyncio
import base64
import json
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from aiohttp import ClientSession, TCPConnector, web
from aiohttp.test_utils import TestServer
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady

from custom_components.hisense_aircon.config import Encryption
from custom_components.hisense_aircon.controller import (
    HisenseCommandsView, HisenseController, callback_error,
)
from test_config_flow import device


def free_port():
  with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    return sock.getsockname()[1]


class HTTPListenerTests(unittest.IsolatedAsyncioTestCase):
  async def asyncSetUp(self):
    self.controllers = []
    self.hass = SimpleNamespace(
        loop=asyncio.get_running_loop(), data={},
        http=SimpleNamespace(ssl_certificate='test-cert', server_port=8123, register_view=Mock()),
        config_entries=SimpleNamespace(async_entries=lambda domain: [c.entry for c in self.controllers]))
    for name in ('async_get_clientsession', 'async_get_source_ip'):
      self.enterContext(patch('custom_components.hisense_aircon.controller.' + name,
                             AsyncMock(return_value='127.0.0.1') if name.endswith('source_ip') else Mock()))

  async def asyncTearDown(self):
    for controller in self.controllers:
      await controller.async_stop()

  def controller(self, devices=None, port=None, **options):
    entry = SimpleNamespace(
        entry_id=str(len(self.controllers)), data={'devices': devices or [device(ip='127.0.0.1')]},
        options={'separate_http_port': free_port() if port is None else port, **options},
        async_create_background_task=lambda hass, coro, name: asyncio.create_task(coro, name=name))
    controller = HisenseController(self.hass, entry)
    entry.runtime_data = controller
    controller._notifier.start = AsyncMock()
    controller._query_status_device = AsyncMock()
    controller._handle_property_update = Mock()
    self.controllers.append(controller)
    return controller

  async def test_https_server_and_plain_listener_with_real_protocol(self):
    with tempfile.TemporaryDirectory() as directory:
      cert, key = [str(Path(directory) / name) for name in ('cert.pem', 'key.pem')]
      await asyncio.to_thread(subprocess.run, ['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                      '-keyout', key, '-out', cert, '-days', '1', '-subj', '/CN=localhost'],
                     check=True, capture_output=True)
      context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
      context.load_cert_chain(cert, key)
      https = TestServer(web.Application(), scheme='https')
      await https.start_server(ssl=context)
      self.addAsyncCleanup(https.close)
      self.hass.http.ssl_certificate = cert
      self.hass.http.server_port = https.port
      config = {**device(ip='127.0.0.1'), 'model': 'AP-WA1E'}
      controller = self.controller([config])
      await controller.async_start()
      self.hass.http.register_view.assert_not_called()
      unit = controller.devices[0]
      port = controller.entry.options['separate_http_port']
      self.assertEqual(controller._notifier._json['local_reg']['port'], port)
      url = f'http://127.0.0.1:{port}/local_lan'
      async with ClientSession() as client:
        # A live TLS server remains separate from the plain device protocol.
        response = await client.get(https.make_url('/'), ssl=False)
        self.assertEqual(response.status, 404)
        response = await client.post(url + '/key_exchange.json', json={'key_exchange': {
            'ver': 1, 'proto': 1, 'key_id': 1, 'random_1': 'test-device', 'time_1': 123}})
        self.assertEqual(response.status, 200)
        self.assertIn('random_2', await response.json())
        unit.queue_status()
        queued = unit.commands_queue.qsize()
        response = await client.get(url + '/commands.json')
        self.assertEqual(response.status, 200)
        command = await response.json()
        enc = unit.get_app_encryption()
        plain = Cipher(algorithms.AES(enc.crypto_key), modes.CBC(enc.iv_seed)).decryptor().update(base64.b64decode(command['enc']))
        self.assertIn('cmds', json.loads(plain.rstrip(b'\0'))['data'])
        self.assertEqual(unit.commands_queue.qsize(), queued - 1)
        enc = unit.get_dev_encryption()
        sender = Cipher(algorithms.AES(enc.crypto_key), modes.CBC(enc.iv_seed)).encryptor()
        paths = ('property/datapoint.json', 'property/datapoint/ack.json',
                 'node/property/datapoint.json', 'node/property/datapoint/ack.json')
        for seq, path in enumerate(paths, 1):
          text = json.dumps({'seq_no': seq, 'data': {'name': 'display_temperature', 'value': 200 + seq}}).encode()
          envelope = {
              'enc': base64.b64encode(sender.update(controller.handlers.pad(text))).decode(),
              'sign': base64.b64encode(Encryption.hmac_digest(enc.sign_key, text)).decode()}
          response = await client.post(url + '/' + path, json=envelope)
          self.assertEqual(response.status, 200)
        self.assertIsNotNone(unit.get_reported_property('display_temperature'))
        for chunked in (False, True):
          response = await client.post(url + '/key_exchange.json', data='x' * 70000,
                                       **({'chunked': True} if chunked else {}))
          self.assertEqual(response.status, 413)
        response = await client.post(url + '/property/datapoint.json', json={'enc': '!', 'sign': ''})
        self.assertEqual(response.status, 400)
        response = await client.get(f'http://127.0.0.1:{port}/api/states')
        self.assertEqual(response.status, 404)
      await controller.async_stop()
      self.assertIsNone(controller._http_runner)
      replacement = self.controller([config], port=port)
      await replacement.async_start()
      self.assertEqual(self.hass.http.ssl_certificate, cert)

  async def test_failed_setup_and_port_conflict_leave_other_entry_running(self):
    first = self.controller()
    await first.async_start()
    port = first.entry.options['separate_http_port']
    second = self.controller([device('aabbccddeeff', '192.0.2.2')], port=port)
    with self.assertRaises(ConfigEntryNotReady):
      await second.async_start()
    self.assertIsNone(second._http_runner)
    self.assertFalse(second._tasks)
    await second.async_stop()
    async with ClientSession() as client:
      self.assertEqual((await client.get(f'http://127.0.0.1:{port}/local_lan/commands.json')).status, 200)
    # Cleanup after setup fails *after* the socket has been opened.
    third = self.controller()
    third_port = third.entry.options['separate_http_port']
    with patch('custom_components.hisense_aircon.controller.async_get_source_ip',
               AsyncMock(side_effect=OSError('no route'))):
      with self.assertRaises(ConfigEntryNotReady):
        await third.async_start()
    await third.async_stop()
    await self.controller(port=third_port).async_start()

  async def test_unconfigured_source_is_rejected_and_ip_change_rebuilds_routes(self):
    controller = self.controller([device(ip='192.0.2.1')])
    await controller.async_start()
    port = controller.entry.options['separate_http_port']
    url = f'http://127.0.0.1:{port}/local_lan'
    async with ClientSession() as client:
      for method, path in (('GET', '/commands.json'), ('POST', '/key_exchange.json'),
                           ('POST', '/property/datapoint.json')):
        response = await client.request(method, url + path, json={},
                                        headers={'X-Forwarded-For': '192.0.2.1'})
        self.assertEqual(response.status, 404)
      await controller.async_stop()
      controller.entry.data['devices'][0]['ip_address'] = '127.0.0.1'
      updated = self.controller(controller.entry.data['devices'], port=port)
      await updated.async_start()
      response = await client.get(url + '/commands.json')
      self.assertEqual(response.status, 200)
      self.assertEqual(updated.handlers.device_ips, {'127.0.0.1'})

  async def test_entry_setup_cancellation_and_platform_failure_close_listener(self):
    from custom_components.hisense_aircon import async_setup_entry
    for failure in (asyncio.CancelledError(), RuntimeError('platform failure')):
      controller = self.controller()
      port = controller.entry.options['separate_http_port']
      with patch('custom_components.hisense_aircon.HisenseController', return_value=controller), patch.object(
          self.hass.config_entries, 'async_forward_entry_setups', AsyncMock(side_effect=failure), create=True), patch.object(
              self.hass.config_entries, 'async_unload_platforms', AsyncMock(return_value=True), create=True):
        with self.assertRaises(type(failure)):
          await async_setup_entry(self.hass, controller.entry)
      self.assertIsNone(controller._http_runner)
      self.assertFalse(controller._tasks)
      self.assertFalse(controller.devices[0]._property_change_listeners)
      self.assertFalse(hasattr(controller.entry, 'runtime_data'))
      replacement = self.controller(port=port)
      await replacement.async_start()

  async def test_multiple_devices_and_mixed_entries_stay_isolated(self):
    # Linux accepts all 127/8 source addresses; macOS requires explicit aliases.
    with socket.socket() as sock:
      try:
        sock.bind(('127.0.0.2', 0))
      except OSError:
        self.skipTest('Multiple loopback source addresses are unavailable; exercised by Linux CI')
    first = self.controller([device(ip='127.0.0.1'), device('aabbccddeeff', '127.0.0.2')])
    second = self.controller([device('112233445566', '127.0.0.3')])
    shared = self.controller([device('223344556677', '127.0.0.4')], port=0, callback_port=8125)
    for controller in (first, second, shared):
      await controller.async_start()
      for unit in controller.devices:
        unit.queue_status()
    self.assertIsNone(shared._http_runner)
    self.assertEqual(self.hass.http.register_view.call_count, 8)
    # Exercise the existing HA view alongside both dedicated listeners.
    app = web.Application()
    app['hass'] = self.hass
    app.router.add_get('/local_lan/commands.json', HisenseCommandsView().get)
    server = TestServer(app)
    await server.start_server()
    self.addAsyncCleanup(server.close)
    for controller in (first, second, shared):
      port = controller.entry.options['separate_http_port'] or server.port
      for unit in controller.devices:
        sizes = [d.commands_queue.qsize() for c in self.controllers for d in c.devices]
        async with ClientSession(connector=TCPConnector(local_addr=(unit.ip_address, 0))) as client:
          response = await client.get(f'http://127.0.0.1:{port}/local_lan/commands.json')
          self.assertEqual(response.status, 200)
          self.assertIn('enc', await response.json())
        current = [d.commands_queue.qsize() for c in self.controllers for d in c.devices]
        self.assertEqual(sum(sizes) - sum(current), 1)
        devices = [d for c in self.controllers for d in c.devices]
        self.assertEqual(unit.commands_queue.qsize(), sizes[devices.index(unit)] - 1)
    async with ClientSession(connector=TCPConnector(local_addr=('127.0.0.3', 0))) as client:
      url = f'http://127.0.0.1:{first.entry.options["separate_http_port"]}/local_lan/commands.json'
      self.assertEqual((await client.get(url)).status, 404)
    await first.async_stop()
    async with ClientSession(connector=TCPConnector(local_addr=('127.0.0.3', 0))) as client:
      url = f'http://127.0.0.1:{second.entry.options["separate_http_port"]}/local_lan/commands.json'
      self.assertEqual((await client.get(url)).status, 200)

  async def test_https_detection_and_existing_http_or_proxy_settings(self):
    self.assertEqual(callback_error(self.hass, {}), 'https_callback')
    self.assertEqual(callback_error(self.hass, {'local_ip': '  '}), 'https_callback')
    self.assertEqual(callback_error(self.hass, {'separate_http_port': 8123}), 'listener_port_conflict')
    for settings in ({'separate_http_port': 8124}, {'callback_port': 8124}, {'local_ip': '192.0.2.10'}):
      self.assertIsNone(callback_error(self.hass, settings))
    controller = self.controller(port=0)
    with self.assertRaises(ConfigEntryError):
      await controller.async_start()
    self.assertFalse(controller._tasks)
    self.hass.http.ssl_certificate = None
    self.assertIsNone(callback_error(self.hass, {}))
    await controller.async_start()
    self.assertIsNone(controller._http_runner)
    self.hass.http.register_view.assert_called()
