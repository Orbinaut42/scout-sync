import os
import logging
from flask import Flask, send_file
from scout_sync import sync

app = Flask('scout_sync')
logging.getLogger('werkzeug').setLevel(logging.ERROR)


@app.route('/')
def root():
    sync('schedule', 'calendar')
    return send_file('scout_sync.log', mimetype='text/plain')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 5000))
