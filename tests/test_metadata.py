"""Translation compatibility and manifest checks."""

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / 'custom_components/hisense_aircon'


def keys(value, prefix=''):
  if not isinstance(value, dict):
    return set()
  return {prefix + key for key in value} | set().union(
      *(keys(child, prefix + key + '.') for key, child in value.items()))


class MetadataTests(unittest.TestCase):
  def test_translation_keys_and_protocol_sleep_values(self):
    english = json.loads((COMPONENT / 'strings.json').read_text())
    for path in (COMPONENT / 'translations').glob('*.json'):
      translation = json.loads(path.read_text())
      self.assertEqual(keys(english), keys(translation), path.name)
      self.assertEqual(set(translation['entity']['select']['sleep_mode']['state']),
                       {'stop', 'one', 'two', 'three', 'four'})

  def test_project_metadata_and_changelog(self):
    manifest = json.loads((COMPONENT / 'manifest.json').read_text())
    self.assertEqual(manifest['codeowners'], ['@cvladan'])
    self.assertIn(f"## {manifest['version']}\n", (ROOT / 'CHANGELOG.md').read_text())
    self.assertFalse(manifest['single_config_entry'])
    self.assertEqual(manifest['dhcp'], [{'registered_devices': True}])
