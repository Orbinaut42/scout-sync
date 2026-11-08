import configparser

import pytest

import scout_sync.scan_leagues as scan_leagues


def write_config(path):
    path.write_text(
        '[COMMON]\n'
        'title = Scouting Test\n'
        '\n'
        '[SCHEDULE_LEAGUES]\n'
        '# league_<league ID>_<teamPermanentId> = league name, '
        'league ID, teamPermanentId, teamSeasonId\n'
        'league_55802_163079 = BBL, 55802, 163079,\n'
        'league_12345_99999 = Missing, 12345, 99999,\n'
        '\n'
        '[SCHEDULE_ARENAS]\n'
        '106934 = Arena\n',
        encoding='utf-8')


@pytest.fixture
def config_file(monkeypatch, tmp_path):
    path = tmp_path / 'scout_sync.cfg'
    write_config(path)
    monkeypatch.setattr(scan_leagues, 'config_path', path)
    return path


def test_update_schedule_leagues_appends_new_leagues(config_file):
    scan_leagues._update_schedule_leagues({
        'NBBL Ulm': {
            'permanent_id': 163292,
            'league_ids': [56103, 56703]}})

    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read(config_file, encoding='utf-8')

    assert parser.get(
        'SCHEDULE_LEAGUES', 'league_55802_163079') == 'BBL, 55802, 163079,'
    assert parser.get(
        'SCHEDULE_LEAGUES', 'league_12345_99999') == 'Missing, 12345, 99999,'
    assert parser.get(
        'SCHEDULE_LEAGUES', 'league_56103_163292') == 'NBBL Ulm, 56103, 163292,'
    assert parser.get(
        'SCHEDULE_LEAGUES', 'league_56703_163292') == 'NBBL Ulm, 56703, 163292,'
    assert parser.get('SCHEDULE_ARENAS', '106934') == 'Arena'


def test_update_schedule_leagues_does_not_duplicate_configured_leagues(
        config_file):
    scan_leagues._update_schedule_leagues({
        'BBL': {
            'permanent_id': 163079,
            'league_ids': [55802]}})

    text = config_file.read_text(encoding='utf-8')
    assert text.count('BBL, 55802, 163079,') == 1
    assert text.count('league_55802_163079 =') == 1
    assert 'Missing, 12345, 99999,' in text


def test_update_config_writes_scan_results(monkeypatch, config_file):
    scan_config = configparser.ConfigParser(interpolation=None)
    scan_config.optionxform = str
    scan_config.read_dict({
        'NBBL Ulm': {
            'permanent_id': '163292',
            'verbandIds': '[100]'}})

    monkeypatch.setattr(scan_leagues, 'scan_config', scan_config)
    monkeypatch.setattr(
        scan_leagues,
        '_find_team_leagues',
        lambda session, params, permanent_id: [56103])

    scan_leagues.update_config()

    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read(config_file, encoding='utf-8')

    assert parser.get(
        'SCHEDULE_LEAGUES', 'league_56103_163292') == 'NBBL Ulm, 56103, 163292,'
    assert parser.get(
        'SCHEDULE_LEAGUES', 'league_12345_99999') == 'Missing, 12345, 99999,'
