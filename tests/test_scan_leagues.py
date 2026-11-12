import pytest

import scout_sync.scan_leagues as scan_leagues
from scout_sync.config import Config, config


LEAGUES_CSV = (
    'league_name,league_id,team_permanent_id,team_season_id\n'
    'BBL,55802,163079,\n'
    'Season Team,12345,,99999\n')


@pytest.fixture
def leagues_file(monkeypatch, tmp_path):
    path = tmp_path / 'schedule_leagues.csv'
    path.write_text(LEAGUES_CSV, encoding='utf-8')
    monkeypatch.setattr(
        type(config), 'schedule_leagues_file', property(lambda _: str(path)))
    return path


def test_schedule_leagues_reads_csv(leagues_file):
    assert config.schedule_leagues == [
        {
            'league_name': 'BBL',
            'league_id': 55802,
            'team_permanent_id': 163079,
            'team_season_id': None},
        {
            'league_name': 'Season Team',
            'league_id': 12345,
            'team_permanent_id': None,
            'team_season_id': 99999}]


def test_scan_leagues_merges_common_and_team_params(tmp_path):
    config_path = tmp_path / 'test.cfg'
    config_path.write_text(
        '[COMMON]\n'
        'schedule_leagues_file = leagues.csv\n'
        '[GOOGLE_API]\n'
        '[CALDAV]\n'
        '[SCAN_LEAGUES]\n'
        'token = 0\n'
        'verbandIds = [100]\n'
        '[SCAN_LEAGUES:NBBL Ulm]\n'
        'teamPermanentId = 163292\n'
        'verbandIds = [200]\n'
        'akgGeschlechtIds = ["2_1"]\n'
        '[SCHEDULE_ARENAS]\n'
        '106934 = Arena\n',
        encoding='utf-8')

    test_config = Config(str(config_path))

    assert test_config.scan_leagues == {
        'NBBL Ulm': {
            'token': 0,
            'verbandIds': [200],
            'teamPermanentId': 163292,
            'akgGeschlechtIds': ['2_1']}}
    assert test_config.schedule_leagues_file == str(tmp_path / 'leagues.csv')


def test_append_schedule_leagues_keeps_existing_leagues(leagues_file):
    scan_leagues._append_schedule_leagues({
        'NBBL Ulm': {
            'team_permanent_id': 163292,
            'league_ids': [56103, 56703]}})

    assert leagues_file.read_text(encoding='utf-8') == (
        LEAGUES_CSV
        + 'NBBL Ulm,56103,163292,\n'
        + 'NBBL Ulm,56703,163292,\n')


def test_append_schedule_leagues_does_not_duplicate_leagues(leagues_file):
    scan_leagues._append_schedule_leagues({
        'Renamed BBL': {
            'team_permanent_id': 163079,
            'league_ids': [55802, 55802]}})

    assert leagues_file.read_text(encoding='utf-8') == LEAGUES_CSV


def test_append_schedule_leagues_handles_missing_trailing_newline(
        leagues_file):
    leagues_file.write_text(LEAGUES_CSV.rstrip('\n'), encoding='utf-8')

    scan_leagues._append_schedule_leagues({
        'NBBL Ulm': {
            'team_permanent_id': 163292,
            'league_ids': [56103]}})

    assert leagues_file.read_text(encoding='utf-8') == (
        LEAGUES_CSV + 'NBBL Ulm,56103,163292,\n')


def test_append_schedule_leagues_creates_missing_file(leagues_file):
    leagues_file.unlink()

    scan_leagues._append_schedule_leagues({
        'NBBL Ulm': {
            'team_permanent_id': 163292,
            'league_ids': [56103]}})

    assert leagues_file.read_text(encoding='utf-8') == (
        'league_name,league_id,team_permanent_id,team_season_id\n'
        'NBBL Ulm,56103,163292,\n')


def test_update_schedule_leagues_writes_scan_results(
        monkeypatch, leagues_file):
    monkeypatch.setattr(
        type(config),
        'scan_leagues',
        property(lambda _: {
            'NBBL Ulm': {
                'teamPermanentId': 163292,
                'verbandIds': [100]}}))
    requested_params = []

    def find_team_leagues(session, params, team_permanent_id):
        requested_params.append((params, team_permanent_id))
        return [56103]

    monkeypatch.setattr(scan_leagues, '_find_team_leagues', find_team_leagues)

    scan_leagues.update_schedule_leagues()

    assert requested_params == [({'verbandIds': [100]}, 163292)]
    assert leagues_file.read_text(encoding='utf-8') == (
        LEAGUES_CSV + 'NBBL Ulm,56103,163292,\n')
