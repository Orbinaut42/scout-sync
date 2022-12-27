import os
from .app import app

app.run(debug=True, host='0.0.0.0', port=os.environ.get('PORT', 3000))
