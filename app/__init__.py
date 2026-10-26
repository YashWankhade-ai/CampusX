import os
from flask import Flask, jsonify
from .extensions import db, migrate, cors
from .config import config_by_name, Config
from .logging_config import setup_logging
from .repositories.health_repository import HealthRepository

def create_app(config_name=None, run_seed=True):
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
    
    # Configure CORS for Vercel, Hugging Face, and custom domains
    cors_origins = app.config.get("CORS_ORIGINS", ["*"])
    if isinstance(cors_origins, str):
        cors_origins = [o.strip() for o in cors_origins.split(",") if o.strip()]
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": cors_origins if cors_origins else "*"}},
        supports_credentials=True
    )

    # Session Lifecycle Management: Teardown database session on request end
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db.session.remove()

    # Register Blueprints (/api/v1 namespace)
    from .blueprints.web import web_bp
    from .blueprints.api.v1 import api_v1_bp

    app.register_blueprint(web_bp)
    app.register_blueprint(api_v1_bp)

    # Ensure database schema and default seed data are initialized
    if run_seed:
        with app.app_context():
            try:
                from .models.user import User
                db.create_all()
                if not User.query.filter_by(email="admin@campusx.edu").first():
                    from seed import seed_database
                    seed_database(app=app)
            except Exception as e:
                app.logger.warning(f"[DB Auto-Init Warning]: {e}")

    # Register Middlewares
    from .middleware.security_headers import security_headers
    from .middleware.audit_middleware import audit_middleware
    from .middleware.tenant_context import tenant_context

    app.after_request(security_headers)
    app.after_request(audit_middleware)
    app.before_request(tenant_context)

    try:
        import flask_limiter
        from .middleware.rate_limiter import init_rate_limiter
        init_rate_limiter(app)
    except ImportError:
        pass

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
        from flask import request as _req, render_template as _rt
        # Return HTML for browser requests, JSON for API/AJAX requests
        if _req.path.startswith('/api/') or \
           _req.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json':
            return jsonify({
                "success": False,
                "error": {
                    "code": "NOT_FOUND",
                    "message": "The requested resource or endpoint was not found."
                }
            }), 404
        return _rt("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(error):
        import traceback
        err_msg = traceback.format_exc()
        app.logger.error(f"[500 Error Handler]: {err_msg}")
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected server error occurred.",
                "details": str(getattr(error, 'description', error)),
                "trace": err_msg
            }
        }), 500

    return app

# Expose 'app' attribute for serverless environments (e.g. Vercel) that inspect package root
_cached_app = None

def __getattr__(name):
    if name == "app":
        global _cached_app
        if _cached_app is None:
            _cached_app = create_app()
        return _cached_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
