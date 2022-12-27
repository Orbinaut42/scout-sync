import os
from .app import app, start_sync_jobs

start_sync_jobs()
app.run(debug=True, host='0.0.0.0', port=os.environ.get('PORT', 3000), use_reloader=False)
