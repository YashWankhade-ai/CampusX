import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

from app import create_app

flask_env = os.getenv("FLASK_ENV", "development")
app = create_app(flask_env)

# Configure ProxyFix for reverse proxy deployments (Nginx, AWS ALB, Cloudflare)
if os.getenv("ENABLE_PROXY_FIX", "1") == "1":
    try:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    except Exception:
        pass

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
