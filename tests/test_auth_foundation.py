import pytest
import time
import logging
from app import create_app
from app.extensions import db
from app.models.academic import Institution
from app.models.user import User
from app.utils.hashing import hash_password, verify_password
from app.utils.token import generate_access_token, decode_access_token

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

def test_argon2id_password_hashing_and_verification():
    raw_pass = "SecurePass123!"
    hashed = hash_password(raw_pass)

    assert hashed is not None
    assert hashed != raw_pass
    assert hashed.startswith("$argon2id$") or "$argon2" in hashed

    # Valid password verification
    assert verify_password(raw_pass, hashed) is True

    # Incorrect password rejection
    assert verify_password("WrongPassword!", hashed) is False
    assert verify_password("", hashed) is False

def test_jwt_generation_and_validation(app):
    with app.app_context():
        inst = Institution(name="Auth Test Inst", short_name="ATI", code="ATI-01", domain_whitelist=[])
        db.session.add(inst)
        db.session.commit()

        user = User(
            institution_id=inst.id,
            email="authtest@campusx.edu",
            full_name="Auth Test User",
            password_hash=hash_password("Password123!"),
            role="FACULTY"
        )
        db.session.add(user)
        db.session.commit()

        # Generate 15-min access token
        token = generate_access_token(user, expires_in_seconds=900)
        assert token is not None
        assert isinstance(token, str)

        # Validate token
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["sub"] == str(user.id)
        assert payload["institution_id"] == str(inst.id)
        assert payload["role"] == "FACULTY"
        assert payload["iss"] == "campusx-api"

def test_expired_and_invalid_jwt_rejection(app):
    with app.app_context():
        inst = Institution(name="Expired Inst", short_name="EI", code="EI-01", domain_whitelist=[])
        db.session.add(inst)
        db.session.commit()

        user = User(
            institution_id=inst.id,
            email="expired@campusx.edu",
            full_name="Expired User",
            password_hash="hash"
        )
        db.session.add(user)
        db.session.commit()

        # Token with 0-second expiration
        token = generate_access_token(user, expires_in_seconds=-1)
        assert decode_access_token(token) is None

        # Malformed token rejection
        assert decode_access_token("invalid.jwt.token.string") is None
        assert decode_access_token("") is None

def test_login_and_protected_endpoint_flow(client):
    # 1. Setup User in DB
    inst = Institution(name="Login Test Inst", short_name="LTI", code="LTI-01", domain_whitelist=[])
    db.session.add(inst)
    db.session.commit()

    raw_pass = "ValidPassword123!"
    user = User(
        institution_id=inst.id,
        email="loginuser@campusx.edu",
        full_name="Login User",
        password_hash=hash_password(raw_pass),
        status="active",
        role="STUDENT"
    )
    db.session.add(user)
    db.session.commit()

    # 2. Login with incorrect password -> 401 Unauthorized
    bad_res = client.post("/api/v1/auth/login", json={
        "email": "loginuser@campusx.edu",
        "password": "WrongPassword!"
    })
    assert bad_res.status_code == 401
    bad_json = bad_res.get_json()
    assert bad_json["success"] is False
    assert bad_json["error"]["code"] == "UNAUTHORIZED"

    # 3. Login with correct password -> 200 OK
    good_res = client.post("/api/v1/auth/login", json={
        "email": "loginuser@campusx.edu",
        "password": raw_pass
    })
    assert good_res.status_code == 200
    good_json = good_res.get_json()
    assert good_json["success"] is True
    assert "access_token" in good_json["data"]
    token = good_json["data"]["access_token"]

    # 4. Protected endpoint without token -> 401 Unauthorized
    unauth_res = client.get("/api/v1/auth/me")
    assert unauth_res.status_code == 401
    unauth_json = unauth_res.get_json()
    assert unauth_json["error"]["code"] == "UNAUTHORIZED"

    # 5. Protected endpoint with valid Bearer token -> 200 OK
    headers = {"Authorization": f"Bearer {token}"}
    me_res = client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    me_json = me_res.get_json()
    assert me_json["success"] is True
    assert me_json["data"]["id"] == str(user.id)
    assert me_json["data"]["role"] == "STUDENT"

def test_sensitive_values_not_in_logs(caplog):
    caplog.set_level(logging.DEBUG)
    secret_pass = "SuperSecretPassword123!"
    secret_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.secretpayload.sig"

    hashed = hash_password(secret_pass)
    verify_password(secret_pass, hashed)
    decode_access_token(secret_token)

    logged_text = caplog.text
    assert secret_pass not in logged_text
    assert hashed not in logged_text
    assert secret_token not in logged_text
