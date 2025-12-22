import os
import json
from configparser import ConfigParser

CONFIG_FILE = 'scout_sync_local.cfg'

config = ConfigParser(
    converters={'list': lambda line: [int(v) if v.isdigit() else v for v in [w.strip() for w in line.split(',')]]},
    interpolation=None)
config.optionxform = str
config.read(os.path.join(__path__[0], CONFIG_FILE), encoding='utf8')

# read email adresses and calendar auth infos from environment variables for Replit compatibility
for name, email in json.loads(os.getenv('EMAILS', default='{}')).items():
    if not config.has_option('EMAILS', name):
        config['EMAILS'][name] = email

if not config.get('COMMON', 'submit_pw', fallback=None):
    config['COMMON']['submit_pw'] = os.getenv('SUBMIT_PW', default='')

if not config.get('GOOGLE_API', 'oauth_info', fallback=None):
    config['GOOGLE_API']['oauth_info'] = os.getenv('OAUTH_INFO', default='')

if not config.get('GOOGLE_API', 'service_account_info', fallback=None):
    config['GOOGLE_API']['service_account_info'] = os.getenv('SERVICE_ACCOUNT_INFO', default='')

if not config.get('CALDAV', 'url', fallback=None):
    config['CALDAV']['url'] = os.getenv('CALDAV_URL', default='')

if not config.get('CALDAV', 'calendar_name', fallback=None):
    config['CALDAV']['calendar_name'] = os.getenv('CALDAV_CALENDAR_NAME', default='')

if not config.get('CALDAV', 'username', fallback=None):
    config['CALDAV']['username'] = os.getenv('CALDAV_USERNAME', default='')

if not config.get('CALDAV', 'password', fallback=None):
    config['CALDAV']['password'] = os.getenv('CALDAV_PASSWORD', default='')

__all__ = ['config']
