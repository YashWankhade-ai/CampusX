from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    """
    SQLAlchemy 2.x Declarative Base Registry for CampusX.
    Serves as the root metadata registry for all future domain models.
    """
    pass

db = SQLAlchemy(model_class=Base)

try:
    from flask_migrate import Migrate
    migrate = Migrate()
except ImportError:
    class DummyMigrate:
        def init_app(self, app, db=None, **kwargs):
            pass
    migrate = DummyMigrate()

try:
    from flask_cors import CORS
    cors = CORS()
except ImportError:
    class DummyCORS:
        def init_app(self, app, **kwargs):
            pass
    cors = DummyCORS()
