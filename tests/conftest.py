import pytest
from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.resource import StudyMaterial, MaterialType

@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        # Seed test user and resource
        user = User(
            email="testuser@campusx.edu",
            password_hash="hashed_test_pass",
            first_name="Test",
            last_name="User",
            role="STUDENT"
        )
        db.session.add(user)
        db.session.flush()

        sample = StudyMaterial(
            title="Introduction to Computer Science & Algorithms",
            description="Comprehensive lecture notes and study material covering basic algorithms, sorting, and complexity.",
            author_id=user.id,
            material_type=MaterialType.NOTE,
            status="APPROVED"
        )
        db.session.add(sample)
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def runner(app):
    return app.test_cli_runner()
