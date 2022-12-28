import os
import json
from configparser import ConfigParser

CONFIG_FILE = 'scout_sync.cfg'

config = ConfigParser(
    converters={'list': lambda line: [int(v) if v.isdigit() else v for v in [w.strip() for w in line.split(',')]]},
    interpolation=None)
config.optionxform = str
config.read(os.path.join(__path__[0], CONFIG_FILE), encoding='utf8')

# read email adresses and calendar auth infos from environment variables for Replit compatibility
for name, email in json.loads(os.getenv('EMAILS', default='{}')).items():
    if not config.has_option('EMAILS', name):
        config['EMAILS'][name] = email

if not config.get('CALENDAR', 'oauth_info', fallback=None):
    config['CALENDAR']['oauth_info'] = os.getenv('OAUTH_INFO', default='')

if not config.get('CALENDAR', 'service_account_info', fallback=None):
    config['CALENDAR']['service_account_info'] = os.getenv('SERVICE_ACCOUNT_INFO', default='')

__all__ = ['config']
