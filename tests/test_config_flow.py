"""Config flow and callback routing regressions, using Home Assistant classes."""

import tempfile
from types import MappingProxyType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from aiohttp import web
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry, ConfigEntries
from homeassistant.helpers import device_registry as dr, entity_registry as er, frame

from custom_components.hisense_aircon.config_flow import HisenseConfigFlow
from custom_components.hisense_aircon.const import DOMAIN
from custom_components.hisense_aircon.controller import HisenseController, _controller_from_request


def device(mac="001122334455", ip="192.0.2.1"):
  return dict(name="Test", app="hisense-eu", model="AEH-W4E1", sw_version="",
              mac_address=mac, ip_address=ip, lanip_key="testkey", lanip_key_id=1,
              temp_type="C", dsn="test-dsn")


class ConfigFlowTests(unittest.IsolatedAsyncioTestCase):
  async def asyncSetUp(self):
    self.directory = tempfile.TemporaryDirectory()
    self.hass = HomeAssistant(self.directory.name)
    frame.async_setup(self.hass)
    self.hass.config_entries = ConfigEntries(self.hass, {})
    if hasattr(dr, "async_setup"):
      dr.async_setup(self.hass)
    await dr.async_load(self.hass, load_empty=True)
    await er.async_load(self.hass, load_empty=True)
    self.entry = self.add_entry([device()])
    self.flow = HisenseConfigFlow()
    self.flow.hass = self.hass
    self.flow.context = {"source": "reconfigure", "entry_id": self.entry.entry_id}
    self.flow.flow_id = "test"
    self.flow.handler = DOMAIN

  def add_entry(self, devices):
    entry = ConfigEntry(version=1, minor_version=1, domain=DOMAIN,
                        title="Test", data={"devices": devices, "app": "hisense-eu"},
                        options={"status_interval": 600}, source="user", unique_id=None,
                        discovery_keys=MappingProxyType({}), subentries_data=None)
    self.hass.config_entries._entries[entry.entry_id] = entry
    return entry

  async def asyncTearDown(self):
    await self.hass.async_stop(force=True)
    self.directory.cleanup()

  async def test_existing_entry_can_add_devices_without_migration_or_password(self):
    discovered = [{**device("aabbccddeeff", "192.0.2.2"), "product_name": "New",
                   "mac": "aa:bb:cc:dd:ee:ff", "lan_ip": "192.0.2.2"}]
    with patch("custom_components.hisense_aircon.config_flow.perform_discovery",
               AsyncMock(return_value=discovered)), patch(
                   "custom_components.hisense_aircon.config_flow.async_get_clientsession"):
      await self.flow.async_step_cloud({"app": "hisense-eu", "username": "test", "password": "secret"})
    result = await self.flow.async_step_select_devices(
        {"selected_devices": ["001122334455", "aabbccddeeff"]})
    self.assertEqual(result["type"], "abort")
    self.assertEqual(self.entry.version, 1)
    self.assertEqual(len(self.entry.data["devices"]), 2)
    self.assertNotIn("password", self.entry.data)
    self.assertEqual(self.entry.options["status_interval"], 600)

  async def test_duplicate_mac_or_ip_and_empty_selection(self):
    self.add_entry([device("aabbccddeeff", "192.0.2.2")])
    for candidate in (device("aabbccddeeff", "192.0.2.3"), device("000000000001", "192.0.2.2")):
      self.assertTrue(self.flow._conflicts([device(), candidate]))
    self.assertFalse(self.flow._conflicts([device()]))
    result = await self.flow.async_step_manage_devices({"selected_devices": []})
    self.assertEqual(result["errors"]["base"], "no_device_selected")

  async def test_removal_preserves_other_entry_association(self):
    second = device("aabbccddeeff", "192.0.2.2")
    self.hass.config_entries.async_update_entry(self.entry, data={"devices": [device(), second]})
    other = self.add_entry([])
    registry = dr.async_get(self.hass)
    record = registry.async_get_or_create(config_entry_id=self.entry.entry_id,
                                          identifiers={(DOMAIN, second["mac_address"])})
    other_record = registry.async_get_or_create(config_entry_id=other.entry_id,
                                                identifiers={(DOMAIN, second["mac_address"])})
    entities = er.async_get(self.hass)
    own = entities.async_get_or_create("sensor", DOMAIN, "own", config_entry=self.entry,
                                      device_id=record.id)
    shared = entities.async_get_or_create("sensor", DOMAIN, "shared", config_entry=other,
                                         device_id=other_record.id)
    await self.flow.async_step_manage_devices({"selected_devices": [device()["mac_address"]]})
    self.assertIsNotNone(registry.async_get(other_record.id))
    self.assertIsNone(entities.async_get(own.entity_id))
    self.assertIsNotNone(entities.async_get(shared.entity_id))

  async def test_routes_each_device_and_survives_other_controller_removal(self):
    first = object.__new__(HisenseController)
    second = object.__new__(HisenseController)
    first.handlers = SimpleNamespace(device_ips={"192.0.2.1"})
    second.handlers = SimpleNamespace(device_ips={"192.0.2.2"})
    self.entry.runtime_data = first
    other = self.add_entry([device("aabbccddeeff", "192.0.2.2")])
    other.runtime_data = second
    request = SimpleNamespace(app={"hass": self.hass}, remote="192.0.2.2")
    self.assertIs(_controller_from_request(request), second)
    del self.entry.runtime_data
    self.assertIs(_controller_from_request(request), second)
    request.remote = "192.0.2.99"
    with self.assertRaises(web.HTTPNotFound):
      _controller_from_request(request)

  async def test_ip_change_updates_only_selected_device_and_validates_conflicts(self):
    devices = [device(), device('aabbccddeeff', '192.0.2.2'), device('112233445566', '192.0.2.3')]
    self.hass.config_entries.async_update_entry(self.entry, data={'devices': devices})
    await self.flow.async_step_edit_device({'mac_address': 'aabbccddeeff'})
    for address, error in [('bad-ip', 'invalid_manual_config'), ('192.0.2.1', 'duplicate_device')]:
      result = await self.flow.async_step_edit_ip({'host': address})
      self.assertEqual(result['errors']['base'], error)
    result = await self.flow.async_step_edit_ip({'host': '192.0.2.20'})
    self.assertEqual(result['type'], 'abort')
    self.assertEqual([d['ip_address'] for d in self.entry.data['devices']],
                     ['192.0.2.1', '192.0.2.20', '192.0.2.3'])
    controller = HisenseController(self.hass, self.entry)
    self.assertIn('192.0.2.20', controller.handlers.device_ips)
    self.assertNotIn('192.0.2.2', controller.handlers.device_ips)

  async def test_setup_removes_only_its_registered_climate_duplicates(self):
    from custom_components.hisense_aircon import async_setup_entry
    from custom_components.hisense_aircon.aircon import Device
    from unittest.mock import Mock
    registry = er.async_get(self.hass)
    old = registry.async_get_or_create('switch', DOMAIN, '001122334455_t_power',
                                       config_entry=self.entry)
    keep = registry.async_get_or_create('select', DOMAIN, '001122334455_t_sleep',
                                        config_entry=self.entry)
    controller = Mock(devices=[Device.create(device(), lambda: None)], async_start=AsyncMock())
    with patch('custom_components.hisense_aircon.HisenseController', return_value=controller), patch.object(
        self.hass.config_entries, 'async_forward_entry_setups', AsyncMock()):
      await async_setup_entry(self.hass, self.entry)
    self.assertIsNone(registry.async_get(old.entity_id))
    self.assertIsNotNone(registry.async_get(keep.entity_id))

  async def test_new_manual_and_second_account_setup(self):
    self.flow.context = {'source': 'user'}
    manual = dict(name='Manual', app='hisense-eu', host='192.0.2.2',
                  mac_address='aabbccddeeff', lanip_key='testkey', lanip_key_id=1,
                  model='AEH-W4E1', temp_type='C')
    result = await self.flow.async_step_manual(manual)
    self.assertEqual(result['type'], 'create_entry')
    self.add_entry(result['data']['devices'])
    duplicate = await self.flow.async_step_manual(manual)
    self.assertEqual(duplicate['errors']['base'], 'duplicate_device')
    discovered = [{**device('112233445566', '192.0.2.3'), 'product_name': 'Second account',
                   'mac': '112233445566', 'lan_ip': '192.0.2.3'}]
    with patch('custom_components.hisense_aircon.config_flow.perform_discovery',
               AsyncMock(return_value=discovered)), patch(
                   'custom_components.hisense_aircon.config_flow.async_get_clientsession'):
      await self.flow.async_step_cloud({'app': 'oem-eu', 'username': 'other', 'password': 'secret'})
    result = await self.flow.async_step_select_devices({'selected_devices': ['112233445566']})
    self.assertEqual(result['type'], 'create_entry')
    self.assertEqual(result['data']['app'], 'oem-eu')
    self.assertNotIn('password', result['data'])
    self.assertNotIn('username', result['data'])

  async def test_malformed_cloud_device_and_empty_local_ip(self):
    from custom_components.hisense_aircon.config_flow import HisenseOptionsFlow
    with patch('custom_components.hisense_aircon.config_flow.perform_discovery',
               AsyncMock(return_value=[{'product_name': 'Bad', 'mac': 'invalid'}])), patch(
                   'custom_components.hisense_aircon.config_flow.async_get_clientsession'), self.assertLogs(
                       'custom_components.hisense_aircon.config_flow', level='WARNING'):
      result = await self.flow.async_step_cloud({'app': 'hisense-eu', 'username': 'u', 'password': 'p'})
    self.assertEqual(result['errors']['base'], 'cannot_connect')
    options = HisenseOptionsFlow(self.entry)
    options.hass = self.hass
    form = await options.async_step_init()
    for value in ('', None):
      data = form['data_schema']({'local_ip': value})
      result = await options.async_step_init(data)
      self.assertIsNone(result['data']['local_ip'])

  async def test_cloud_error_categories(self):
    from custom_components.hisense_aircon.error import InvalidAuth
    for outcome, error in [(InvalidAuth('rejected'), 'invalid_auth'),
                           (TimeoutError(), 'cannot_connect'), ([], 'device_not_found')]:
      discovery = AsyncMock(side_effect=outcome) if isinstance(outcome, Exception) else AsyncMock(return_value=outcome)
      with patch('custom_components.hisense_aircon.config_flow.perform_discovery', discovery), patch(
          'custom_components.hisense_aircon.config_flow.async_get_clientsession'):
        result = await self.flow.async_step_cloud({'app': 'hisense-eu', 'username': 'u', 'password': 'secret'})
      self.assertEqual(result['errors']['base'], error)

  async def test_local_ip_validation_in_each_form(self):
    import voluptuous as vol
    from custom_components.hisense_aircon.config_flow import HisenseOptionsFlow
    options = HisenseOptionsFlow(self.entry)
    options.hass = self.hass
    schema = (await options.async_step_init())['data_schema']
    self.assertEqual(schema({'local_ip': ' 192.0.2.100 '})['local_ip'], '192.0.2.100')
    for address in ('bad-ip', '::1', '999.1.1.1'):
      with self.assertRaises(vol.Invalid):
        schema({'local_ip': address})
    self.flow.context = {'source': 'user'}
    for step in (self.flow.async_step_manual, self.flow.async_step_cloud):
      schema = (await step())['data_schema']
      values = schema.schema
      if step == self.flow.async_step_cloud:
        values = next(value.schema.schema for key, value in values.items()
                      if key.schema == 'advanced_settings')
      validator = next(value for key, value in values.items() if key.schema == 'local_ip')
      self.assertIsNone(validator(''))
      with self.assertRaises(ValueError):
        validator('bad-ip')

  async def test_callback_ip_selection_and_network_retry(self):
    from unittest.mock import Mock
    from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
    self.hass.config_entries.async_update_entry(self.entry, data={
        'devices': [device(), device('aabbccddeeff', '198.51.100.2')]})
    controller = HisenseController(self.hass, self.entry)
    with patch.object(controller, '_register_views'), patch(
        'custom_components.hisense_aircon.controller.async_get_source_ip',
        AsyncMock(side_effect=['192.0.2.100', '198.51.100.100'])) as source, patch(
            'custom_components.hisense_aircon.controller.async_get_clientsession'), patch.object(
                controller, '_create_background_task', side_effect=lambda coro, name: coro.close()):
      await controller.async_start()
    self.assertEqual([c.local_ip for c in controller._notifier._configurations],
                     ['192.0.2.100', '198.51.100.100'])
    self.assertEqual([call.kwargs['target_ip'] for call in source.call_args_list],
                     ['192.0.2.1', '198.51.100.2'])
    controller = HisenseController(self.hass, self.entry)
    with patch.object(controller, '_register_views'), patch(
        'custom_components.hisense_aircon.controller.async_get_source_ip',
        AsyncMock(side_effect=HomeAssistantError('no route'))):
      with self.assertRaises(ConfigEntryNotReady):
        await controller.async_start()
    self.hass.config_entries.async_update_entry(self.entry, options={'local_ip': '192.0.2.200'})
    controller = HisenseController(self.hass, self.entry)
    with patch.object(controller, '_register_views'), patch(
        'custom_components.hisense_aircon.controller.async_get_source_ip', AsyncMock()) as source, patch(
            'custom_components.hisense_aircon.controller.async_get_clientsession'), patch.object(
                controller, '_create_background_task', side_effect=lambda coro, name: coro.close()):
      await controller.async_start()
    source.assert_not_awaited()
    self.assertEqual([c.local_ip for c in controller._notifier._configurations], ['192.0.2.200'] * 2)

  async def test_setup_failure_and_unload_cleanup(self):
    import asyncio
    from unittest.mock import Mock
    from custom_components.hisense_aircon import async_setup_entry, async_unload_entry
    from custom_components.hisense_aircon.aircon import Device
    registry = er.async_get(self.hass)
    old = registry.async_get_or_create('switch', DOMAIN, '001122334455_t_power', config_entry=self.entry)
    for failure in (RuntimeError('platform failure'), asyncio.CancelledError()):
      controller = Mock(devices=[Device.create(device(), lambda: None)],
                        async_start=AsyncMock(), async_stop=AsyncMock())
      with patch('custom_components.hisense_aircon.HisenseController', return_value=controller), patch.object(
          self.hass.config_entries, 'async_forward_entry_setups', AsyncMock(side_effect=failure)), patch.object(
              self.hass.config_entries, 'async_unload_platforms', AsyncMock(return_value=True)):
        with self.assertRaises(type(failure)):
          await async_setup_entry(self.hass, self.entry)
      controller.async_stop.assert_awaited_once()
      self.assertFalse(hasattr(self.entry, 'runtime_data'))
      self.assertIsNotNone(registry.async_get(old.entity_id))
    self.entry.runtime_data = controller
    for success in (False, True):
      controller.async_stop.reset_mock()
      with patch.object(self.hass.config_entries, 'async_unload_platforms', AsyncMock(return_value=success)):
        self.assertEqual(await async_unload_entry(self.hass, self.entry), success)
      self.assertEqual(hasattr(self.entry, 'runtime_data'), not success)
      self.assertEqual(controller.async_stop.await_count, int(success))

  async def test_controller_stop_is_safe_before_start_and_after_cancel(self):
    import asyncio
    controller = HisenseController(self.hass, self.entry)
    await controller.async_stop()
    with patch.object(controller, '_register_views'), patch(
        'custom_components.hisense_aircon.controller.async_get_source_ip', AsyncMock(return_value='192.0.2.100')), patch(
            'custom_components.hisense_aircon.controller.async_get_clientsession'), patch.object(
                controller._notifier, 'start', new=lambda session: asyncio.sleep(3600)):
      await controller.async_start()
      tasks = list(controller._tasks)
      await controller.async_stop()
      await controller.async_stop()
    self.assertTrue(all(task.done() for task in tasks))
    self.assertFalse(controller._tasks)
    self.assertFalse(controller.devices[0]._property_change_listeners)
