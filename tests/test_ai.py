import pytest

def test_ai_session_and_chat_flow(client):
    # 1. Register user
    client.post("/api/v1/auth/register", json={
        "email": "aistudent@campusx.edu",
        "password": "Password123!",
        "first_name": "AI",
        "last_name": "Student",
        "role": "STUDENT"
    })

    # 2. Login user to get token
    login_res = client.post("/api/v1/auth/login", json={
        "email": "aistudent@campusx.edu",
        "password": "Password123!"
    })
    token = login_res.get_json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 3. Create AI Session
    sess_res = client.post("/api/v1/ai/sessions", json={"title": "Algorithms Study Session"}, headers=headers)
    assert sess_res.status_code == 201
    session_id = sess_res.get_json()["data"]["id"]
    assert session_id is not None

    # 4. Send AI Chat message
    chat_res = client.post("/api/v1/ai/chat", json={
        "session_id": session_id,
        "message": "Explain the time complexity of QuickSort in best and worst cases."
    }, headers=headers)

    assert chat_res.status_code == 200
    chat_data = chat_res.get_json()["data"]
    assert "response" in chat_data
    assert "usage" in chat_data
    assert chat_data["session_id"] == session_id

    # 5. Retrieve Session History
    hist_res = client.get(f"/api/v1/ai/sessions/{session_id}", headers=headers)
    assert hist_res.status_code == 200
    messages = hist_res.get_json()["data"]["messages"]
    assert len(messages) >= 2 # 1 user message + 1 AI message

def test_ai_summarization(client):
    """Summarize route now requires resource_id (grounded, Cycle 3).

    This test verifies:
    - Auth passes for a FACULTY user
    - Sending the old text= body without resource_id correctly returns 400
    - No crash or 500 error

    Full grounded summary tests are in tests/test_cycle3.py.
    """
    client.post("/api/v1/auth/register", json={
        "email": "aifaculty@campusx.edu",
        "password": "Password123!",
        "first_name": "AI",
        "last_name": "Faculty",
        "role": "FACULTY"
    })

    login_res = client.post("/api/v1/auth/login", json={
        "email": "aifaculty@campusx.edu",
        "password": "Password123!"
    })
    token = login_res.get_json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Old text= body no longer accepted — route now requires resource_id
    sum_res = client.post("/api/v1/ai/summarize", json={
        "text": "Dynamic programming is an algorithmic technique."
    }, headers=headers)

    # Correct behaviour: 400 VALIDATION_ERROR (resource_id missing)
    assert sum_res.status_code == 400
    resp_json = sum_res.get_json()
    # CampusX error envelope: {"error": {"code": "VALIDATION_ERROR", ...}}
    assert resp_json.get("error", {}).get("code") == "VALIDATION_ERROR" or \
           resp_json.get("code") == "VALIDATION_ERROR"
