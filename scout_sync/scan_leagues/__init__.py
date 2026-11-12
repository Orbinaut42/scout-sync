import csv
import json
import logging
from pathlib import Path

import requests
from jsonschema import ValidationError, validate

from scout_sync.config import config


logger = logging.getLogger(__name__)


def _load_json(filename):
    path = Path(__file__).with_name(filename)
    with path.open(encoding='utf-8') as file:
        return json.load(file)


liga_list_schema = _load_json('liga_list_schema.json')
liga_schedule_schema = _load_json('liga_schedule_schema.json')

api_url = 'https://www.basketball-bund.net/rest'
list_url = f"{api_url}/wam/liga/list?startAtIndex={{start_idx}}"
schedule_url = f"{api_url}/competition/spielplan/id/{{league_id}}"


def _fetch_leagues(session, params):
    leagues = []
    start_idx = 0

    while True:
        url = list_url.format(start_idx=start_idx)
        response = session.post(
            url, json=params, timeout=config.schedule_request_timeout)

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


def _find_team_leagues(session, params, team_permanent_id):
    league_ids = []

    for league in _fetch_leagues(session, params):
        league_id = league['ligaId']
        url = schedule_url.format(league_id=league_id)
        response = session.get(url, timeout=config.schedule_request_timeout)

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

        if team_permanent_id in home_team_ids:
            league_ids.append(league_id)

    return league_ids


def _append_schedule_leagues(scan_results):
    leagues_path = Path(config.schedule_leagues_file)
    known_leagues = set()
    write_header = True
    prepend_newline = False

    if leagues_path.exists() and leagues_path.stat().st_size > 0:
        known_leagues = {
            (league['league_id'], league['team_permanent_id'])
            for league in config.schedule_leagues}
        write_header = False
        with leagues_path.open('rb') as file:
            file.seek(-1, 2)
            prepend_newline = file.read(1) != b'\n'

    new_leagues = []
    for team_name, team in scan_results.items():
        for league_id in team['league_ids']:
            if (league_id, team['team_permanent_id']) in known_leagues:
                continue

            known_leagues.add((league_id, team['team_permanent_id']))
            new_leagues.append([team_name, league_id, team['team_permanent_id'], ''])

    if not new_leagues:
        return

    with leagues_path.open('a', encoding='utf-8', newline='') as file:
        if prepend_newline:
            file.write('\n')

        writer = csv.writer(file, lineterminator='\n')
        if write_header:
            writer.writerow([
                'league_name', 'league_id', 'team_permanent_id', 'team_season_id'])

        writer.writerows(new_leagues)

    for league in new_leagues:
        logger.info('Added league: %s', league)


def update_schedule_leagues():
    scan_results = {}

    with requests.Session() as session:
        for team_name, params in config.scan_leagues.items():
            team_permanent_id = params.pop('teamPermanentId')
            league_ids = _find_team_leagues(session, params, team_permanent_id)
            scan_results[team_name] = {
                'team_permanent_id': team_permanent_id,
                'league_ids': league_ids}
            logger.info(
                'Leagues for %s (%s): %s',
                team_name, team_permanent_id, league_ids)

    _append_schedule_leagues(scan_results)
