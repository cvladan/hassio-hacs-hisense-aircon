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
    self.hass.data[DOMAIN] = {"first": first, "second": second, "views_registered": True}
    request = SimpleNamespace(app={"hass": self.hass}, remote="192.0.2.2")
    self.assertIs(_controller_from_request(request), second)
    del self.hass.data[DOMAIN]["first"]
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
