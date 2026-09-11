"""Hisense Air Conditioner integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .controller import HisenseController

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
  """Set up Hisense Air Conditioner from a config entry."""
  controller = HisenseController(hass, entry)
  hass.data.setdefault(DOMAIN, {})[entry.entry_id] = controller
  await controller.async_start()
  await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
  entry.async_on_unload(entry.add_update_listener(_async_update_listener))
  return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
  """Unload a config entry."""
  unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
  if unload_ok:
    controller = hass.data[DOMAIN].pop(entry.entry_id)
    await controller.async_stop()
  return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
  """Reload when options change."""
  await hass.config_entries.async_reload(entry.entry_id)
