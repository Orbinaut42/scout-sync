import sys
import os
import logging
import json
import arrow
from flask import Flask, request, abort
from markupsafe import escape
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

scheduler = BackgroundScheduler(timzone=config.get('COMMON', 'timezone'))
scheduler.start()

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

app = Flask(
    'scout_sync',
    static_folder='app/static',
    static_url_path='')

@app.route('/')
def root():
    """ping access point"""

    return ''

@app.post('/list/edit')
def edit():
    """POST access point for edits from webpage
    
    Request data should be:
    {password: password, events: [json_events]}"""

    logging.info(f'Edit request from {request.access_route[0]}')
    try:
        request_data = escape_json(request.json)
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
    logging.info(f'Events cache updated from webpage.')

    scheduler.add_job(sync, kwargs={'source': 'cache'})

    return {}, 201


@app.route('/list')
def _list():
    """GET access point for the current game list
    Returns a HTML document with the empty table"""

    logging.info(f'List request from {request.access_route[0]}')
    return app.send_static_file('list.html')

@app.route('/list/events')
def events():
    """GET access point for the current table contents
    Returns the cached events in JSON format"""

    logging.info(f'Events update request from {request.access_route[0]}')
    events =  WebCacheHandler(config.get('COMMON', 'web_cache_file')).json_events()
    if events is None:
        abort(500, description='Events have not been cached yet.')

    return {
        'events': events,
        'names': list(config['EMAILS'].keys())}


def start_sync_job():
    """start a scheduler with the calendar syncronisation job defined in the SYNC_JOB config section"""

    if not 'SYNC_JOB' in config:
        return
    
    interval = config.getint('SYNC_JOB', 'interval')

    scheduler.add_job(
        sync,
        'interval',
        kwargs={'source': 'schedule'},
        minutes=interval,
        start_date=arrow.get().shift(seconds=10).datetime)

def app_startup():
    """app factory method launch function"""

    start_sync_job()
    return app
