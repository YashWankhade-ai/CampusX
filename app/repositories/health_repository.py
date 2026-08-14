from typing import Tuple
from sqlalchemy import text
from app.extensions import db

class HealthRepository:
    """
    Repository for database health and connectivity verification.
    Follows separation of concerns: route functions do NOT execute raw queries directly.
    """
    @staticmethod
    def ping_database() -> Tuple[bool, str]:
        """
        Executes a minimal `SELECT 1` query to verify database connection readiness.
        Returns (True, "connected") if healthy, or (False, error_message) if connection fails.
        """
        try:
            db.session.execute(text("SELECT 1"))
            return True, "connected"
        except Exception as e:
            db.session.rollback()
            return False, str(e)
