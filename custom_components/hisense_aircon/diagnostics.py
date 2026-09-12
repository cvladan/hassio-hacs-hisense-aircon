"""Device diagnostics without account credentials or network identifiers."""

import enum
from datetime import datetime


async def async_get_config_entry_diagnostics(hass, entry):
  """Export reported protocol state, using an allowlist instead of raw config data."""
  controller = getattr(entry, "runtime_data", None)
  return {
      "devices": [
          {
              "model": device.model,
              "app": device.app,
              "available": device.available,
              "queued_commands": device.commands_queue.qsize(),
              "lan_key_invalid": device.lan_key_invalid,
              **{name: value.isoformat() if isinstance(value, datetime) else value
                 for name, value in device.diagnostics.items()},
              "properties": {
                  name: value.name.lower() if isinstance(value, enum.Enum) else value
                  for name, value in device._reported_properties.items()
              },
          }
          for device in controller.devices
      ] if controller else [],
  }
