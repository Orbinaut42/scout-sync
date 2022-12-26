import os
import logging
import arrow
from configparser import ConfigParser
from flask import Flask, render_template, request, abort
from scout_sync import sync, CalendarHandler

_CONFIG = ConfigParser()
_CONFIG.read('scout_sync.cfg', encoding='utf8')
logging.basicConfig(
    filename=_CONFIG.get('COMMON', 'log_file'),
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S',
    level=logging.INFO)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

app = Flask('scout_sync')

@app.route('/sync')
def sync_():
    targets = ['calendar', 'schedule', 'table']
    source = request.args.get('from')
    dest = request.args.get('to')
    logging.info(f'Sync request from {request.access_route[0]} ({source}, {dest})')

    if source not in targets or dest not in targets:
        abort(400, 'invalid "from" or "to" argument')
    
    try:
        sync(source, dest)
    except:
        abort(500)
    
    return 'OK'


@app.route('/')
def root():
    logging.info(f'Table request from {request.access_route[0]}')
    calendar = CalendarHandler(_CONFIG.get('CALENDAR', 'id'))
    calendar.connect()
    events = calendar.list_events()

    return render_template('game_list.html', events=events, today=arrow.now(_CONFIG.get('COMMON', 'timezone')).date())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 3000))
