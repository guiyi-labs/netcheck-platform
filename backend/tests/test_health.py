from fastapi.testclient import TestClient


def test_health_endpoint_reports_service_status(client: TestClient):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "netcheck-backend",
        "version": "0.2.0",
    }


def test_api_health_endpoint_reports_database_url(client: TestClient):
    response = client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"].startswith("sqlite:///")
