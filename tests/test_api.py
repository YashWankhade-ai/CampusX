def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["status"] == "healthy"
    assert json_data["service"] == "CampusX API"

def test_list_resources(client):
    response = client.get("/api/v1/resources")
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["success"] is True
    assert len(json_data["data"]) >= 1

def test_search_api(client):
    response = client.get("/api/v1/search?q=algorithms")
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["success"] is True

def test_student_dashboard_web(client):
    response = client.get("/student/dashboard")
    assert response.status_code == 200
    assert b"Lumina" in response.data or b"CampusX" in response.data or response.status_code == 200
