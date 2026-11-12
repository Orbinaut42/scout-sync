import csv
import json
import os
from configparser import ConfigParser

CONFIG_FILE = 'scout_sync_local.cfg'


class Config:
    """Provides application configuration values."""

    def __init__(self, config_file):
        config_parser = ConfigParser(interpolation=None)
        config_parser.optionxform = str
        config_path = os.path.join(__path__[0], config_file)
        config_parser.read(config_path, encoding='utf8')

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

        if not config_parser.get('CALDAV', 'url', fallback=None):
            config_parser['CALDAV']['url'] = os.getenv(
                'CALDAV_URL', default='')

        if not config_parser.get('CALDAV', 'calendar_name', fallback=None):
            config_parser['CALDAV']['calendar_name'] = os.getenv(
                'CALDAV_CALENDAR_NAME', default='')

        if not config_parser.get('CALDAV', 'username', fallback=None):
            config_parser['CALDAV']['username'] = os.getenv(
                'CALDAV_USERNAME', default='')

        if not config_parser.get('CALDAV', 'password', fallback=None):
            config_parser['CALDAV']['password'] = os.getenv(
                'CALDAV_PASSWORD', default='')

        self._config_parser = config_parser
        self._config_dir = os.path.dirname(config_path)

    @property
    def log_file(self):
        return self._config_parser.get('COMMON', 'log_file')

    @property
    def timezone(self):
        return self._config_parser.get('COMMON', 'timezone')

    @property
    def title(self):
        return self._config_parser.get('COMMON', 'title')

    @property
    def port(self):
        return self._config_parser.getint('COMMON', 'port')

    @property
    def schedule_request_timeout(self):
        return self._config_parser.getint('COMMON', 'schedule_request_timeout')

    @property
    def web_cache_file(self):
        return self._config_parser.get('COMMON', 'web_cache_file')

    @property
    def submit_pw(self):
        return self._config_parser.get('COMMON', 'submit_pw')

    @property
    def calendar_backend(self):
        backend = self._config_parser.get(
            'COMMON', 'calendar_backend', fallback='caldav').strip().lower()
        if backend not in ('google', 'caldav'):
            raise ValueError(
                f"Invalid calendar_backend '{backend}': "
                f"expected 'google' or 'caldav'")

        return backend

    @property
    def oauth_info(self):
        return self._config_parser.get('GOOGLE_API', 'oauth_info', fallback=None)

    @property
    def service_account_info(self):
        return self._config_parser.get(
            'GOOGLE_API', 'service_account_info', fallback=None)

    @property
    def calendar_id(self):
        return self._config_parser.get('CALENDAR', 'id')

    @property
    def caldav_url(self):
        return self._config_parser.get('CALDAV', 'url', fallback=None)

    @property
    def caldav_calendar_name(self):
        return self._config_parser.get('CALDAV', 'calendar_name', fallback=None)

    @property
    def caldav_username(self):
        return self._config_parser.get('CALDAV', 'username', fallback=None)

    @property
    def caldav_password(self):
        return self._config_parser.get('CALDAV', 'password', fallback=None)

    @property
    def schedule_leagues_file(self):
        return os.path.join(
            self._config_dir,
            self._config_parser.get('COMMON', 'schedule_leagues_file'))

    @property
    def schedule_leagues(self):
        with open(self.schedule_leagues_file, encoding='utf8', newline='') as file:
            return [
                {
                    'league_name': row['league_name'],
                    'league_id': int(row['league_id']),
                    'team_permanent_id': (
                        int(row['team_permanent_id'])
                        if row['team_permanent_id'] else None),
                    'team_season_id': (
                        int(row['team_season_id'])
                        if row['team_season_id'] else None)}
                for row in csv.DictReader(file, skipinitialspace=True)]

    @property
    def scan_leagues(self):
        def parse_value(value):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value

        prefix = 'SCAN_LEAGUES:'
        common_params = (
            self._config_parser['SCAN_LEAGUES']
            if self._config_parser.has_section('SCAN_LEAGUES')
            else {})
        return {
            section.removeprefix(prefix): {
                key: parse_value(value)
                for key, value in {
                    **common_params,
                    **self._config_parser[section]}.items()}
            for section in self._config_parser.sections()
            if section.startswith(prefix)}

    @property
    def schedule_arenas(self):
        return dict(self._config_parser.items('SCHEDULE_ARENAS'))

    @property
    def emails(self):
        return dict(self._config_parser.items('EMAILS'))

    @property
    def sync_interval(self):
        if not self._config_parser.has_section('SYNC_JOB'):
            return None
        return self._config_parser.getint('SYNC_JOB', 'interval', fallback=None)

    @property
    def scan_leagues_interval(self):
        return self._config_parser.getint(
            'SCAN_LEAGUES_JOB', 'interval', fallback=None)


config = Config(CONFIG_FILE)

__all__ = ['config']
