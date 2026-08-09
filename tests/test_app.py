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
    events_fragment = client.get('/list/events')
    editor = client.get('/list/edit')
    summary_script = client.get('/list/assignment_summary.js')

    assert page.status_code == 200
    page_body = page.get_data(as_text=True)
    assert 'bootstrap-5.3.3.min.css' in page_body
    assert 'htmx-2.0.4.min.js' in page_body
    assert 'assignment_summary.js' in page_body
    assert 'hx-get="/list/events"' in page_body
    assert 'hx-trigger="load"' in page_body
    assert 'id="assignmentSummaryToggle"' in page_body
    assert 'role="switch"' in page_body
    assert 'aria-controls="assignmentSummary"' in page_body
    assert 'aria-expanded="false"' in page_body
    assert '<section id="assignmentSummary"' not in page_body
    assert 'Early Hall' not in page_body
    events_body = events_fragment.get_data(as_text=True)
    assert 'Early Hall' in events_body
    assert '&lt;b&gt;Late&lt;/b&gt;' in events_body
    assert 'table-hover' not in events_body
    assert 'id="assignmentSummary"' not in events_body
    assert 'id="assignmentSummaryTable"' not in events_body
    assert (
        "this.querySelector('.upcoming')?.scrollIntoView({ block: 'start' })"
        in events_body)
    assert 'hx-trigger="focus from:window"' in events_body
    assert 'hx-trigger="focus from:window"' not in editor.get_data(as_text=True)
    assert 'id="editorFeedback"' not in page_body
    assert 'id="editorFeedback"' not in editor.get_data(as_text=True)
    assert 'id="toastContainer"' not in page_body
    assert events_fragment.get_data(as_text=True).count('id="toastContainer"') == 1
    editor_body = editor.get_data(as_text=True)
    assert editor_body.count('id="toastContainer"') == 1
    assert 'class="toast show' not in editor_body
    assert '05.08.26' in events_fragment.get_data(as_text=True)
    assert '06.08.26' in events_fragment.get_data(as_text=True)

    assert editor.status_code == 200
    assert 'value="Alice"' in editor_body
    assert 'value="Bob"' in editor_body
    assert 'hx-on::after-swap=' in editor_body
    assert "this.lastElementChild?.scrollIntoView({ block: 'nearest' })" in editor_body
    assert editor_body.count('id="assignmentSummary"') == 1
    assert 'id="assignmentSummaryTable"' in editor_body
    assert 'id="assignmentSummaryBody"' in editor_body
    assert 'id="assignmentSummaryEmpty"' in editor_body
    assert 'Noch keine Scouter zugewiesen.' in editor_body
    assert 'BBL / Eurocup' in editor_body
    assert '>ProA<' in editor_body
    assert '>Sonstige<' in editor_body
    assert '>Gesamt<' in editor_body
    assert 'hidden>' in editor_body
    assert editor_body.count('data-assignment-league') == 2
    assert editor_body.count('data-assignment-scouter') == 6
    assert summary_script.status_code == 200
    assert 'leagueCategory' in summary_script.get_data(as_text=True)

    manual_row = editor_body.split('data-game-id="manual-late"', 1)[1].split('</tr>', 1)[0]
    dbb_row = editor_body.split('data-game-id="dbb-early"', 1)[1].split('</tr>', 1)[0]
    assert 'disabled' not in manual_row
    assert 'readonly' not in manual_row
    assert 'disabled' in dbb_row
    assert 'readonly' in dbb_row
    assert manual_row.count('name="events[manual-late][scouters]"') == 3
    assert dbb_row.count('name="events[dbb-early][scouters]"') == 3


def test_empty_cache_feedback_targets_footer(app_env):
    response = app_env['client'].get('/list/events')
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '<div id="toastContainer"' in body
    assert 'Es sind noch keine Spieltermine verfügbar.' in body
    assert '<section id="eventView"' in body
    assert 'class="toast show text-bg-warning"' in body
    assert 'setTimeout(() => this.remove(), 5000)' in body


def test_new_manual_row_has_unique_server_id_and_three_scouters(app_env):
    client = app_env['client']

    first = client.get('/list/edit/row').get_data(as_text=True)
    second = client.get('/list/edit/row').get_data(as_text=True)
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
    response = app_env['client'].post('/list/edit', data=submit_data())

    saved = json.loads(app_env['cache_file'].read_text(encoding='utf8'))
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'eventView' in body
    assert 'gespeichert' in body
    assert 'id="toastContainer"' in body
    assert 'class="toast show text-bg-success"' in body
    assert saved[0]['id'] == 'manual-submit'
    assert saved[0]['scouters'] == ['Alice']
    assert len(app_env['scheduler'].jobs) == 1
    assert app_env['scheduler'].jobs[0][0] == (app_module.sync,)
    assert app_env['scheduler'].jobs[0][1] == {'kwargs': {'source': 'cache'}}


def test_wrong_password_keeps_feedback_target_and_does_not_write(app_env):
    original_cache = '[]'
    app_env['cache_file'].write_text(original_cache, encoding='utf8')

    response = app_env['client'].post(
        '/list/edit',
        data=submit_data(password='wrong'))

    assert response.status_code == 200
    assert response.headers['HX-Retarget'] == '#toastContainer'
    assert response.headers['HX-Reswap'] == 'outerHTML'
    assert 'Passwort' in response.get_data(as_text=True)
    assert response.get_data(as_text=True).count('id="toastContainer"') == 1
    assert app_env['cache_file'].read_text(encoding='utf8') == original_cache
    assert app_env['scheduler'].jobs == []


def test_invalid_date_keeps_feedback_target_and_does_not_write(app_env):
    original_cache = '[]'
    app_env['cache_file'].write_text(original_cache, encoding='utf8')

    response = app_env['client'].post(
        '/list/edit',
        data=submit_data(date='not-a-date'))

    assert response.status_code == 200
    assert response.headers['HX-Retarget'] == '#toastContainer'
    assert response.headers['HX-Reswap'] == 'outerHTML'
    assert 'Fehler beim Speichern' in response.get_data(as_text=True)
    assert response.get_data(as_text=True).count('id="toastContainer"') == 1
    assert app_env['cache_file'].read_text(encoding='utf8') == original_cache
    assert app_env['scheduler'].jobs == []


def test_duplicate_event_ids_return_validation_feedback(app_env):
    response = app_env['client'].post(
        '/list/edit',
        data=MultiDict([
            ('password', 'secret'),
            ('event_ids', 'duplicate'),
            ('event_ids', 'duplicate'),
            ('events[duplicate][date]', '2026-08-10'),
            ('events[duplicate][time]', '19:30')]))

    assert response.status_code == 200
    assert response.headers['HX-Retarget'] == '#toastContainer'
    assert 'Fehler beim Speichern' in response.get_data(as_text=True)
    assert app_env['scheduler'].jobs == []


def test_migrated_routes_exist_and_hx_routes_do_not(app_env):
    client = app_env['client']

    for path in ('/list/events', '/list/edit', '/list/edit/row'):
        assert client.get(path).status_code == 200
    assert client.post('/list/edit', data={'password': 'wrong'}).status_code == 200
    assert client.get('/list/hx/events').status_code == 404
    assert client.post('/list/hx/edit').status_code in (404, 405)
