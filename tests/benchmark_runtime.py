"""Run with PYTHONPATH=. python tests/benchmark_runtime.py; no timing gates in CI."""

from statistics import median
from timeit import repeat
from types import SimpleNamespace

from custom_components.hisense_aircon.aircon import Device
from custom_components.hisense_aircon.climate import HisenseClimate
from custom_components.hisense_aircon.config import Encryption
from custom_components.hisense_aircon.entity import property_fields
from custom_components.hisense_aircon import control_value
from custom_components.hisense_aircon.properties import Power, AcWorkMode

unit = Device.create(dict(name='Benchmark', app='hisense-eu', model='AEH-W4E1', sw_version='',
                          mac_address='001122334455', ip_address='192.0.2.1',
                          lanip_key='testkey', lanip_key_id=1, temp_type='C'), lambda: None)
climate = HisenseClimate(SimpleNamespace(), unit)
writes = []
climate.async_write_ha_state = lambda: writes.append(1)
unit.add_property_change_listener(lambda mac, changed: climate._handle_device_update(changed))
value = control_value.set_power(0, Power.ON)
value = control_value.set_work_mode(value, AcWorkMode.COOL)
value = control_value.set_temp(value, 24)
unit.update_property('t_control_value', value)
print(f'Climate writes per packed report: {len(writes)}')
writes.clear()
unit.update_property('f_voltage', 230)
print(f'Climate writes per unrelated voltage report: {len(writes)}')
encryption = Encryption(b'testkey', b'benchmark')
for name, operation in (
    ('Property metadata', lambda: property_fields(unit)),
    ('AES CBC 64-byte message', lambda: encryption.encryptor.update(b'x' * 64)),
):
  duration = median(repeat(operation, number=10000, repeat=5)) / 10000
  print(f'{name}: {duration * 1e6:.2f} microseconds per call (median of 5 runs)')
