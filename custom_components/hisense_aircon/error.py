class Error(Exception):
  """Error class for AC handling."""


class KeyIdReplaced(Error):
  """The device requests a different LAN key."""


class InvalidAuth(Error):
  """The cloud account rejected the supplied credentials."""
