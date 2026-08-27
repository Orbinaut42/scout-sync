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
    editor_script = client.get('/list/event_editor.js')
    toast_script = client.get('/list/toast.js')

    assert page.status_code == 200
    page_body = page.get_data(as_text=True)
    assert 'bootstrap-5.3.3.min.css' in page_body
    assert 'htmx-2.0.4.min.js' in page_body
    assert 'toast.js' in page_body
    assert 'assignment_summary.js' in page_body
    assert 'event_editor.js' in page_body
    assert 'hx-on:edit-mode-saved=' in page_body
    assert 'hx-get="/list/events"' in page_body
    assert 'hx-trigger="load"' in page_body
    assert 'id="assignmentSummaryToggle"' in page_body
    assert 'role="switch"' in page_body
    assert 'aria-controls="assignmentSummary"' in page_body
    assert 'aria-expanded="false"' in page_body
    assert 'stroke-width="2"' in page_body
    assert '<section id="assignmentSummary"' in page_body
    assert 'id="assignmentSummaryTable"' in page_body
    assert 'id="assignmentSummaryBody"' in page_body
    assert 'id="passwordVisibilityToggle"' in page_body
    assert 'aria-controls="pwInput"' in page_body
    assert 'BBL / Euro' in page_body
    assert '>ProA<' in page_body
    assert '>Sonstige<' in page_body
    assert '>Gesamt<' in page_body
    assert 'hidden>' in page_body
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
    assert (
        'hx-on::after-request="document.getElementById(\'pwInput\').value = \'\'"'
        in editor_body)
    assert "this.lastElementChild?.scrollIntoView({ block: 'nearest' })" in editor_body
    assert 'id="assignmentSummary"' not in editor_body
    assert editor_body.count('data-assignment-league') == 2
    assert editor_body.count('data-assignment-scouter') == 6
    assert 'name="event_ids"' not in editor_body
    assert 'data-event-field="date"' in editor_body
    assert 'data-original-scouters=' in editor_body
    assert "data-original-scouters='[\"Alice\"]'" in editor_body
    assert "data-original-scouters='[\"Bob\"]'" in editor_body
    assert summary_script.status_code == 200
    assert 'leagueCategory' in summary_script.get_data(as_text=True)
    assert editor_script.status_code == 200
    assert 'htmx:configRequest' in editor_script.get_data(as_text=True)
    assert 'setPasswordVisibility' in editor_script.get_data(as_text=True)
    assert toast_script.status_code == 200
    assert 'htmx:load' in toast_script.get_data(as_text=True)

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


def test_new_manual_row_has_unique_server_id_and_three_scouters(app_env):
    client = app_env['client']

    first = client.get('/list/edit/row').get_data(as_text=True)
    second = client.get('/list/edit/row').get_data(as_text=True)
    first_id = re.search(r'data-game-id="(manual-[0-9a-f]{32})"', first).group(1)
    second_id = re.search(r'data-game-id="(manual-[0-9a-f]{32})"', second).group(1)

    assert first_id != second_id
    assert f'data-game-id="{first_id}"' in first
    assert 'data-new-event="true"' in first
    assert 'data-dirty="false"' in first
    assert first.count(f'name="events[{first_id}][scouters]"') == 3
    assert second.count(f'name="events[{second_id}][scouters]"') == 3


def event_patch(event_id, operation='update', password='secret', **fields):
    data = [
        ('password', password),
        (f'events[{event_id}][operation]', operation)]
    for field, value in fields.items():
        values = value if field == 'scouters' else [value]
        for field_value in values:
            data.append((f'events[{event_id}][{field}]', field_value))
    return MultiDict(data)


def submit_data(password='secret', date='2026-08-10'):
    return event_patch(
        'manual-submit',
        operation='create',
        password=password,
        date=date,
        time='19:30',
        location='Main Hall',
        league='Liga C',
        opponent='Opponent C',
        scouters=['Alice'])


def test_submit_creates_event_and_enqueues_once(app_env):
    response = app_env['client'].post('/list/edit', data=submit_data())

    saved = json.loads(app_env['cache_file'].read_text(encoding='utf8'))
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert response.headers['HX-Trigger-After-Swap'] == 'edit-mode-saved'
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
    assert 'HX-Trigger-After-Swap' not in response.headers
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


def test_scouters_only_patch_preserves_other_fields_and_schedule_info(app_env):
    write_cache(app_env['cache_file'], cached_events())

    response = app_env['client'].post(
        '/list/edit',
        data=event_patch('dbb-early', scouters=['Bob']))

    saved = {
        event['id']: event
        for event in json.loads(
            app_env['cache_file'].read_text(encoding='utf8'))}
    assert response.status_code == 200
    assert saved['dbb-early']['datetime'].startswith('2026-08-05 18:00:00')
    assert saved['dbb-early']['location'] == 'Early Hall'
    assert saved['dbb-early']['league'] == 'Liga A'
    assert saved['dbb-early']['opponent'] == 'Opponent A'
    assert saved['dbb-early']['scouters'] == ['Bob']
    assert saved['dbb-early']['schedule_info'] == {
        'match_id': 'match-1',
        'league_id': 'league-1'}
    assert len(app_env['scheduler'].jobs) == 1


def test_empty_scouter_patch_clears_scouters_without_replacing_event(app_env):
    write_cache(app_env['cache_file'], cached_events())

    response = app_env['client'].post(
        '/list/edit',
        data=MultiDict([
            ('password', 'secret'),
            ('events[manual-late][operation]', 'update'),
            ('events[manual-late][scouters]', '')]))

    saved = {
        event['id']: event
        for event in json.loads(
            app_env['cache_file'].read_text(encoding='utf8'))}
    assert response.status_code == 200
    assert saved['manual-late']['location'] == '<b>Late</b>'
    assert saved['manual-late']['scouters'] == []
    assert len(app_env['scheduler'].jobs) == 1


def test_date_only_patch_preserves_existing_time(app_env):
    write_cache(app_env['cache_file'], cached_events())

    app_env['client'].post(
        '/list/edit',
        data=event_patch('manual-late', date='2026-08-11'))

    saved = json.loads(app_env['cache_file'].read_text(encoding='utf8'))
    manual_event = next(event for event in saved if event['id'] == 'manual-late')
    assert manual_event['datetime'].startswith('2026-08-11 19:30:00')


def test_sequential_disjoint_patches_preserve_both_changes(app_env):
    write_cache(app_env['cache_file'], cached_events())

    first = app_env['client'].post(
        '/list/edit',
        data=event_patch('manual-late', location='Updated Hall'))
    second = app_env['client'].post(
        '/list/edit',
        data=event_patch('manual-late', league='Updated League'))

    saved = json.loads(app_env['cache_file'].read_text(encoding='utf8'))
    manual_event = next(event for event in saved if event['id'] == 'manual-late')
    assert first.status_code == 200
    assert second.status_code == 200
    assert manual_event['location'] == 'Updated Hall'
    assert manual_event['league'] == 'Updated League'
    assert len(app_env['scheduler'].jobs) == 2


def test_same_field_patches_use_last_write_wins(app_env):
    write_cache(app_env['cache_file'], cached_events())

    app_env['client'].post(
        '/list/edit',
        data=event_patch('manual-late', opponent='First Opponent'))
    app_env['client'].post(
        '/list/edit',
        data=event_patch('manual-late', opponent='Second Opponent'))

    saved = json.loads(app_env['cache_file'].read_text(encoding='utf8'))
    manual_event = next(event for event in saved if event['id'] == 'manual-late')
    assert manual_event['opponent'] == 'Second Opponent'


def test_omitted_events_are_not_deleted(app_env):
    write_cache(app_env['cache_file'], cached_events())

    app_env['client'].post(
        '/list/edit',
        data=event_patch('manual-late', location='Updated Hall'))

    saved = json.loads(app_env['cache_file'].read_text(encoding='utf8'))
    assert {event['id'] for event in saved} == {'manual-late', 'dbb-early'}


def test_explicit_manual_delete_removes_only_that_event(app_env):
    write_cache(app_env['cache_file'], cached_events())

    response = app_env['client'].post(
        '/list/edit',
        data=event_patch('manual-late', operation='delete'))

    saved = json.loads(app_env['cache_file'].read_text(encoding='utf8'))
    assert response.status_code == 200
    assert [event['id'] for event in saved] == ['dbb-early']
    assert len(app_env['scheduler'].jobs) == 1


def test_delete_of_missing_event_is_idempotent(app_env):
    app_env['cache_file'].write_text(
        json.dumps([cached_events()[1]], ensure_ascii=False),
        encoding='utf8')
    current_cache = app_env['cache_file'].read_text(encoding='utf8')

    response = app_env['client'].post(
        '/list/edit',
        data=event_patch('manual-late', operation='delete'))

    assert response.status_code == 200
    assert app_env['cache_file'].read_text(encoding='utf8') == current_cache
    assert app_env['scheduler'].jobs == []


def test_update_of_missing_event_returns_reload_feedback_without_write(app_env):
    original_cache = json.dumps([cached_events()[1]], ensure_ascii=False)
    app_env['cache_file'].write_text(original_cache, encoding='utf8')

    response = app_env['client'].post(
        '/list/edit',
        data=event_patch('manual-late', location='Updated Hall'))

    assert response.status_code == 200
    assert 'gelöscht' in response.get_data(as_text=True)
    assert app_env['cache_file'].read_text(encoding='utf8') == original_cache
    assert app_env['scheduler'].jobs == []


def test_schedule_event_fields_cannot_be_changed_by_request(app_env):
    original_cache = json.dumps(cached_events(), ensure_ascii=False)
    app_env['cache_file'].write_text(original_cache, encoding='utf8')

    response = app_env['client'].post(
        '/list/edit',
        data=event_patch('dbb-early', location='Changed Hall'))

    assert response.status_code == 200
    assert 'Fehler beim Speichern' in response.get_data(as_text=True)
    assert app_env['cache_file'].read_text(encoding='utf8') == original_cache
    assert app_env['scheduler'].jobs == []


def test_schedule_event_cannot_be_deleted_by_request(app_env):
    original_cache = json.dumps(cached_events(), ensure_ascii=False)
    app_env['cache_file'].write_text(original_cache, encoding='utf8')

    response = app_env['client'].post(
        '/list/edit',
        data=event_patch('dbb-early', operation='delete'))

    assert response.status_code == 200
    assert 'Fehler beim Speichern' in response.get_data(as_text=True)
    assert app_env['cache_file'].read_text(encoding='utf8') == original_cache
    assert app_env['scheduler'].jobs == []


def test_new_event_without_scouters_uses_empty_list(app_env):
    response = app_env['client'].post(
        '/list/edit',
        data=event_patch(
            'manual-empty',
            operation='create',
            date='2026-08-10'))

    saved = json.loads(app_env['cache_file'].read_text(encoding='utf8'))
    assert response.status_code == 200
    assert saved[0]['id'] == 'manual-empty'
    assert saved[0]['scouters'] == []


def test_unknown_scouter_rejects_entire_patch(app_env):
    original_cache = json.dumps(cached_events(), ensure_ascii=False)
    app_env['cache_file'].write_text(original_cache, encoding='utf8')

    response = app_env['client'].post(
        '/list/edit',
        data=event_patch('manual-late', scouters=['Unknown']))

    assert response.status_code == 200
    assert 'Fehler beim Speichern' in response.get_data(as_text=True)
    assert app_env['cache_file'].read_text(encoding='utf8') == original_cache
    assert app_env['scheduler'].jobs == []


def test_unknown_patch_field_rejects_without_deleting_cached_events(app_env):
    original_cache = json.dumps(cached_events(), ensure_ascii=False)
    app_env['cache_file'].write_text(original_cache, encoding='utf8')

    response = app_env['client'].post(
        '/list/edit',
        data=MultiDict([
            ('password', 'secret'),
            ('events[manual-late][operation]', 'update'),
            ('events[manual-late][schedule_info]', 'None')]))

    assert response.status_code == 200
    assert 'Fehler beim Speichern' in response.get_data(as_text=True)
    assert app_env['cache_file'].read_text(encoding='utf8') == original_cache
    assert app_env['scheduler'].jobs == []


def test_noop_patch_does_not_write_or_enqueue(app_env):
    original_cache = json.dumps(cached_events(), ensure_ascii=False)
    app_env['cache_file'].write_text(original_cache, encoding='utf8')

    response = app_env['client'].post(
        '/list/edit',
        data=event_patch('manual-late'))

    assert response.status_code == 200
    assert 'keine Änderungen' in response.get_data(as_text=True)
    assert app_env['cache_file'].read_text(encoding='utf8') == original_cache
    assert app_env['scheduler'].jobs == []


def test_migrated_routes_exist_and_hx_routes_do_not(app_env):
    client = app_env['client']

    for path in ('/list/events', '/list/edit', '/list/edit/row'):
        assert client.get(path).status_code == 200
    assert client.post('/list/edit', data={'password': 'wrong'}).status_code == 200
    assert client.get('/list/hx/events').status_code == 404
    assert client.post('/list/hx/edit').status_code in (404, 405)
