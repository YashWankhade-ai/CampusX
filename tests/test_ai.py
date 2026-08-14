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

    sum_res = client.post("/api/v1/ai/summarize", json={
        "text": "Dynamic programming is an algorithmic technique for solving optimization problems by breaking them down into simpler subproblems and storing the results to avoid redundant calculations."
    }, headers=headers)

    assert sum_res.status_code == 200
    assert "summary" in sum_res.get_json()["data"]
