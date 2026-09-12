"""Independent LAN registration and keepalive loops for each device."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http import HTTPStatus
import logging
import time

import aiohttp

from .aircon import Device

_LOGGER = logging.getLogger(__name__)


@dataclass
class _NotifyConfiguration:
  device: Device
  local_ip: str
  last_timestamp: float = 0
  failures: int = 0
  next_attempt: float = 0
  reconnect: bool = False
  notification: asyncio.Event = field(default_factory=asyncio.Event)


class Notifier:
  _KEEP_ALIVE_INTERVAL = 10.0
  _REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=5.0)
  _TIME_TO_HANDLE_REQUESTS = 0.1
  _HEADERS = {'Accept': 'application/json', 'Connection': 'keep-alive', 'Accept-Encoding': 'gzip'}

  def __init__(self, port: int, local_ip: str | None):
    self._configurations = []
    self._running = False
    self._json = {'local_reg': {'ip': local_ip, 'notify': 0, 'port': port, 'uri': '/local_lan'}}

  def register_device(self, device: Device, local_ip: str | None = None):
    if not any(conf.device is device for conf in self._configurations):
      self._configurations.append(_NotifyConfiguration(
          device, local_ip or self._json['local_reg']['ip']))

  def notify(self, mac_address: str, *, reconnect=False):
    for config in self._configurations:
      if config.device.mac_address == mac_address:
        config.reconnect |= reconnect
        config.notification.set()
        return

  async def start(self, session: aiohttp.ClientSession):
    self._running = True
    async with asyncio.TaskGroup() as group:
      for config in self._configurations:
        group.create_task(self._run_device(session, config))

  async def stop(self):
    self._running = False
    for config in self._configurations:
      config.notification.set()

  def _next_request(self, config):
    if config.reconnect:
      return config.last_timestamp + self._TIME_TO_HANDLE_REQUESTS
    if config.failures:
      return config.next_attempt
    if not config.last_timestamp:
      return 0
    interval = (self._TIME_TO_HANDLE_REQUESTS
                if config.device.available and not config.device.commands_queue.empty()
                else self._KEEP_ALIVE_INTERVAL)
    return config.last_timestamp + interval

  async def _run_device(self, session, config):
    while self._running:
      config.notification.clear()
      await self._perform_request(session, config)
      delay = max(self._TIME_TO_HANDLE_REQUESTS, self._next_request(config) - time.monotonic())
      try:
        await asyncio.wait_for(config.notification.wait(), timeout=delay)
      except TimeoutError:
        pass

  @staticmethod
  def _record_failure(config, now):
    config.last_timestamp = now
    config.failures += 1
    config.next_attempt = now + min(10, 2 ** min(config.failures, 4))
    config.device.update_diagnostics(failures=config.failures)
    if config.failures >= 3:
      config.device.available = False

  async def _perform_request(self, session: aiohttp.ClientSession,
                             config: _NotifyConfiguration) -> int:
    if time.monotonic() < self._next_request(config):
      return config.device.commands_queue.qsize()
    method = 'PUT' if config.device.available and not config.failures and not config.reconnect else 'POST'
    config.reconnect = False
    payload = {'local_reg': {**self._json['local_reg'], 'ip': config.local_ip,
                             'notify': int(not config.device.commands_queue.empty())}}
    url = f'http://{config.device.ip_address}/local_reg.json'
    _LOGGER.debug('Sending %s local registration to %s', method, config.device.ip_address)
    try:
      async with session.request(method, url, json=payload, headers=self._HEADERS,
                                 timeout=self._REQUEST_TIMEOUT) as resp:
        if resp.status != HTTPStatus.ACCEPTED:
          _LOGGER.warning('Local registration to %s failed: HTTP %s', config.device.ip_address, resp.status)
          self._record_failure(config, time.monotonic())
          return 0
    except (aiohttp.ClientError, TimeoutError) as ex:
      _LOGGER.warning('Failed to connect to %s: %s', config.device.ip_address, ex)
      self._record_failure(config, time.monotonic())
      return 0
    config.last_timestamp = time.monotonic()
    config.failures = 0
    config.next_attempt = 0
    config.device.update_diagnostics(last_registration=datetime.now(timezone.utc), failures=0)
    config.device.available = True
    if method == 'POST':
      config.device.queue_status()
    return config.device.commands_queue.qsize()
