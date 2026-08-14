import pytest
from app import create_app

def test_app_factory_development():
    app = create_app("development")
    assert app.config["DEBUG"] is True
    assert app.config["TESTING"] is False

def test_app_factory_testing():
    app = create_app("testing")
    assert app.config["TESTING"] is True
    assert app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite:///:memory:"

def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"
    assert data["service"] == "CampusX API"
    assert data["version"] == "1.0"
