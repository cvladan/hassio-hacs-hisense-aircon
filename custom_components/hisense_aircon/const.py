"""Constants for the Hisense Air Conditioner integration."""

from __future__ import annotations

DOMAIN = "hisense_aircon"

CONF_APP = "app"
CONF_CALLBACK_PORT = "callback_port"
CONF_DEVICES = "devices"
CONF_DEVICE_NAME = "device_name"
CONF_LANIP_KEY = "lanip_key"
CONF_LANIP_KEY_ID = "lanip_key_id"
CONF_LOCAL_IP = "local_ip"
CONF_MAC_ADDRESS = "mac_address"
CONF_MODEL = "model"
CONF_SETUP_METHOD = "setup_method"
CONF_STATUS_INTERVAL = "status_interval"
CONF_SW_VERSION = "sw_version"
CONF_TEMP_TYPE = "temp_type"
CONF_TEMP_TYPE_AUTO = "auto"

DEFAULT_CALLBACK_PORT = 8123
DEFAULT_STATUS_INTERVAL = 600

SETUP_METHOD_CLOUD = "cloud"
SETUP_METHOD_MANUAL = "manual"

TEMP_TYPE_OPTIONS = [CONF_TEMP_TYPE_AUTO, "C", "F"]

VIEWS_REGISTERED = "views_registered"


def signal_device_update(entry_id: str, mac_address: str) -> str:
  """Return dispatcher signal for a device update."""
  return f"{DOMAIN}_{entry_id}_{mac_address}"
