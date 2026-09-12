from dataclasses import dataclass, field
import enum


class FanSpeed(enum.IntEnum):
  AUTO = 0
  LOWER = 5
  LOW = 6
  MEDIUM = 7
  HIGH = 8
  HIGHER = 9


class VertiSweep(enum.IntEnum):
  SWEEP = 0
  AUTO = 1
  ANGLE1 = 2
  ANGLE2 = 3
  ANGLE3 = 4
  ANGLE4 = 5
  ANGLE5 = 6
  ANGLE6 = 7


class SleepMode(enum.IntEnum):
  STOP = 0
  ONE = 1
  TWO = 2
  THREE = 3
  FOUR = 4


class AcWorkMode(enum.IntEnum):
  FAN = 0
  HEAT = 1
  COOL = 2
  DRY = 3
  AUTO = 4


class AirFlow(enum.Enum):
  OFF = 0
  ON = 1


class Dimmer(enum.Enum):
  ON = 0
  OFF = 1


class DoubleFrequency(enum.Enum):
  OFF = 0
  ON = 1


class Economy(enum.Enum):
  OFF = 0
  ON = 1


class Powerful(enum.Enum):
  OFF = 0
  ON = 1


class EightHeat(enum.Enum):
  OFF = 0
  ON = 1


class FastColdHeat(enum.Enum):
  OFF = 0
  ON = 1


class Power(enum.Enum):
  OFF = 0
  ON = 1


class Quiet(enum.Enum):
  OFF = 0
  ON = 1


class TemperatureUnit(enum.Enum):
  CELSIUS = 0
  FAHRENHEIT = 1


class HumidifierWorkMode(enum.Enum):
  NORMAL = 0
  NIGHTLIGHT = 1
  SLEEP = 2


class HumidifierWater(enum.Enum):
  OK = 0
  NO_WATER = 1


class Mist(enum.Enum):
  SMALL = 1
  MIDDLE = 2
  BIG = 3


class MistState(enum.Enum):
  OFF = 0
  ON = 1


class FglOperationMode(enum.IntEnum):
  OFF = 0
  ON = 1
  AUTO = 2
  COOL = 3
  DRY = 4
  FAN_ONLY = 5
  FAN = 5
  HEAT = 6


class FglFanSpeed(enum.IntEnum):
  DIFFUSE = 0
  QUIET = 0
  LOW = 1
  MEDIUM = 2
  HIGH = 3
  AUTO = 4


class OutdoorLowNoise(enum.Enum):
  OFF = 0
  ON = 1


class Getprop(enum.Enum):
  OFF = 0
  ON = 1


class Refresh(enum.Enum):
  OFF = 0
  ON = 1


class Properties(object):

  @classmethod
  def _get_metadata(cls, attr: str):
    return cls.__dataclass_fields__[attr].metadata

  @classmethod
  def get_type(cls, attr: str):
    return cls.__dataclass_fields__[attr].type

  @classmethod
  def parse_attr(cls, attr: str, value):
    parser = cls._get_metadata(attr).get('parser')
    if parser:
      return parser(value)
    return cls.get_type(attr)(value)

  @classmethod
  def get_base_type(cls, attr: str):
    return cls._get_metadata(attr)['base_type']

  @classmethod
  def get_scale(cls, attr: str):
    return cls._get_metadata(attr).get('scale', 1)

  @classmethod
  def get_precision(cls, attr: str):
    return cls._get_metadata(attr).get('precision', 1)

  @classmethod
  def get_read_only(cls, attr: str):
    return cls._get_metadata(attr)['read_only']


@dataclass
class AcProperties(Properties):
  f_electricity: int = field(default=100, metadata={'base_type': 'integer', 'read_only': True})
  f_e_arkgrille: bool = field(default=0, metadata={'base_type': 'boolean', 'read_only': True})
  f_e_incoiltemp: bool = field(default=0, metadata={'base_type': 'boolean', 'read_only': True})
  f_e_incom: bool = field(default=0, metadata={'base_type': 'boolean', 'read_only': True})
  f_e_indisplay: bool = field(default=0, metadata={'base_type': 'boolean', 'read_only': True})
  f_e_ineeprom: bool = field(default=0, metadata={'base_type': 'boolean', 'read_only': True})
  f_e_inele: bool = field(default=0, metadata={'base_type': 'boolean', 'read_only': True})
  f_e_infanmotor: bool = field(default=0, metadata={'base_type': 'boolean', 'read_only': True})
  f_e_inhumidity: bool = field(default=0, metadata={'base_type': 'boolean', 'read_only': True})
  f_e_inkeys: bool = field(default=0, metadata={'base_type': 'boolean', 'read_only': True})
  f_e_inlow: bool = field(default=0, metadata={'base_type': 'boolean', 'read_only': True})
  f_e_intemp: bool = field(default=0, metadata={'base_type': 'boolean', 'read_only': True})
  f_e_invzero: bool = field(default=0, metadata={'base_type': 'boolean', 'read_only': True})
  f_e_outcoiltemp: bool = field(default=0, metadata={'base_type': 'boolean', 'read_only': True})
  f_e_outeeprom: bool = field(default=0, metadata={'base_type': 'boolean', 'read_only': True})
  f_e_outgastemp: bool = field(default=0, metadata={'base_type': 'boolean', 'read_only': True})
  f_e_outmachine2: bool = field(default=0, metadata={'base_type': 'boolean', 'read_only': True})
  f_e_outmachine: bool = field(default=0, metadata={'base_type': 'boolean', 'read_only': True})
  f_e_outtemp: bool = field(default=0, metadata={'base_type': 'boolean', 'read_only': True})
  f_e_outtemplow: bool = field(default=0, metadata={'base_type': 'boolean', 'read_only': True})
  f_e_push: bool = field(default=0, metadata={'base_type': 'boolean', 'read_only': True})
  f_filterclean: bool = field(default=0, metadata={'base_type': 'boolean', 'read_only': True})
  f_humidity: int = field(default=50, metadata={
      'base_type': 'integer',
      'read_only': True
  })  # Humidity
  f_power_display: bool = field(default=0, metadata={'base_type': 'boolean', 'read_only': True})
  f_temp_in: float = field(default=81.0, metadata={
      'base_type': 'decimal',
      'read_only': True
  })  # EnvironmentTemperature (Fahrenheit)
  f_voltage: int = field(default=0, metadata={'base_type': 'integer', 'read_only': True})
  t_backlight: Dimmer = field(default=Dimmer.OFF,
                              metadata={
                                  'base_type': 'boolean',
                                  'read_only': False,
                              })  # DimmerStatus
  t_control_value: int = field(default=None, metadata={'base_type': 'integer', 'read_only': False})
  t_device_info: bool = field(default=0, metadata={'base_type': 'boolean', 'read_only': False})
  t_display_power: bool = field(default=None, metadata={'base_type': 'boolean', 'read_only': False})
  t_eco: Economy = field(default=Economy.OFF,
                         metadata={
                             'base_type': 'boolean',
                             'read_only': False,
                         })
  t_fan_leftright: AirFlow = field(default=AirFlow.OFF,
                                   metadata={
                                       'base_type': 'boolean',
                                       'read_only': False,
                                   })  # HorizontalAirFlow
  t_fan_mute: Quiet = field(default=Quiet.OFF,
                            metadata={
                                'base_type': 'boolean',
                                'read_only': False,
                            })  # QuietModeStatus
  t_fan_power: AirFlow = field(default=AirFlow.OFF,
                               metadata={
                                   'base_type': 'boolean',
                                   'read_only': False,
                               })  # VerticalAirFlow
  t_fan_speed: FanSpeed = field(default=FanSpeed.AUTO,
                                metadata={
                                    'base_type': 'integer',
                                    'read_only': False,
                                })  # FanSpeed
  t_swing_angle: VertiSweep = field(default=VertiSweep.AUTO,
                                    metadata={
                                        'base_type': 'integer',
                                        'read_only': False,
                                    })  # Vertical sweep angle
  t_ftkt_start: int = field(default=None, metadata={'base_type': 'integer', 'read_only': False})
  t_power: Power = field(default=Power.ON,
                         metadata={
                             'base_type': 'boolean',
                             'read_only': False,
                         })  # PowerStatus
  t_run_mode: DoubleFrequency = field(default=DoubleFrequency.OFF,
                                      metadata={
                                          'base_type': 'boolean',
                                          'read_only': False,
                                      })  # DoubleFrequency
  t_setmulti_value: int = field(default=None, metadata={'base_type': 'integer', 'read_only': False})
  t_sleep: SleepMode = field(default=SleepMode.STOP,
                             metadata={
                                 'base_type': 'integer',
                                 'read_only': False,
                             })  # SleepMode
  t_temp: int = field(default=81, metadata={
      'base_type': 'integer',
      'read_only': False
  })  # CurrentTemperature
  t_temptype: TemperatureUnit = field(default=TemperatureUnit.FAHRENHEIT,
                                      metadata={
                                          'base_type': 'boolean',
                                          'read_only': False,
                                      })  # CurrentTemperatureUnit
  t_temp_eight: EightHeat = field(default=EightHeat.OFF,
                                  metadata={
                                      'base_type': 'boolean',
                                      'read_only': False,
                                  })  # EightHeatStatus
  t_temp_heatcold: FastColdHeat = field(default=FastColdHeat.OFF,
                                        metadata={
                                            'base_type': 'boolean',
                                            'read_only': False,
                                        })  # FastCoolHeatStatus
  t_work_mode: AcWorkMode = field(default=AcWorkMode.AUTO,
                                  metadata={
                                      'base_type': 'integer',
                                      'read_only': False,
                                  })  # WorkModeStatus


@dataclass
class HumidifierProperties(Properties):
  humi: int = field(default=0, metadata={'base_type': 'integer', 'read_only': False})
  mist: Mist = field(default=Mist.SMALL,
                     metadata={
                         'base_type': 'integer',
                         'read_only': False,
                     })
  mistSt: MistState = field(default=MistState.OFF,
                            metadata={
                                'base_type': 'integer',
                                'read_only': True,
                            })
  realhumi: int = field(default=0, metadata={'base_type': 'integer', 'read_only': True})
  remain: int = field(default=0, metadata={'base_type': 'integer', 'read_only': True})
  switch: Power = field(default=Power.ON,
                        metadata={
                            'base_type': 'boolean',
                            'read_only': False,
                        })
  temp: int = field(default=81, metadata={'base_type': 'integer', 'read_only': True})
  timer: int = field(default=-1, metadata={'base_type': 'integer', 'read_only': False})
  water: HumidifierWater = field(default=HumidifierWater.OK,
                                 metadata={
                                     'base_type': 'boolean',
                                     'read_only': True,
                                 })
  workmode: HumidifierWorkMode = field(default=HumidifierWorkMode.NORMAL,
                                       metadata={
                                           'base_type': 'integer',
                                           'read_only': False,
                                       })


@dataclass
class FglProperties(Properties):
  operation_mode: FglOperationMode = field(default=FglOperationMode.AUTO,
                                           metadata={
                                               'base_type': 'integer',
                                               'read_only': False,
                                           })
  fan_speed: FglFanSpeed = field(default=FglFanSpeed.AUTO,
                                 metadata={
                                     'base_type': 'integer',
                                     'read_only': False,
                                 })
  adjust_temperature: int = field(default=25,
                                  metadata={
                                      'base_type': 'integer',
                                      'scale': 0.1,
                                      'precision': 0.5,
                                      'read_only': False
                                  })
  display_temperature: float = field(default=25,
                                     metadata={
                                      'base_type': 'integer',
                                      'read_only': True,
                                      'parser': lambda x: round((int(x) - 5000) / 50) / 2
                                     })
  outdoor_temperature: float = field(default=25,
                                     metadata={
                                         'base_type': 'integer',
                                         'read_only': True,
                                         'parser': lambda x: round((int(x) - 5000) / 50) / 2
                                     })
  af_vertical_direction: int = field(default=3,
                                     metadata={
                                         'base_type': 'integer',
                                         'read_only': False
                                     })
  af_vertical_swing: AirFlow = field(default=AirFlow.OFF,
                                     metadata={
                                         'base_type': 'boolean',
                                         'read_only': False,
                                     })  # HorizontalAirFlow
  af_horizontal_direction: int = field(default=3,
                                       metadata={
                                           'base_type': 'integer',
                                           'read_only': False
                                       })
  af_horizontal_swing: AirFlow = field(default=AirFlow.OFF,
                                       metadata={
                                           'base_type': 'boolean',
                                           'read_only': False,
                                       })  # HorizontalAirFlow
  economy_mode: Economy = field(default=Economy.OFF,
                                metadata={
                                    'base_type': 'boolean',
                                    'read_only': False,
                                })
  powerful_mode: Powerful = field(default=Powerful.OFF,
                                  metadata={
                                      'base_type': 'boolean',
                                      'read_only': False,
                                  })
  outdoor_low_noise: OutdoorLowNoise = field(default=OutdoorLowNoise.OFF,
                                             metadata={
                                                 'base_type': 'boolean',
                                                 'read_only': False,
                                             })
  get_prop: Getprop = field(default=Getprop.OFF,
                            metadata={
                                'base_type': 'boolean',
                                'read_only': False,
                            })
  get_prop2: Getprop = field(default=Getprop.OFF,
                             metadata={
                                 'base_type': 'boolean',
                                 'read_only': False,
                             })
  refresh: Refresh = field(default=Refresh.OFF,
                           metadata={
                               'base_type': 'boolean',
                               'read_only': False,
                           })


@dataclass
class FglBProperties(Properties):
  operation_mode: FglOperationMode = field(default=FglOperationMode.AUTO,
                                           metadata={
                                               'base_type': 'integer',
                                               'read_only': False,
                                           })
  fan_speed: FglFanSpeed = field(default=FglFanSpeed.AUTO,
                                 metadata={
                                     'base_type': 'integer',
                                     'read_only': False,
                                 })
  adjust_temperature: int = field(default=25,
                                  metadata={
                                      'base_type': 'integer',
                                      'scale': 0.1,
                                      'precision': 0.5,
                                      'read_only': False
                                  })
  display_temperature: float = field(default=25,
                                     metadata={
                                      'base_type': 'integer',
                                      'read_only': True,
                                      'parser': lambda x: round((int(x) - 5000) / 50) / 2
                                     })
  af_vertical_move_step1: int = field(default=3,
                                      metadata={
                                          'base_type': 'integer',
                                          'read_only': False
                                      })
  af_horizontal_move_step1: int = field(default=3,
                                        metadata={
                                            'base_type': 'integer',
                                            'read_only': False
                                        })
  economy_mode: Economy = field(default=Economy.OFF,
                                metadata={
                                    'base_type': 'boolean',
                                    'read_only': False,
                                })
