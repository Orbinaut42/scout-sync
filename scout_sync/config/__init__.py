import os
from configparser import ConfigParser

_CONFIG_FILE = 'scout_sync.cfg'

config = ConfigParser(
    converters={'list': lambda line: [int(v) if v.isdigit() else v for v in [w.strip() for w in line.split(',')]]},
    interpolation=None)
config.optionxform = str
config.read(os.path.join(__path__[0], _CONFIG_FILE), encoding='utf8')

__all__ = ['config']
