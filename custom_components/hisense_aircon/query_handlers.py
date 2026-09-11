from aiohttp import web
import base64
import binascii
import hmac
from Crypto.Cipher import AES
from http import HTTPStatus
import json
import math
import logging
import queue
import random
import string
import time
from typing import Callable

from .config import Config, Encryption
from .aircon import Device
from .error import Error, KeyIdReplaced

_LOGGER = logging.getLogger(__name__)


class QueryHandlers:

  _MAX_REQUEST_BODY = 64 * 1024

  def __init__(self, devices: [Device]):
    self._devices_map = {}
    for device in devices:
      self._devices_map[device.ip_address] = device

  @property
  def device_ips(self) -> set[str]:
    return set(self._devices_map)

  def _device_for_remote(self, request: web.Request) -> Device:
    device = self._devices_map.get(request.remote)
    if device is None:
      raise web.HTTPNotFound(
          reason=f'No configured Hisense device matches request source {request.remote!r}.')
    return device

  async def key_exchange_handler(self, request: web.Request) -> web.Response:
    """Handles a key exchange.
    Accepts the AC's random and time and pass its own.
    Note that a key encryption component is the lanip_key, mapped to the
    lanip_key_id provided by the AC. This secret part is provided by HiSense
    server. Fortunately the lanip_key_id (and lanip_key) are static for a given
    AC.
    """
    device = self._device_for_remote(request)
    data = await self._read_json(request)
    key = data.get('key_exchange')
    if (not isinstance(key, dict) or key.get('ver') != 1 or key.get('proto') != 1
        or key.get('sec') or not isinstance(key.get('random_1'), str)
        or type(key.get('time_1')) is not int or type(key.get('key_id')) is not int):
      raise web.HTTPBadRequest(reason='Invalid key exchange payload.')
    try:
      updated_keys = device.update_key(key)
    except KeyIdReplaced:
      _LOGGER.warning('Device LAN key ID changed; rediscover the device.')
      raise web.HTTPNotFound(reason='Device LAN key ID changed.') from None
    return web.json_response(updated_keys)

  async def command_handler(self, request: web.Request) -> web.Response:
    """Handles a command request.
    Request arrives from the AC. takes a command from the queue,
    builds the JSON, encrypts and signs it, and sends it to the AC.
    """
    command = {}
    device = self._device_for_remote(request)
    command['seq_no'] = device.get_command_seq_no()
    try:
      command_entry = device.commands_queue.get_nowait()
      command['data'], property_updater = command_entry.command, command_entry.updater
    except queue.Empty:
      command['data'], property_updater = {}, None
    if property_updater:
      property_updater()  #TODO: should be async as well?
    return web.json_response(self._encrypt_and_sign(device, command))

  async def property_update_handler(self, request: web.Request) -> web.Response:
    """Handles a property update request.
    Decrypts, validates, and pushes the value into the local properties store.
    """
    device = self._device_for_remote(request)
    data = await self._read_json(request)
    try:
      update = self._decrypt_and_validate(device, data)
    except Error as ex:
      _LOGGER.warning('Rejected device update: %s', ex)
      return web.Response(status=HTTPStatus.BAD_REQUEST.value, reason='Failed to parse property.')
    response = web.Response()
    if (not isinstance(update, dict) or type(update.get('seq_no')) is not int
        or not isinstance(update.get('data'), dict)):
      raise web.HTTPBadRequest(reason='Invalid device update payload.')
    if not device.is_update_valid(update['seq_no']):
      return response
    try:
      if not update['data']:
        _LOGGER.info('Unsupported update message = {}'.format(update['seq_no']))
        return response
      name = update['data']['name']
      # Fix A/C typos.
      if name == 'f_votage':
        name = 'f_voltage'
      if device.get_property_type(name) is None:
        _LOGGER.debug('Ignoring unsupported device property %s', name)
        return response
      value = device.parse_property(name, update['data']['value'])
      device.update_property(name, value)
    except Exception as ex:
      _LOGGER.warning('Invalid device property update (%s)', type(ex).__name__)
      #TODO: Should return internal error?
    return response

  async def get_status_handler(self, request: web.Request) -> web.Response:
    """Handles get status request (by a smart home hub).
    Returns the current internally stored state of the AC.
    """
    devices = []
    for device in self._devices_map.values():
      if 'device_ip' in request.query.keys() and device.ip_address != request.query['device_ip']:
        continue
      devices.append({'ip': device.ip_address, 'props': device.get_all_properties().to_dict()})
    return web.json_response({'devices': devices})

  async def queue_command_handler(self, request: web.Request) -> web.Response:
    """Handles queue command request (by a smart home hub).
    """
    device = self._devices_map.get(request.query.get('device_ip'))
    if not device:
      if len(self._devices_map) == 1:
        device = list(self._devices_map.values())[0]
      else:
        raise web.HTTPBadRequest(reason=f'Device "{request.query.get("device_ip")}" not found.')
    try:
      device.queue_command(request.query['property'], request.query['value'])
    except Exception as ex:
      _LOGGER.exception('Failed to queue command.')
      raise web.HTTPBadRequest(f'Failed to queue command:\n{ex!r}')
    return web.json_response({'queued_commands': device.commands_queue.qsize()})

  def _encrypt_and_sign(self, device: Device, data: dict) -> dict:
    text = json.dumps(data)
    _LOGGER.debug('Sending device command sequence %s', data.get('seq_no'))
    text = text.encode('utf-8')
    encryption = device.get_app_encryption()
    return {
        "enc": base64.b64encode(encryption.cipher.encrypt(self.pad(text))).decode('utf-8'),
        "sign": base64.b64encode(Encryption.hmac_digest(encryption.sign_key, text)).decode('utf-8')
    }

  async def _read_json(self, request: web.Request) -> dict:
    """Use aiohttp's body limit, including requests with chunked encoding."""
    try:
      data = await request.clone(client_max_size=self._MAX_REQUEST_BODY).json()
    except (ValueError, UnicodeDecodeError):
      raise web.HTTPBadRequest(reason='Invalid JSON payload.') from None
    if not isinstance(data, dict):
      raise web.HTTPBadRequest(reason='JSON payload must be an object.')
    return data

  def _decrypt_and_validate(self, device: Device, data: dict) -> dict:
    encryption = device.get_dev_encryption()
    try:
      encrypted = base64.b64decode(data['enc'], validate=True)
      signature = base64.b64decode(data['sign'], validate=True)
      if not encrypted or len(encrypted) % AES.block_size or len(signature) != 32:
        raise ValueError('Invalid encrypted envelope')
    except (KeyError, TypeError, ValueError, binascii.Error):
      raise Error('Invalid encrypted device payload.') from None
    text = self.unpad(encryption.cipher.decrypt(encrypted))
    if not hmac.compare_digest(Encryption.hmac_digest(encryption.sign_key, text), signature):
      raise Error('Invalid device message signature.')
    try:
      return json.loads(text)
    except (ValueError, UnicodeDecodeError):
      raise Error('Invalid decrypted JSON payload.') from None

  @staticmethod
  def pad(data: bytes):
    """Zero padding for AES data encryption (non standard)."""
    new_size = math.ceil(len(data) / AES.block_size) * AES.block_size
    return data.ljust(new_size, bytes([0]))

  @staticmethod
  def unpad(data: bytes):
    """Remove Zero padding for AES data encryption (non standard)."""
    return data.rstrip(bytes([0]))
