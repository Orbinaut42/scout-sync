import json
import re

from werkzeug.datastructures import MultiDict

import scout_sync.app.app as app_module


def write_cache(cache_file, events):
    cache_file.write_text(
        json.dumps(events, ensure_ascii=False),
        encoding='utf8')


def cached_events():
    return [
        {
            'id': 'manual-late',
            'datetime': '2026-08-06T19:30',
            'location': '<b>Late</b>',
            'league': 'Liga B',
            'opponent': 'Opponent B',
            'scouters': ['Bob'],
            'schedule_info': None},
        {
            'id': 'dbb-early',
            'datetime': '2026-08-05T18:00',
            'location': 'Early Hall',
            'league': 'Liga A',
            'opponent': 'Opponent A',
            'scouters': ['Alice'],
            'schedule_info': {'match_id': 'match-1', 'league_id': 'league-1'}}]


def test_page_and_fragments_render_sorted_escaped_and_locked(app_env):
    write_cache(app_env['cache_file'], cached_events())
    client = app_env['client']

    page = client.get('/list')
    events_fragment = client.get('/list/hx/events')
    editor = client.get('/list/hx/edit')

    assert page.status_code == 200
    page_body = page.get_data(as_text=True)
    assert 'bootstrap-5.3.3.min.css' in page_body
    assert 'htmx-2.0.4.min.js' in page_body
    assert page_body.index('Early Hall') < page_body.index('&lt;b&gt;Late&lt;/b&gt;')
    assert '<b>Late</b>' not in page_body
    assert '05.08.26' in events_fragment.get_data(as_text=True)
    assert '06.08.26' in events_fragment.get_data(as_text=True)

    editor_body = editor.get_data(as_text=True)
    assert editor.status_code == 200
    assert 'value="Alice"' in editor_body
    assert 'value="Bob"' in editor_body
    assert 'statistics' not in editor_body.lower()
    assert 'statistik' not in editor_body.lower()

    manual_row = editor_body.split('data-game-id="manual-late"', 1)[1].split('</tr>', 1)[0]
    dbb_row = editor_body.split('data-game-id="dbb-early"', 1)[1].split('</tr>', 1)[0]
    assert 'disabled' not in manual_row
    assert 'readonly' not in manual_row
    assert 'disabled' in dbb_row
    assert 'readonly' in dbb_row
    assert manual_row.count('name="events[manual-late][scouters]"') == 3
    assert dbb_row.count('name="events[dbb-early][scouters]"') == 3


def test_new_manual_row_has_unique_server_id_and_three_scouters(app_env):
    client = app_env['client']

    first = client.get('/list/hx/edit/row').get_data(as_text=True)
    second = client.get('/list/hx/edit/row').get_data(as_text=True)
    first_id = re.search(r'data-game-id="(manual-[0-9a-f]{32})"', first).group(1)
    second_id = re.search(r'data-game-id="(manual-[0-9a-f]{32})"', second).group(1)

    assert first_id != second_id
    assert f'name="event_ids" value="{first_id}"' in first
    assert first.count(f'name="events[{first_id}][scouters]"') == 3
    assert second.count(f'name="events[{second_id}][scouters]"') == 3


def submit_data(password='secret', date='2026-08-10'):
    return MultiDict([
        ('password', password),
        ('event_ids', 'manual-submit'),
        ('events[manual-submit][date]', date),
        ('events[manual-submit][time]', '19:30'),
        ('events[manual-submit][location]', 'Main Hall'),
        ('events[manual-submit][league]', 'Liga C'),
        ('events[manual-submit][opponent]', 'Opponent C'),
        ('events[manual-submit][scouters]', 'Alice'),
        ('events[manual-submit][scouters]', ''),
        ('events[manual-submit][scouters]', 'Unknown')])


def test_submit_persists_cache_filters_scouters_and_enqueues_once(app_env):
    response = app_env['client'].post('/list/hx/edit', data=submit_data())

    saved = json.loads(app_env['cache_file'].read_text(encoding='utf8'))
    assert response.status_code == 200
    assert 'eventView' in response.get_data(as_text=True)
    assert 'gespeichert' in response.get_data(as_text=True)
    assert saved[0]['id'] == 'manual-submit'
    assert saved[0]['scouters'] == ['Alice']
    assert len(app_env['scheduler'].jobs) == 1
    assert app_env['scheduler'].jobs[0][0] == (app_module.sync,)
    assert app_env['scheduler'].jobs[0][1] == {'kwargs': {'source': 'cache'}}


def test_wrong_password_keeps_editor_target_and_does_not_write(app_env):
    original_cache = '[]'
    app_env['cache_file'].write_text(original_cache, encoding='utf8')

    response = app_env['client'].post(
        '/list/hx/edit',
        data=submit_data(password='wrong'))

    assert response.status_code == 200
    assert response.headers['HX-Retarget'] == '#editorFeedback'
    assert response.headers['HX-Reswap'] == 'innerHTML'
    assert 'Passwort' in response.get_data(as_text=True)
    assert app_env['cache_file'].read_text(encoding='utf8') == original_cache
    assert app_env['scheduler'].jobs == []


def test_invalid_date_keeps_editor_target_and_does_not_write(app_env):
    original_cache = '[]'
    app_env['cache_file'].write_text(original_cache, encoding='utf8')

    response = app_env['client'].post(
        '/list/hx/edit',
        data=submit_data(date='not-a-date'))

    assert response.status_code == 200
    assert response.headers['HX-Retarget'] == '#editorFeedback'
    assert response.headers['HX-Reswap'] == 'innerHTML'
    assert 'Eingaben' in response.get_data(as_text=True)
    assert app_env['cache_file'].read_text(encoding='utf8') == original_cache
    assert app_env['scheduler'].jobs == []


def test_duplicate_event_ids_return_validation_feedback(app_env):
    response = app_env['client'].post(
        '/list/hx/edit',
        data=MultiDict([
            ('password', 'secret'),
            ('event_ids', 'duplicate'),
            ('event_ids', 'duplicate'),
            ('events[duplicate][date]', '2026-08-10'),
            ('events[duplicate][time]', '19:30')]))

    assert response.status_code == 200
    assert response.headers['HX-Retarget'] == '#editorFeedback'
    assert 'Eingaben' in response.get_data(as_text=True)
    assert app_env['scheduler'].jobs == []


def test_migrated_routes_exist_and_legacy_json_routes_do_not(app_env):
    client = app_env['client']

    for path in ('/list/hx/events', '/list/hx/edit', '/list/hx/edit/row'):
        assert client.get(path).status_code == 200
    assert client.post('/list/hx/edit', data={'password': 'wrong'}).status_code == 200
    assert client.get('/list/events').status_code == 404
    assert client.post('/list/edit').status_code in (404, 405)
