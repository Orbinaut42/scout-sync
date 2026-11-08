import configparser
import json
import logging
from pathlib import Path

import requests
from jsonschema import ValidationError, validate


logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def _load_json(filename):
    path = Path(__file__).with_name(filename)
    with path.open(encoding='utf-8') as file:
        return json.load(file)


def _parse_config_value(value):
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


liga_list_schema = _load_json('liga_list_schema.json')
liga_schedule_schema = _load_json('liga_schedule_schema.json')

scan_config = configparser.ConfigParser(interpolation=None)
scan_config.optionxform = str
scan_config.read(Path(__file__).with_name('config.cfg'), encoding='utf-8')

api_url = 'https://www.basketball-bund.net/rest'
list_url = f"{api_url}/wam/liga/list?startAtIndex={{start_idx}}"
schedule_url = f"{api_url}/competition/spielplan/id/{{league_id}}"
config_path = Path(__file__).parents[1] / 'config' / 'scout_sync.cfg'
schedule_leagues_section = 'SCHEDULE_LEAGUES'


def _fetch_leagues(session, params):
    leagues = []
    start_idx = 0

    while True:
        url = list_url.format(start_idx=start_idx)
        response = session.post(url, json=params)

        if response.status_code != 200:
            logger.error('Error: %s - %s', response.status_code, response.text)
            break

        response_content = response.json()
        try:
            validate(instance=response_content, schema=liga_list_schema)
        except ValidationError as error:
            logger.error('Invalid response JSON: %s', error.message)
            break

        response_data = response_content['data']
        leagues.extend(response_data['ligen'])

        if not response_data['hasMoreData']:
            break

        start_idx += response_data['size']

    return leagues


def _find_team_leagues(session, params, permanent_id):
    league_ids = []

    for league in _fetch_leagues(session, params):
        league_id = league['ligaId']
        url = schedule_url.format(league_id=league_id)
        response = session.get(url)

        if response.status_code != 200:
            logger.error(
                'Error fetching schedule for league %s: %s - %s',
                league_id, response.status_code, response.text)
            continue

        response_data = response.json()
        try:
            validate(instance=response_data, schema=liga_schedule_schema)
        except ValidationError as error:
            logger.error(
                'Invalid schedule JSON for league %s: %s',
                league_id, error.message)
            continue

        home_team_ids = [
            match['homeTeam']['teamPermanentId']
            for match in response_data['data']['matches']]

        if permanent_id in home_team_ids:
            league_ids.append(league_id)

    return league_ids


def _update_schedule_leagues(scan_results):
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read(config_path, encoding='utf-8')

    if not parser.has_section(schedule_leagues_section):
        parser.add_section(schedule_leagues_section)

    leagues = parser[schedule_leagues_section]
    new_leagues = []

    for team_name, team in scan_results.items():
        permanent_id = str(team['permanent_id'])
        for league_id in team['league_ids']:
            key = f'league_{league_id}_{permanent_id}'
            if key in leagues:
                continue

            value = f'{team_name}, {league_id}, {permanent_id},'
            leagues[key] = value
            new_leagues.append(f'{key} = {value}')

    if new_leagues:
        with config_path.open('w', encoding='utf-8') as file:
            parser.write(file)

        for league in new_leagues:
            logger.info('Added league to %s: %s', config_path, league)


def update_config():
    scan_results = {}

    with requests.Session() as session:
        for team_name in scan_config.sections():
            team = scan_config[team_name]
            permanent_id = team.getint('permanent_id')
            params = {
                key: _parse_config_value(value)
                for key, value in team.items()
                if key != 'permanent_id'
            }
            league_ids = _find_team_leagues(session, params, permanent_id)
            scan_results[team_name] = {
                'permanent_id': permanent_id,
                'league_ids': league_ids}
            logger.info(
                'Leagues with %s as home team (%s): %s',
                team_name, permanent_id, league_ids)

    _update_schedule_leagues(scan_results)
