import pytest

def test_user_registration(client):
    res = client.post("/api/v1/auth/register", json={
        "email": "newstudent@campusx.edu",
        "password": "Password123!",
        "first_name": "New",
        "last_name": "Student",
        "role": "STUDENT"
    })
    assert res.status_code == 201
    data = res.get_json()
    assert data["success"] is True
    assert data["data"]["email"] == "newstudent@campusx.edu"
    assert data["data"]["verification_token"] is not None

def test_login_and_token_refresh(client):
    # 1. Register user
    client.post("/api/v1/auth/register", json={
        "email": "authtest@campusx.edu",
        "password": "Password123!",
        "first_name": "Auth",
        "last_name": "Tester",
        "role": "FACULTY"
    })

    # 2. Login
    login_res = client.post("/api/v1/auth/login", json={
        "email": "authtest@campusx.edu",
        "password": "Password123!"
    })
    assert login_res.status_code == 200
    login_data = login_res.get_json()["data"]
    assert "access_token" in login_data
    assert "refresh_token" in login_data
    assert login_data["user"]["role"] == "FACULTY"

    # 3. Refresh token rotation
    refresh_res = client.post("/api/v1/auth/refresh", json={
        "refresh_token": login_data["refresh_token"]
    })
    assert refresh_res.status_code == 200
    refresh_data = refresh_res.get_json()["data"]
    assert "access_token" in refresh_data
    assert "refresh_token" in refresh_data
    assert refresh_data["refresh_token"] != login_data["refresh_token"]

def test_account_lockout_after_five_failed_attempts(client):
    # 1. Register user
    client.post("/api/v1/auth/register", json={
        "email": "lockout@campusx.edu",
        "password": "Password123!",
        "first_name": "Lock",
        "last_name": "Out",
        "role": "STUDENT"
    })

    # 2. Fail login 5 times
    for _ in range(5):
        res = client.post("/api/v1/auth/login", json={
            "email": "lockout@campusx.edu",
            "password": "WrongPassword123"
        })

    # 3. 6th attempt should return 423 ACCOUNT_LOCKED
    lockout_res = client.post("/api/v1/auth/login", json={
        "email": "lockout@campusx.edu",
        "password": "Password123!"
    })
    assert lockout_res.status_code == 423
    assert "ACCOUNT_LOCKED" in lockout_res.get_json()["error"]["code"]
