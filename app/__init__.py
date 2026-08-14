import os
from flask import Flask, jsonify
from .extensions import db, migrate, cors
from .config import config_by_name, Config
from .logging_config import setup_logging
from .repositories.health_repository import HealthRepository

def create_app(config_name=None):
    """
    Application Factory Pattern for CampusX Backend.
    Sprint 2 Database Foundation: SQLAlchemy 2.x, Flask-Migrate, Session Lifecycle, Health Readiness.
    """
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")

    app = Flask(__name__)

    # Load environment-driven configuration
    config_cls = config_by_name.get(config_name.lower(), Config)
    app.config.from_object(config_cls)

    if os.environ.get("DATABASE_URL") and config_name.lower() != "testing":
        app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")

    # Configure structured JSON logging
    setup_logging(log_level=app.config.get("LOG_LEVEL", "INFO"))

    # Initialize database extensions
    db.init_app(app)
    migrate.init_app(app, db)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config.get("CORS_ORIGINS", "*")}})

    # Session Lifecycle Management: Teardown database session on request end
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db.session.remove()

    # Register Blueprints (/api/v1 namespace)
    from .blueprints.web import web_bp
    from .blueprints.api.v1 import api_v1_bp

    app.register_blueprint(web_bp)
    app.register_blueprint(api_v1_bp)

    # Lightweight Liveness Endpoint (Does NOT query database)
    @app.route("/health", methods=["GET"])
    def health_liveness():
        return jsonify({
            "status": "healthy",
            "service": "CampusX API",
            "version": "1.0"
        }), 200

    # Database Readiness Endpoint (Checks DB connectivity)
    @app.route("/health/ready", methods=["GET"])
    def health_readiness():
        is_ready, details = HealthRepository.ping_database()
        if is_ready:
            return jsonify({
                "status": "ready",
                "database": "connected",
                "service": "CampusX API"
            }), 200
        else:
            return jsonify({
                "status": "not_ready",
                "database": "disconnected",
                "error": details,
                "service": "CampusX API"
            }), 503

    # Global Error Handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return jsonify({
            "success": False,
            "error": {
                "code": "NOT_FOUND",
                "message": "The requested resource or endpoint was not found."
            }
        }), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected server error occurred."
            }
        }), 500

    return app
