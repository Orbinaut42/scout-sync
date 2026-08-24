import sys
import logging
import re
from uuid import uuid4
import arrow
from flask import Flask, request, make_response, render_template
from apscheduler.schedulers.background import BackgroundScheduler
from ..config import config
from ..sync import sync, Event, WebCacheHandler

logging.basicConfig(
    filename=config.log_file,
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S',
    level=logging.INFO)

logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.getLogger('apscheduler').setLevel(logging.ERROR)
sys.excepthook = lambda exc_type, exc_value, exc_traceback: logging.exception(
    exc_type.__name__, exc_info=(exc_type, exc_value, exc_traceback))

_scheduler = None
_app = Flask(
    'scout_sync',
    template_folder='app/templates',
    static_folder='app/web',
    static_url_path='/list')


class _EditConflictError(ValueError):
    pass


def template_context(events=None, feedback=None):
    def format_datetime(value):
        if value is None:
            return {
                'date': '',
                'time': '',
                'date_input': '',
                'time_input': ''}

        local_value = value.to(config.timezone)
        has_time = local_value.hour or local_value.minute
        return {
            'date': local_value.format('ddd, DD.MM.YY', locale='de'),
            'time': local_value.format('HH:mm') if has_time else '',
            'date_input': local_value.format('YYYY-MM-DD'),
            'time_input': local_value.format('HH:mm') if has_time else ''}

    sorted_events = sorted(
        events or [],
        key=lambda event: (
            event.datetime.timestamp()
            if event.datetime is not None
            else float('inf')))

    return {
        'title': config.title,
        'events': sorted_events,
        'names': sorted(config.emails.keys()),
        'timezone': config.timezone,
        'current_time': arrow.now(config.timezone),
        'format_datetime': format_datetime,
        'feedback': feedback}


def _cached_events():
    return WebCacheHandler(config.web_cache_file).list_events()


@_app.route('/')
def _root():
    """ping access point"""

    return ''


@_app.route('/list')
def _list():
    """GET access point for the current game list
    Returns a empty shell for the events"""

    logging.info(f'List request from {request.access_route[0]}')
    return render_template('base.html', **template_context())


@_app.get('/list/events')
def _events():
    """Return the read-only event table fragment."""

    logging.info(f'Events fragment request from {request.access_route[0]}')
    cached_events = _cached_events()
    feedback = (
        {
            'kind': 'empty-cache',
            'message': 'Es sind noch keine Spieltermine verfügbar.'}
        if cached_events is None
        else None)
    return render_template(
        'fragments/event_table.html',
        **template_context(cached_events, feedback))


@_app.get('/list/edit')
def _edit():
    """Return the populated event editor fragment."""

    logging.info(f'Editor fragment request from {request.access_route[0]}')
    return render_template(
        'fragments/event_editor.html',
        **template_context(_cached_events()))


@_app.get('/list/edit/row')
def _edit_row():
    """Return a new manual event row fragment."""

    logging.info(f'New event row request from {request.access_route[0]}')
    event = Event(id=f'manual-{uuid4().hex}', datetime=None, scouters=[])
    return render_template(
        'fragments/event_row.html',
        event=event,
        new_event=True,
        **template_context([]))


@_app.post('/list/edit')
def _edit_submit():
    """Apply changed event fields submitted by the HTML editor form."""

    logging.info(f'Edit request from {request.access_route[0]}')

    def editor_feedback(kind, message):
        response = make_response(render_template(
            'fragments/toast.html',
            feedback={'kind': kind, 'message': message}))
        response.headers['HX-Retarget'] = '#toastContainer'
        response.headers['HX-Reswap'] = 'outerHTML'
        return response

    pw = config.submit_pw
    if pw == '' or pw != request.form.get('password'):
        return editor_feedback('password', 'Passwort falsch.')

    def parse_patches():
        """Parse and validate event patches from the submitted form."""

        event_field_pattern = re.compile(
            r'^events\[([^\]]+)\]\[(operation|date|time|location|league|opponent|scouters)\]$')

        patches = {}
        for key in request.form:
            if key == 'password':
                continue

            match = event_field_pattern.fullmatch(key)
            if match is None:
                raise ValueError(f'Unknown editor field: {key}')

            event_id, field = match.groups()
            if not event_id:
                raise ValueError('Event ID must not be empty')

            patch = patches.setdefault(
                event_id, {'operation': None, 'fields': {}})

            if field == 'operation':
                patch['operation'] = request.form.get(key)
            elif field == 'scouters':
                patch['fields'][field] = list(set(request.form.getlist(key)))
            else:
                patch['fields'][field] = request.form.get(key)

        return patches

    def validate_scouters(values):
        """Validate and normalize submitted scouter names."""

        values = [value for value in values if value]
        unknown = sorted(set(values) - set(Event._emails))
        if unknown:
            raise ValueError('Unbekannter Scouter im Änderungsantrag.')

        return values

    def validate_existing_event(current_event, fields):
        """Validate fields submitted for an existing event."""

        if current_event.schedule_info is not None:
            forbidden_fields = set(fields) - {'scouters'}
            if forbidden_fields:
                raise ValueError(
                    'Spiele aus dem Spielplan dürfen nur bei den '
                    'Scoutern geändert werden.')

    def update_event(current_event, fields):
        """Merge submitted fields into an existing event."""

        data = current_event.as_json()

        if 'date' in fields or 'time' in fields:
            if current_event.datetime is None:
                current_date = ''
                current_time = ''
            else:
                local_datetime = current_event.datetime.to(config.timezone)
                current_date = local_datetime.format('YYYY-MM-DD')
                current_time = (
                    local_datetime.format('HH:mm')
                    if local_datetime.hour or local_datetime.minute
                    else '')

            date = fields.get('date', current_date)
            time = fields.get('time', current_time) or '00:00'
            if not date:
                raise ValueError('Ein Spiel benötigt ein Datum.')
            data['datetime'] = f'{date}T{time}'

        for field in ('location', 'league', 'opponent'):
            if field in fields:
                data[field] = fields[field] or None

        if 'scouters' in fields:
            data['scouters'] = validate_scouters(fields['scouters'])

        return Event.from_json(data)

    def create_event(event_id, fields):
        """Validate and create a new manual event from submitted fields."""

        if event_id in current_events:
            raise ValueError(f'Event already exists: {event_id}')

        if not event_id.startswith('manual-') or event_id == 'manual-':
            raise ValueError('Neue Spiele benötigen eine manuelle ID.')

        date = fields.get('date', '')
        if not date:
            raise ValueError('Ein neues Spiel benötigt ein Datum.')

        return Event.from_json({
            'id': event_id,
            'datetime': f'{date}T{fields.get("time") or "00:00"}',
            'location': fields.get('location') or None,
            'league': fields.get('league') or None,
            'opponent': fields.get('opponent') or None,
            'scouters': validate_scouters(fields.get('scouters', [])),
            'schedule_info': None})

    def validate_deletable_event(current_event):
        """Validate that an event is allowed to be deleted."""

        if current_event.schedule_info is not None:
            raise ValueError(
                'Spiele aus dem Spielplan dürfen nicht gelöscht werden.')

    try:
        patches = parse_patches()
        cached_events = _cached_events() or []
        current_events = {event.id: event for event in cached_events}

        working_events = dict(current_events)
        working_order = [event.id for event in cached_events]

        for event_id, patch in patches.items():
            operation = patch['operation']
            fields = patch['fields']

            if operation == 'update':
                if event_id not in current_events:
                    raise _EditConflictError(
                        'Ein Spiel wurde inzwischen gelöscht. '
                        'Bitte lade die Bearbeitungsansicht neu.')

                current_event = current_events[event_id]
                validate_existing_event(current_event, fields)
                working_events[event_id] = update_event(current_event, fields)

            elif operation == 'create':
                new_event = create_event(event_id, fields)
                working_events[event_id] = new_event
                working_order.append(event_id)

            else:  # delete
                if event_id not in current_events:
                    continue

                validate_deletable_event(current_events[event_id])
                working_events.pop(event_id)
                working_order.remove(event_id)

        event_list = [working_events[event_id] for event_id in working_order]
        changed = [event.as_json() for event in cached_events] != [
            event.as_json() for event in event_list]

    except _EditConflictError as e:
        logging.warning(str(e))
        return editor_feedback('validation', str(e))

    except Exception as e:
        logging.exception(e)
        return editor_feedback('validation', 'Fehler beim Speichern der Spieltermine.')

    if changed:
        WebCacheHandler(config.web_cache_file).store_events(event_list)
        logging.info('Events cache updated from webpage.')

        if _scheduler is not None:
            _scheduler.add_job(sync, kwargs={'source': 'cache'})

    feedback = {
        'kind': 'success',
        'message': (
            'Die Spieltermine wurden gespeichert.'
            if changed else
            'Es wurden keine Änderungen vorgenommen.')}
    response = make_response(render_template(
        'fragments/event_table.html',
        **template_context(event_list, feedback)))
    response.headers['HX-Trigger-After-Swap'] = 'edit-mode-saved'
    return response


def app_startup():
    """app factory method launch function"""

    global _scheduler

    if _scheduler is None:
        _scheduler = BackgroundScheduler(
            timezone=config.timezone)
        _scheduler.start()

    interval = config.sync_interval
    if interval is not None:

        print(f'Scheduling sync job every {interval} minutes.')
        _scheduler.add_job(
            sync,
            'interval',
            kwargs={'source': 'schedule'},
            minutes=interval,
            start_date=arrow.get().shift(seconds=10).datetime,
            id='schedule-sync',
            replace_existing=True)

    return _app
