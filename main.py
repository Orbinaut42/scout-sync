import os
import logging
import datetime
from configparser import ConfigParser
from flask import Flask, render_template, request, abort
from scout_sync import sync, CalendarHandler

app = Flask('scout_sync')
logging.getLogger('werkzeug').setLevel(logging.ERROR)


@app.route('/')
def root():
    parse_bool = lambda s: {'true': True, 'True': True, 'false': False, 'False': False}.get(s)

    sync_request = request.args.get('sync', False, type=parse_bool)
    if not isinstance(sync_request, bool):
        abort(400, 'invalid "sync_request" argument')

    if sync_request:
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

    config = ConfigParser()
    config.read('scout_sync.cfg', encoding='utf8')

    calendar = CalendarHandler(config.get('CALENDAR', 'id'))
    calendar.connect()
    events = calendar.list_events()

    return render_template('game_list.html', events=events, today=datetime.datetime.today())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 3000))
