"""Starts the app with the Flask debug server"""

from .app import app_startup
from ..config import config

app = app_startup()
app.run(
    debug=True,
    host='0.0.0.0',
    port=config.port,
    use_reloader=False)
