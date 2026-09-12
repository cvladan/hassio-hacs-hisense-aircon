import asyncio
import aiohttp
import base64
from getmac import get_mac_address
from http import HTTPStatus
import json
import logging

from .app_mappings import (
    AYLA_DEVICES_SERVERS,
    AYLA_USER_SERVERS,
    CELSIUS_BASED_APPS,
    SECRET_ID_EXTRA_MAP,
    SECRET_ID_MAP,
    SECRET_MAP,
)
from .error import Error, InvalidAuth

_LOGGER = logging.getLogger(__name__)

_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)

_USER_AGENT = 'Dalvik/2.1.0 (Linux; U; Android 9.0; SM-G850F Build/LRX22G)'


async def _sign_in(user: str, passwd: str, user_server: str, app_id: str, app_secret: str,
                   session: aiohttp.ClientSession):
  query = {
      'user': {
          'email': user,
          'password': passwd,
          'application': {
              'app_id': app_id,
              'app_secret': app_secret
          }
      }
  }
  headers = {
      'Accept': 'application/json',
      'Connection': 'Keep-Alive',
      'Authorization': 'none',
      'Content-Type': 'application/json',
      'User-Agent': _USER_AGENT,
      'Host': user_server,
      'Accept-Encoding': 'gzip'
  }
  _LOGGER.debug('Signing in to %s', user_server)
  async with session.request('POST',
                             f'https://{user_server}/users/sign_in.json',
                             json=query,
                             headers=headers,
                             timeout=_REQUEST_TIMEOUT) as resp:
    if resp.status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
      raise InvalidAuth('Cloud sign in was rejected.')
    if resp.status != HTTPStatus.OK.value:
      raise Error('Failed to login to Hisense server: '
                  f'Status {resp.status}: {resp.reason!r}')
    resp_data = await resp.text()
    try:
      tokens = json.loads(resp_data)
    except (ValueError, UnicodeDecodeError):
      _LOGGER.warning('Invalid login response from Hisense server')
      raise Error('Failed to parse login tokens from Hisense server.')
    return tokens['access_token']


async def _get_devices(devices_server: str, headers: dict,
                       session: aiohttp.ClientSession):
  _LOGGER.debug('Fetching account devices')
  async with session.get(f'https://{devices_server}/apiv1/devices.json',
                         headers=headers,
                         timeout=_REQUEST_TIMEOUT) as resp:
    if resp.status != HTTPStatus.OK.value:
      raise Error('Failed to get devices data from Hisense server: '
                  f'Status {resp.status}: {resp.reason!r}')
    resp_data = await resp.text()
    try:
      devices = json.loads(resp_data)
    except (ValueError, UnicodeDecodeError):
      _LOGGER.warning('Invalid devices response from Hisense server')
      raise Error('Failed to parse devices data from Hisense server.')
    return devices


async def _get_lanip(devices_server: str, dsn: str, headers: dict, session: aiohttp.ClientSession):
  _LOGGER.debug('Fetching device LAN configuration')
  async with session.get(f'https://{devices_server}/apiv1/dsns/{dsn}/lan.json',
                         headers=headers,
                         timeout=_REQUEST_TIMEOUT) as resp:
    if resp.status != HTTPStatus.OK.value:
      raise Error(f'Failed to get LAN data from Hisense server: {resp.status} {resp.reason!r}')
    resp_data = await resp.text()
    return json.loads(resp_data)['lanip']


async def perform_discovery(session: aiohttp.ClientSession,
                            app: str,
                            user: str,
                            passwd: str,
                            device_filter: str | None = None) -> list[dict]:
  if app in SECRET_ID_MAP:
    app_prefix = SECRET_ID_MAP[app]
  else:
    app_prefix = 'a-Hisense-{}-field'.format(app)

  if app in SECRET_ID_EXTRA_MAP:
    app_id = '-'.join((app_prefix, SECRET_ID_EXTRA_MAP[app], 'id'))
  else:
    app_id = '-'.join((app_prefix, 'id'))

  secret = base64.b64encode(SECRET_MAP[app]).decode('utf-8').rstrip('=').replace('+', '-').replace(
      '/', '_')
  app_secret = '-'.join((app_prefix, secret))

  # Extract the region from the app ID (and fallback to US)
  region = app[-2:]
  if region not in AYLA_USER_SERVERS:
    region = 'us'
  user_server = AYLA_USER_SERVERS[region]
  devices_server = AYLA_DEVICES_SERVERS[region]

  access_token = await _sign_in(user, passwd, user_server, app_id, app_secret, session)

  result = []
  headers = {
      'Accept': 'application/json',
      'Connection': 'Keep-Alive',
      'Authorization': 'auth_token ' + access_token,
      'User-Agent': _USER_AGENT,
      'Host': devices_server,
      'Accept-Encoding': 'gzip'
  }
  devices = await _get_devices(devices_server, headers, session)
  _LOGGER.debug('Found %d devices', len(devices))
  for device in devices:
    device_data = device['device']
    if device_filter and device_filter != device_data['product_name']:
      continue
    dsn = device_data['dsn']
    lanip = await _get_lanip(devices_server, dsn, headers, session)
    device_data['lanip_key'] = lanip['lanip_key']
    device_data['lanip_key_id'] = lanip['lanip_key_id']
    device_data['temp_type'] = 'C' if app in CELSIUS_BASED_APPS else 'F'
    # If the server doesn't know the MAC address, fetch it from the local network.
    if not device_data.get('mac'):
      mac = await asyncio.to_thread(get_mac_address, ip=device_data['lan_ip'])
      if not mac or mac == '00:00:00:00:00:00':
        _LOGGER.error(f'Failed to fetch MAC address for AC on IP address {device_data["lan_ip"]}.' +
                      '\nAre you sure it is connected? Skipping...')
        continue
      device_data['mac'] = mac.replace(':', '')
    result.append(device_data)
  return result
