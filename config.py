from configparser import ConfigParser

_CONFIG_FILE = 'scout_sync.cfg'

config = ConfigParser(
    converters={'list': lambda line: [int(v) if v.isdigit() else v for v in [w.strip() for w in line.split(',')]]})
config.optionxform = str
config.read(_CONFIG_FILE, encoding='utf8')
