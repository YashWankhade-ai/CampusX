import pytest
import hashlib
import logging
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
from app import create_app
from app.extensions import db
from app.models.academic import Institution
from app.models.user import User, OTPCode
from app.services.auth_service import generate_secure_otp, hash_otp_code, AuthService
from app.utils.redis_client import get_redis_client

@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

def test_otp_generation_and_hashing_properties():
    otp = generate_secure_otp()
    assert otp is not None
    assert len(otp) == 6
    assert otp.isdigit()

    code_hash = hash_otp_code(otp)
    assert code_hash is not None
    assert len(code_hash) == 64
    assert code_hash == hashlib.sha256(otp.encode("utf-8")).hexdigest()

def test_registration_creates_pending_user_and_hashed_otp(client, app):
    with patch("app.tasks.email.send_otp_email.delay") as mock_email_delay:
        res = client.post("/api/v1/auth/register", json={
            "email": "otptest@campusx.edu",
            "password": "SecurePassword123!",
            "first_name": "OTP",
            "last_name": "Tester",
            "role": "STUDENT"
        })

        assert res.status_code == 201
        json_data = res.get_json()
        assert json_data["success"] is True

        # 1. Plaintext OTP NEVER returned in API response
        res_data = json_data["data"]
        assert "otp" not in res_data
        assert "otp_code" not in res_data
        assert "code" not in res_data

        with app.app_context():
            # 2. User created with status=pending_verification
            user = db.session.query(User).filter_by(email="otptest@campusx.edu").first()
            assert user is not None
            assert user.status == "pending_verification"

            # 3. OTPCode created in DB with SHA-256 hash (never plaintext)
            otp_record = db.session.query(OTPCode).filter_by(email="otptest@campusx.edu").first()
            assert otp_record is not None
            assert otp_record.code_hash != ""
            assert len(otp_record.code_hash) == 64
            assert otp_record.attempt_count == 0
            assert otp_record.used_at is None

            # 4. Redis key set
            redis = get_redis_client()
            redis_val = redis.get("otp:otptest@campusx.edu:email_verification")
            assert redis_val == otp_record.code_hash

        # 5. Celery email task queued
        mock_email_delay.assert_called_once()

def test_correct_otp_activates_user_and_cleans_redis(client, app):
    with patch("app.tasks.email.send_otp_email.delay") as mock_email:
        # Register user
        reg_res = client.post("/api/v1/auth/register", json={
            "email": "verifyuser@campusx.edu",
            "password": "Password123!",
            "first_name": "Verify",
            "last_name": "Me"
        })
        assert reg_res.status_code == 201

        # Extract generated OTP code hash from DB to reconstruct code for test
        with app.app_context():
            otp_record = db.session.query(OTPCode).filter_by(email="verifyuser@campusx.edu").first()
            # Fetch actual sent code from mock
            sent_args = mock_email.call_args[0]
            otp_code = sent_args[1]
            assert len(otp_code) == 6

        # Verify email with correct OTP
        ver_res = client.post("/api/v1/auth/verify-email", json={
            "email": "verifyuser@campusx.edu",
            "otp_code": otp_code
        })
        assert ver_res.status_code == 200
        ver_json = ver_res.get_json()
        assert ver_json["success"] is True
        assert "access_token" in ver_json["data"]
        assert "refresh_token" in ver_json["data"]
        assert ver_json["data"]["user"]["status"] == "active"

        with app.app_context():
            # User status changed to active
            user = db.session.query(User).filter_by(email="verifyuser@campusx.edu").first()
            assert user.status == "active"

            # OTP record marked used_at
            otp_record = db.session.query(OTPCode).filter_by(email="verifyuser@campusx.edu").first()
            assert otp_record.used_at is not None

            # Redis key deleted
            redis = get_redis_client()
            assert redis.get("otp:verifyuser@campusx.edu:email_verification") is None

def test_incorrect_otp_rejected_and_attempt_count_incremented(client, app):
    with patch("app.tasks.email.send_otp_email.delay"):
        client.post("/api/v1/auth/register", json={
            "email": "wrongotp@campusx.edu",
            "password": "Password123!"
        })

        # Submit wrong OTP code
        res = client.post("/api/v1/auth/verify-email", json={
            "email": "wrongotp@campusx.edu",
            "otp_code": "000000"
        })
        assert res.status_code == 400
        assert res.get_json()["error"]["code"] == "INVALID_OTP"

        with app.app_context():
            # Attempt count incremented before check
            otp_record = db.session.query(OTPCode).filter_by(email="wrongotp@campusx.edu").first()
            assert otp_record.attempt_count == 1
            assert otp_record.used_at is None

def test_sixth_failed_attempt_rejected(client, app):
    with patch("app.tasks.email.send_otp_email.delay"):
        client.post("/api/v1/auth/register", json={
            "email": "maxattempts@campusx.edu",
            "password": "Password123!"
        })

        # 5 failed attempts
        for i in range(5):
            client.post("/api/v1/auth/verify-email", json={
                "email": "maxattempts@campusx.edu",
                "otp_code": "999999"
            })

        # 6th attempt should be rejected due to max_attempts
        res6 = client.post("/api/v1/auth/verify-email", json={
            "email": "maxattempts@campusx.edu",
            "otp_code": "999999"
        })
        assert res6.status_code == 423
        assert res6.get_json()["error"]["code"] == "MAX_ATTEMPTS_EXCEEDED"

def test_used_otp_cannot_be_reused(client, app):
    with patch("app.tasks.email.send_otp_email.delay") as mock_email:
        client.post("/api/v1/auth/register", json={
            "email": "reuseotp@campusx.edu",
            "password": "Password123!"
        })
        otp_code = mock_email.call_args[0][1]

        # First verification succeeds
        res1 = client.post("/api/v1/auth/verify-email", json={
            "email": "reuseotp@campusx.edu",
            "otp_code": otp_code
        })
        assert res1.status_code == 200

        # Second verification fails
        res2 = client.post("/api/v1/auth/verify-email", json={
            "email": "reuseotp@campusx.edu",
            "otp_code": otp_code
        })
        assert res2.status_code == 400
        assert res2.get_json()["error"]["code"] == "INVALID_OTP"

def test_expired_otp_rejection(client, app):
    with patch("app.tasks.email.send_otp_email.delay") as mock_email:
        client.post("/api/v1/auth/register", json={
            "email": "expiredotp@campusx.edu",
            "password": "Password123!"
        })
        otp_code = mock_email.call_args[0][1]

        with app.app_context():
            # Manually expire OTP record
            otp_record = db.session.query(OTPCode).filter_by(email="expiredotp@campusx.edu").first()
            otp_record.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            db.session.commit()

        res = client.post("/api/v1/auth/verify-email", json={
            "email": "expiredotp@campusx.edu",
            "otp_code": otp_code
        })
        assert res.status_code == 400
        assert res.get_json()["error"]["code"] == "EXPIRED_OTP"

def test_sensitive_otp_not_written_to_logs(app, caplog):
    caplog.set_level(logging.DEBUG)
    otp_code = "847291"
    auth_service = AuthService()

    code_hash = hash_otp_code(otp_code)
    with app.app_context():
        auth_service.verify_email_otp("logtest@campusx.edu", otp_code)

    logged_text = caplog.text
    assert otp_code not in logged_text
