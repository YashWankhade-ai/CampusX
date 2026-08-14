import pytest
import uuid
from datetime import datetime, timezone
from app import create_app
from app.extensions import db
from app.models.academic import Institution
from app.models.user import User
from sqlalchemy.exc import IntegrityError

@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

def test_institution_creation(app):
    with app.app_context():
        inst = Institution(
            name="Indian Institute of Technology",
            short_name="IIT",
            code="IIT-MAIN",
            domain_whitelist=["iit.ac.in"],
            city="Mumbai",
            state="Maharashtra",
            country="India"
        )
        db.session.add(inst)
        db.session.commit()

        assert inst.id is not None
        assert isinstance(inst.id, uuid.UUID)
        assert inst.code == "IIT-MAIN"
        assert inst.is_active is True
        assert inst.is_deleted is False
        assert inst.created_at is not None

def test_user_creation_and_institution_relationship(app):
    with app.app_context():
        inst = Institution(
            name="National Institute of Technology",
            short_name="NIT",
            code="NIT-MAIN",
            domain_whitelist=["nit.ac.in"]
        )
        db.session.add(inst)
        db.session.commit()

        user = User(
            institution_id=inst.id,
            email="student@nit.ac.in",
            email_normalized="student@nit.ac.in",
            full_name="Aarav Sharma",
            password_hash="argon2id$hashedpassword",
            status="active"
        )
        db.session.add(user)
        db.session.commit()

        assert user.id is not None
        assert isinstance(user.id, uuid.UUID)
        assert user.institution_id == inst.id
        assert user.institution.code == "NIT-MAIN"
        assert user in inst.users

def test_institution_unique_code_constraint(app):
    with app.app_context():
        inst1 = Institution(name="College A", short_name="CA", code="COLLEGE-X", domain_whitelist=[])
        db.session.add(inst1)
        db.session.commit()

        inst2 = Institution(name="College B", short_name="CB", code="COLLEGE-X", domain_whitelist=[])
        db.session.add(inst2)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

def test_user_per_institution_unique_email_constraint(app):
    with app.app_context():
        inst = Institution(name="College C", short_name="CC", code="COLLEGE-C", domain_whitelist=[])
        db.session.add(inst)
        db.session.commit()

        u1 = User(
            institution_id=inst.id,
            email="user@cc.edu",
            email_normalized="user@cc.edu",
            full_name="User One",
            password_hash="hash"
        )
        db.session.add(u1)
        db.session.commit()

        u2 = User(
            institution_id=inst.id,
            email="user@cc.edu",
            email_normalized="user@cc.edu",
            full_name="User Two",
            password_hash="hash"
        )
        db.session.add(u2)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

def test_soft_delete_behavior(app):
    with app.app_context():
        inst = Institution(name="College D", short_name="CD", code="COLLEGE-D", domain_whitelist=[])
        db.session.add(inst)
        db.session.commit()

        now_utc = datetime.now(timezone.utc)
        inst.is_deleted = True
        inst.deleted_at = now_utc
        db.session.commit()

        fetched = db.session.query(Institution).filter_by(code="COLLEGE-D").first()
        assert fetched.is_deleted is True
        assert fetched.deleted_at is not None

def test_migration_upgrade_and_downgrade(app):
    from alembic.config import Config
    from alembic import command

    alembic_cfg = Config("alembic.ini")
    with app.app_context():
        db.drop_all()
        # Upgrade to head
        command.upgrade(alembic_cfg, "head")

        # Downgrade 1 revision (to base)
        command.downgrade(alembic_cfg, "base")

        # Re-upgrade to head
        command.upgrade(alembic_cfg, "head")
