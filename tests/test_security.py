"""Exercise real aiohttp request limits and encrypted message validation."""

import base64
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from custom_components.hisense_aircon.aircon import Device
from custom_components.hisense_aircon.config import Encryption
from custom_components.hisense_aircon.query_handlers import QueryHandlers
from custom_components.hisense_aircon.diagnostics import async_get_config_entry_diagnostics
from custom_components.hisense_aircon import discovery
from test_config_flow import device


class SecurityTests(unittest.IsolatedAsyncioTestCase):
  async def asyncSetUp(self):
    self.unit = Device.create(device(ip='127.0.0.1'), lambda: None)
    self.handlers = QueryHandlers([self.unit])
    app = web.Application()
    app.router.add_post('/key', self.handlers.key_exchange_handler)
    app.router.add_post('/update', self.handlers.property_update_handler)
    self.client = TestClient(TestServer(app))
    await self.client.start_server()

  async def asyncTearDown(self):
    await self.client.close()

  async def test_body_limit_applies_with_and_without_content_length(self):
    for chunked in (False, True):
      response = await self.client.post('/key', data='x' * 70000, **({'chunked': True} if chunked else {}))
      self.assertEqual(response.status, 413, (chunked, (await response.text())[:120]))
    for body in ('[1]', '{', '{}'):
      response = await self.client.post('/key', data=body)
      self.assertEqual(response.status, 400)

  async def test_invalid_envelopes_and_valid_packet(self):
    for envelope in ({}, {'enc': '!', 'sign': ''}, {'enc': 'AA==', 'sign': ''}):
      response = await self.client.post('/update', json=envelope)
      self.assertEqual(response.status, 400)
    text = json.dumps({'seq_no': 1, 'data': {'name': 'f_voltage', 'value': 230}}).encode()
    enc = self.unit.get_dev_encryption()
    sender = Cipher(algorithms.AES(enc.crypto_key), modes.CBC(enc.iv_seed)).encryptor()
    envelope = {'enc': base64.b64encode(sender.update(self.handlers.pad(text))).decode(),
                'sign': base64.b64encode(Encryption.hmac_digest(enc.sign_key, text)).decode()}
    response = await self.client.post('/update', json=envelope)
    self.assertEqual(response.status, 200)
    self.assertEqual(self.unit.get_reported_property('f_voltage'), 230)
    text = b'{"secret":"must-not-appear-in-logs"}'
    envelope = {'enc': base64.b64encode(sender.update(self.handlers.pad(text))).decode(),
                'sign': base64.b64encode(b'0' * 32).decode()}
    with self.assertLogs('custom_components.hisense_aircon.query_handlers', level='WARNING') as logs:
      response = await self.client.post('/update', json=envelope)
    self.assertEqual(response.status, 400)
    self.assertNotIn('must-not-appear-in-logs', str(logs.output))

  async def test_cloud_tls_and_redacted_diagnostics(self):
    with patch.object(discovery, '_sign_in', AsyncMock(return_value='token')) as login, patch.object(
        discovery, '_get_devices', AsyncMock(return_value=[])):
      await discovery.perform_discovery(Mock(), 'hisense-eu', 'user', 'password')
    self.assertEqual(len(login.call_args.args), 6)
    self.assertNotIn("ssl_context", login.call_args.kwargs)
    self.unit.update_property('f_voltage', 230)
    entry = SimpleNamespace(entry_id='test', runtime_data=SimpleNamespace(devices=[self.unit]))
    hass = SimpleNamespace()
    payload = json.dumps(await async_get_config_entry_diagnostics(hass, entry))
    for secret in ('lanip_key', 'testkey', 'mac_address', '001122334455', '127.0.0.1', 'test-dsn'):
      self.assertNotIn(secret, payload)

  async def test_empty_updates_remain_accepted(self):
    for seq, data in enumerate((None, '', {}, {'name': 'version', 'value': 'test'}), 1):
      with patch.object(self.handlers, '_decrypt_and_validate', return_value={'seq_no': seq, 'data': data}):
        response = await self.client.post('/update', json={})
      self.assertEqual(response.status, 200)
    with patch.object(self.handlers, '_decrypt_and_validate', return_value={'seq_no': 5, 'data': 'bad'}):
      response = await self.client.post('/update', json={})
    self.assertEqual(response.status, 400)

  async def test_cloud_requests_preserve_session_tls_and_bound_waits(self):
    from custom_components.hisense_aircon.error import InvalidAuth
    response = Mock(status=200, text=AsyncMock(return_value='{"access_token":"token"}'))
    request = Mock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=response)))
    session = Mock(request=request, get=request)
    self.assertEqual(await discovery._sign_in('u', 'p', 'example.invalid', 'app', 'secret', session), 'token')
    response.text.return_value = '[]'
    self.assertEqual(await discovery._get_devices('example.invalid', {}, session), [])
    response.text.return_value = '{"lanip":{}}'
    await discovery._get_lanip('example.invalid', 'dsn', {}, session)
    for call in request.call_args_list:
      self.assertNotIn('ssl', call.kwargs)
      self.assertEqual(call.kwargs['timeout'].total, 15)
    for status in (401, 403):
      response.status = status
      with self.assertRaises(InvalidAuth):
        await discovery._sign_in('u', 'p', 'example.invalid', 'app', 'secret', session)
