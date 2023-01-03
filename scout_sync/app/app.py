import sys
import os
import logging
import pickle
import requests
import arrow
from flask import Flask, render_template, request, abort
from apscheduler.schedulers.background import BackgroundScheduler
from ..config import config
from ..sync import sync

logging.basicConfig(
    filename=config.get('COMMON', 'log_file'),
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S',
    level=logging.INFO)

logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.getLogger('apscheduler').setLevel(logging.ERROR)
sys.excepthook = lambda exc_type, exc_value, exc_traceback: logging.exception(
    exc_type.__name__, exc_info=(exc_type, exc_value, exc_traceback))

EVENTS_CACHE_FILE = 'events.cache'
app = Flask(
    'scout_sync',
    template_folder=os.path.join(os.path.dirname(__file__), 'templates'))

@app.route('/')
def root():
    """ping access point"""

    return ''

@app.post('/sync')
def sync_():
    """POST access point for sync requests
    
    Request data should be:
    {from: [source], to: [target]}"""

    targets = ['calendar', 'schedule', 'table']
    source = request.form.get('from')
    dest = request.form.get('to')
    logging.info(f'Sync request from {request.access_route[0]} ({source} -> {dest})')

    if source not in targets or dest not in targets:
        abort(400, description='invalid "from" or "to" argument')
    
    try:
        events = sync(source, dest)
    except Exception as e:
        logging.exception(e)
        abort(500)
    
    if isinstance(events, dict):
        with open(os.path.join(os.path.dirname(__file__), EVENTS_CACHE_FILE), 'wb') as f:
            pickle.dump(events, f)
    
    return {}, 201

@app.route('/list')
def list():
    """GET access point for the current game list
    Returns a HTML document with the list, from the events stored in the events cache file,
    created by the last sync request"""

    logging.info(f'List request from {request.access_route[0]}')

    events_cache_path_file = os.path.join(os.path.dirname(__file__), EVENTS_CACHE_FILE)
    if not os.path.isfile(events_cache_path_file):
        abort(500, description='Events have not been cached yet.')
    
    with open(events_cache_path_file, 'rb') as f:
        events = pickle.load(f)
        return render_template(
            'game_list.html',
            events=events,
            today=arrow.now(config.get('COMMON', 'timezone')).date())

def start_sync_jobs():
    """start a scheduler with the syncronisation jobs defined in the SYNC_JOBS config section"""

    scheduler = BackgroundScheduler(timzone=config.get('COMMON', 'timezone'))
    jobs = [config.getlist('SYNC_JOBS', o) for o in config['SYNC_JOBS'].keys()]
    port = config.get('COMMON', 'port')

    for source, target, interval in jobs:
        task = lambda source, target: requests.post(
            f"http://localhost:{port}/sync", data={'from': source, 'to': target})
        scheduler.add_job(
            task,
            'interval',
            kwargs = {'source': source, 'target': target}, minutes=interval)
        logging.info(f"added sync job: {source} -> {target} ({interval}min)")

    scheduler.start()

def app_startup():
    """app factory method launch function"""

    start_sync_jobs()
    return app
 