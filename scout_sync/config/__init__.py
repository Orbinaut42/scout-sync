import os
import json
from configparser import ConfigParser

CONFIG_FILE = 'scout_sync.cfg'


class Config:
    """Provides application configuration values."""

    def __init__(self, config_file):
        config_parser = ConfigParser(
            converters={'list': lambda line: [
                int(v)
                if v.isdigit()
                else v
                for v in [w.strip() for w in line.split(',')]]},
            interpolation=None)
        config_parser.optionxform = str
        config_parser.read(os.path.join(__path__[0], config_file), encoding='utf8')

        # read email adresses and calendar auth infos from environment variables
        for name, email in json.loads(os.getenv('EMAILS', default='{}')).items():
            if not config_parser.has_option('EMAILS', name):
                config_parser['EMAILS'][name] = email

        if not config_parser.get('COMMON', 'submit_pw', fallback=None):
            config_parser['COMMON']['submit_pw'] = os.getenv(
                'SUBMIT_PW', default='')

        if not config_parser.get('GOOGLE_API', 'oauth_info', fallback=None):
            config_parser['GOOGLE_API']['oauth_info'] = os.getenv(
                'OAUTH_INFO', default='')

        if not config_parser.get('GOOGLE_API', 'service_account_info', fallback=None):
            config_parser['GOOGLE_API']['service_account_info'] = os.getenv(
                'SERVICE_ACCOUNT_INFO', default='')

        self.__config_parser = config_parser

    @property
    def log_file(self):
        return self.__config_parser.get('COMMON', 'log_file')

    @property
    def timezone(self):
        return self.__config_parser.get('COMMON', 'timezone')

    @property
    def title(self):
        return self.__config_parser.get('COMMON', 'title')

    @property
    def port(self):
        return self.__config_parser.getint('COMMON', 'port')

    @property
    def schedule_request_timeout(self):
        return self.__config_parser.getint('COMMON', 'schedule_request_timeout')

    @property
    def web_cache_file(self):
        return self.__config_parser.get('COMMON', 'web_cache_file')

    @property
    def submit_pw(self):
        return self.__config_parser.get('COMMON', 'submit_pw')

    @property
    def simulate(self):
        return self.__config_parser.getboolean('COMMON', 'simulate')

    @property
    def oauth_info(self):
        return self.__config_parser.get('GOOGLE_API', 'oauth_info', fallback=None)

    @property
    def service_account_info(self):
        return self.__config_parser.get(
            'GOOGLE_API', 'service_account_info', fallback=None)

    @property
    def calendar_id(self):
        return self.__config_parser.get('CALENDAR', 'id')

    @property
    def schedule_leagues(self):
        return [
            dict(zip(
                ['league_name', 'league_id', 'team_permanent_id', 'team_season_id'],
                self.__config_parser.getlist('SCHEDULE_LEAGUES', name)))
            for name, _ in self.__config_parser.items('SCHEDULE_LEAGUES')]

    @property
    def schedule_arenas(self):
        return dict(self.__config_parser.items('SCHEDULE_ARENAS'))

    @property
    def emails(self):
        return dict(self.__config_parser.items('EMAILS'))

    @property
    def sync_interval(self):
        if not self.__config_parser.has_section('SYNC_JOB'):
            return None
        return self.__config_parser.getint('SYNC_JOB', 'interval', fallback=None)


config = Config(CONFIG_FILE)

__all__ = ['config']
