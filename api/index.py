import os
import sys
import traceback

# Ensure project root is in sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Set VERCEL environment indicator
os.environ["VERCEL"] = "1"

try:
    from run import app as flask_app

    with flask_app.app_context():
        try:
            from app.extensions import db
            db.create_all()
        except Exception as db_err:
            print(f"[Vercel DB Warning]: {db_err}", flush=True)

    def app(environ, start_response):
        # Restore original path if rewritten by Vercel CLI 65
        raw_path = environ.get('PATH_INFO', '')
        matched_path = environ.get('HTTP_X_MATCHED_PATH') or environ.get('HTTP_X_INVOKE_PATH')
        
        if matched_path:
            environ['PATH_INFO'] = matched_path
        elif raw_path in ('/api/index', '/api/index/'):
            environ['PATH_INFO'] = '/'

        try:
            return flask_app(environ, start_response)
        except Exception:
            err_trace = traceback.format_exc()
            print(f"[Vercel Runtime Crash]: {err_trace}", flush=True)
            status = '500 Internal Server Error'
            headers = [('Content-Type', 'text/html; charset=utf-8')]
            start_response(status, headers)
            return [
                f"<html><body style='font-family:sans-serif;padding:2rem;background:#111;color:#eee;'>"
                f"<h2 style='color:#f87171;'>CampusX Runtime Error</h2>"
                f"<pre style='background:#222;padding:1rem;border-radius:8px;overflow-x:auto;'>{err_trace}</pre>"
                f"</body></html>".encode('utf-8')
            ]

except Exception:
    cold_start_trace = traceback.format_exc()
    print(f"[Vercel Cold Start Crash]: {cold_start_trace}", flush=True)

    def app(environ, start_response):
        status = '500 Internal Server Error'
        headers = [('Content-Type', 'text/html; charset=utf-8')]
        start_response(status, headers)
        return [
            f"<html><body style='font-family:sans-serif;padding:2rem;background:#111;color:#eee;'>"
            f"<h2 style='color:#f87171;'>CampusX Cold Start Import Failure</h2>"
            f"<pre style='background:#222;padding:1rem;border-radius:8px;overflow-x:auto;'>{cold_start_trace}</pre>"
            f"</body></html>".encode('utf-8')
        ]
