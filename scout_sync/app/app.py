import sys
import logging
import arrow
from flask import Flask, request, abort, render_template
from markupsafe import Markup, escape
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


def sorted_events(events):
    return sorted(
        events or [],
        key=lambda event: (
            event.datetime.timestamp()
            if event.datetime is not None
            else float('inf')))


def template_context(events, feedback=None):
    return {
        'title': config.get('COMMON', 'title'),
        'events': sorted_events(events),
        'names': sorted(config['EMAILS'].keys()),
        'timezone': config.get('COMMON', 'timezone'),
        'current_time': arrow.now(config.get('COMMON', 'timezone')),
        'format_datetime': format_datetime,
        'feedback': feedback}


def escape_json(j):
    if isinstance(j, str):
        j = str(escape(j))
    elif isinstance(j, list):
        for i in range(len(j)):
            j[i] = escape_json(j[i])
    elif isinstance(j, dict):
        for key in j:
            j[key] = escape_json(j[key])

    return j


def unescape_json(j):
    if isinstance(j, str):
        j = Markup(j).unescape()
    elif isinstance(j, list):
        for i in range(len(j)):
            j[i] = unescape_json(j[i])
    elif isinstance(j, dict):
        for key in j:
            j[key] = unescape_json(j[key])

    return j


@_app.route('/')
def root():
    """ping access point"""

    return ''


@_app.post('/list/edit')
def edit():
    """POST access point for edits from webpage

    Request data should be:
    {password: password, events: [json_events]}"""

    logging.info(f'Edit request from {request.access_route[0]}')

    try:
        request_data = unescape_json(request.json)
    except Exception as e:
        logging.exception(e)
        abort(400)

    pw = config.get('COMMON', 'submit_pw')
    if (pw == '' or pw != request_data.get('password')):
        abort(401)

    events = request_data.get('events')

    # check if event list is valid
    try:
        event_list = [Event.from_json(event) for event in events]

    except Exception as e:
        logging.exception(e)
        abort(400)

    WebCacheHandler(config.get('COMMON', 'web_cache_file')).store_events(event_list)
    logging.info('Events cache updated from webpage.')

    if _scheduler is None:
        raise RuntimeError('The application scheduler has not been initialized.')

    _scheduler.add_job(sync, kwargs={'source': 'cache'})

    return {}, 201


@_app.route('/list')
def _list():
    """GET access point for the current game list
    Returns a HTML document with the current events"""

    logging.info(f'List request from {request.access_route[0]}')
    cached_events = WebCacheHandler(config.get('COMMON', 'web_cache_file')).list_events()
    feedback = (
        {
            'kind': 'empty-cache',
            'id': 'emptyCacheMessage',
            'message': 'Es sind noch keine Spieltermine verfügbar.'}
        if cached_events is None
        else None)

    return render_template('list.html', **template_context(cached_events, feedback))


@_app.route('/list/events')
def events():
    """GET access point for the current table contents
    Returns the cached events in JSON format"""

    logging.info(f'Events update request from {request.access_route[0]}')

    try:
        events = escape_json(
            WebCacheHandler(config.get('COMMON', 'web_cache_file')).json_events()
        )
    except Exception as e:
        logging.exception(e)
        abort(400)

    if events is None:
        abort(500, description='Events have not been cached yet.')

    return events


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
