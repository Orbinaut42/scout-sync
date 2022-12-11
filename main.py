import os
import logging
from flask import Flask, send_file, request, abort
from scout_sync import sync

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

    answer = 'return table' if not sync_request else f"sync({source}, {dest})"
    # sync('schedule', 'calendar')
    return answer


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 3000))
