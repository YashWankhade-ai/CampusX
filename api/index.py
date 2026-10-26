import os
import sys

# Add project root to sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from run import app

# Ensure tables exist in serverless environment
with app.app_context():
    try:
        from app.extensions import db
        db.create_all()
    except Exception:
        pass
