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
    filename=config.get('COMMON', 'log_file'),
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


def template_context(events=None, feedback=None):
    def format_datetime(value):
        if value is None:
            return {
                'date': '',
                'time': '',
                'date_input': '',
                'time_input': ''}

        local_value = value.to(config.get('COMMON', 'timezone'))
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
        'title': config.get('COMMON', 'title'),
        'events': sorted_events,
        'names': sorted(config['EMAILS'].keys()),
        'timezone': config.get('COMMON', 'timezone'),
        'current_time': arrow.now(config.get('COMMON', 'timezone')),
        'format_datetime': format_datetime,
        'feedback': feedback}


def _cached_events():
    return WebCacheHandler(config.get('COMMON', 'web_cache_file')).list_events()


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
            'id': 'emptyCacheMessage',
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
        **template_context([]))


@_app.post('/list/edit')
def _edit_submit():
    """Store events submitted by the HTML editor form."""

    logging.info(f'Edit request from {request.access_route[0]}')

    def editor_feedback(kind, message):
        response = make_response(render_template(
            'fragments/message.html',
            feedback={'kind': kind, 'id': 'editorFeedbackMessage', 'message': message}))
        response.headers['HX-Retarget'] = '#editorFeedback'
        response.headers['HX-Reswap'] = 'innerHTML'
        return response

    event_field_pattern = re.compile(
        r'^events\[([^\]]+)\]\[(date|time|location|league|opponent|scouters)\]$')

    pw = config.get('COMMON', 'submit_pw')
    if pw == '' or pw != request.form.get('password'):
        return editor_feedback('password', 'Passwort falsch.')

    try:
        rows = {}
        for event_id in request.form.getlist('event_ids'):
            if event_id in rows:
                raise ValueError(f'Duplicate event ID: {event_id}')
            rows[event_id] = {}

        for key in request.form:
            match = event_field_pattern.fullmatch(key)
            if match is None:
                continue

            event_id, field = match.groups()
            if event_id not in rows:
                raise ValueError(f'Event field has no event ID: {event_id}')

            rows[event_id][field] = (
                request.form.getlist(key)
                if field == 'scouters'
                else request.form.get(key, ''))

        event_list = [
            Event.from_json({
                'id': event_id,
                'datetime': f'{row.get('date')}T{row.get('time') or '00:00'}',
                'location': row.get('location') or None,
                'league': row.get('league') or None,
                'opponent': row.get('opponent') or None,
                'scouters': row.get('scouters') or [],
                'schedule_info': None})
            for event_id, row in rows.items()]
    except Exception as e:
        logging.exception(e)
        return editor_feedback('validation', 'Fehler beim Speichern der Spieltermine.')

    WebCacheHandler(config.get('COMMON', 'web_cache_file')).store_events(event_list)
    logging.info('Events cache updated from webpage.')

    if _scheduler is not None:
        _scheduler.add_job(sync, kwargs={'source': 'cache'})

    return render_template(
        'fragments/event_table.html',
        **template_context(
            event_list,
            {
                'kind': 'success',
                'id': 'saveFeedback',
                'message': 'Die Spieltermine wurden gespeichert.'}))


def app_startup():
    """app factory method launch function"""

    global _scheduler

    if _scheduler is None:
        _scheduler = BackgroundScheduler(
            timezone=config.get('COMMON', 'timezone'))
        _scheduler.start()

    if 'SYNC_JOB' in config:
        interval = config.getint('SYNC_JOB', 'interval')

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
