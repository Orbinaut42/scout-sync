import os
import logging
import arrow
from configparser import ConfigParser
from flask import Flask, render_template, request, abort
from scout_sync import sync, CalendarHandler

app = Flask('scout_sync')
logging.getLogger('werkzeug').setLevel(logging.ERROR)

@app.route('/sync')
def sync_():
    targets = ['calendar', 'schedule', 'table']
    source = request.args.get('from')
    dest = request.args.get('to')

    if source not in targets or dest not in targets:
        abort(400, 'invalid "from" or "to" argument')
    
    try:
        sync(source, dest)
    except:
        abort(500)
    
    return 'OK'


@app.route('/')
def root():
    config = ConfigParser()
    config.read('scout_sync.cfg', encoding='utf8')

    calendar = CalendarHandler(config.get('CALENDAR', 'id'))
    calendar.connect()
    events = calendar.list_events()

    return render_template('game_list.html', events=events, today=arrow.now(config.get('COMMON', 'timezone')).date())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 3000))
