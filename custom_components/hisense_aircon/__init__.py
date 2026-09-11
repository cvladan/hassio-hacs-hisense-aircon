"""Hisense Air Conditioner integration for Home Assistant."""

from __future__ import annotations

import asyncio

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .controller import HisenseConfigEntry, HisenseController
from .entity import climate_managed_properties

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: HisenseConfigEntry) -> bool:
  """Set up Hisense Air Conditioner from a config entry."""
  controller = HisenseController(hass, entry)
  entry.runtime_data = controller
  try:
    await controller.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
  except (Exception, asyncio.CancelledError):
    try:
      await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    finally:
      await controller.async_stop()
      del entry.runtime_data
    raise
  duplicates = {f"{device.mac_address}_{name}" for device in controller.devices
                for name in climate_managed_properties(device)}
  registry = er.async_get(hass)
  for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
    if entity.domain in ("switch", "select", "number") and entity.unique_id in duplicates:
      registry.async_remove(entity.entity_id)
  entry.async_on_unload(entry.add_update_listener(_async_update_listener))
  return True


async def async_unload_entry(hass: HomeAssistant, entry: HisenseConfigEntry) -> bool:
  """Unload a config entry."""
  unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
  if unload_ok:
    await entry.runtime_data.async_stop()
    del entry.runtime_data
  return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: HisenseConfigEntry) -> None:
  """Reload when options change."""
  await hass.config_entries.async_reload(entry.entry_id)
