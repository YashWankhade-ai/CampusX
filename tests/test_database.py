import pytest
from app import create_app
from app.extensions import db, migrate

def test_app_creation_and_db_extension():
    app = create_app("testing")
    assert app is not None
    assert app.config["TESTING"] is True
    assert app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite:///:memory:"

    with app.app_context():
        # Verify database engine and session are bound
        assert db.engine is not None
        assert db.session is not None

def test_liveness_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"
    assert data["service"] == "CampusX API"

def test_readiness_health_endpoint(client):
    response = client.get("/health/ready")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ready"
    assert data["database"] == "connected"

def test_readiness_failure_behavior(monkeypatch, client):
    # Simulate DB disconnection
    def mock_ping():
        return False, "Connection refused: PostgreSQL database offline"

    from app.repositories.health_repository import HealthRepository
    monkeypatch.setattr(HealthRepository, "ping_database", mock_ping)

    response = client.get("/health/ready")
    assert response.status_code == 503
    data = response.get_json()
    assert data["status"] == "not_ready"
    assert data["database"] == "disconnected"
    assert "Connection refused" in data["error"]
