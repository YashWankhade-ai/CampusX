import os
import sys

# Ensure project root is in sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Set VERCEL environment indicator
os.environ["VERCEL"] = "1"

from run import app

# Ensure tables exist in serverless environment
with app.app_context():
    try:
        from app.extensions import db
        db.create_all()
    except Exception as db_err:
        pass

# WSGI Middleware to restore clean paths on Vercel
class VercelPathFix:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        matched = environ.get('HTTP_X_MATCHED_PATH') or environ.get('HTTP_X_INVOKE_PATH')
        raw = environ.get('PATH_INFO', '')
        if matched and matched != raw:
            environ['PATH_INFO'] = matched
        elif raw in ('/api/index', '/api/index/'):
            environ['PATH_INFO'] = '/'
        return self.wsgi_app(environ, start_response)

app.wsgi_app = VercelPathFix(app.wsgi_app)
