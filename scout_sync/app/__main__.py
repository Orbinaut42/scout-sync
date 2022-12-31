"""Starts the app with the Flask debug server"""

from .app import app, start_sync_jobs
from ..config import config

start_sync_jobs()
app.run(debug=True, host='0.0.0.0', port=config.get('COMMON', 'port'), use_reloader=False)
