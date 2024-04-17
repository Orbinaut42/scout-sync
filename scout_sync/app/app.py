import sys
import os
import logging
import json
import arrow
from flask import Flask, request, abort
from apscheduler.schedulers.background import BackgroundScheduler
from ..config import config
from ..sync import sync, Event

logging.basicConfig(
    filename=config.get('COMMON', 'log_file'),
        format='%(asctime)s %(levelname)s: %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S',
        level=logging.INFO)

logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.getLogger('apscheduler').setLevel(logging.ERROR)
sys.excepthook = lambda exc_type, exc_value, exc_traceback: logging.exception(
    exc_type.__name__, exc_info=(exc_type, exc_value, exc_traceback))

app = Flask(
    'scout_sync',
    static_folder=os.path.join(os.path.dirname(__file__), 'static'))


@app.route('/')
def root():
    """ping access point"""

    return ''


@app.post('/edit')
def edit():
    """POST access point for edits from webpage
    
    Request data should be:
    {events: [json_events]}"""

    logging.info(f'Edit request from {request.access_route[0]}')
    events = request.form.get('events')

    # check if event list is valid
    try:
        for e in events:
            Event.from_json(e)

    except Exception as e:
        logging.exception(e)
        abort(400)

    with open(config.get('COMMON', 'web_cache_file'), 'w') as web_cache_file:
        json.dump(events, web_cache_file)
        logging.info(f'Events cache written to {web_cache_file}')

    return {}, 201


@app.route('/list')
def list():
    """GET access point for the current game list
    Returns a HTML document with the empty table"""

    logging.info(f'List request from {request.access_route[0]}')
    return app.send_static_file('game_list.html')

@app.route('/list/events')
def events():
    """GET access point for the current table contents
    Returns the cached events in JSON format"""

    logging.info(f'Events update request from {request.access_route[0]}')

    try:
        with open(config.get('COMMON', 'web_cache_file'), 'r') as web_cache_file:
            return json.load(web_cache_file)
        
    except FileNotFoundError:
        abort(500, description='Events have not been cached yet.')

def start_sync_job():
    """start a scheduler with the calendar syncronisation job defined in the SYNC_JOB config section"""

    interval = config.get('SYNC_JOB', 'interval')
    if interval is None:
        return
    
    scheduler = BackgroundScheduler(timzone=config.get('COMMON', 'timezone'))
    scheduler.add_job(
        sync,
        'interval',
        kwargs={'source': 'schedule'},
        minutes=interval,
        start_date=arrow.get().shift(seconds=10).datetime)

    scheduler.start()


def app_startup():
    """app factory method launch function"""

    start_sync_job()
    return app
