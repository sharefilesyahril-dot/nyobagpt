from fastapi.testclient import TestClient

from autopilot.app import create_app
from autopilot.db import get_session
from autopilot.identity.service import bootstrap_owner


def test_venture_task_http_scoping_and_conflicts(db_session, monkeypatch):
    monkeypatch.setenv("AUTOPILOT_BOOTSTRAP_SECRET", "test-secret")
    _, token = bootstrap_owner(db_session, "test-secret")
    app = create_app()

    def test_session():
        yield db_session

    app.dependency_overrides[get_session] = test_session
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/ventures", json={"name": "A"}).status_code == 401
    response = client.post("/ventures", headers=headers, json={"name": "A"})
    assert response.status_code == 201
    venture_id = response.json()["id"]
    response = client.post(
        f"/ventures/{venture_id}/tasks", headers=headers,
        json={"title": "Research", "acceptance_criteria": "Evidence"},
    )
    assert response.status_code == 201
    task_id = response.json()["id"]
    url = f"/ventures/{venture_id}/tasks/{task_id}/transition"
    assert client.post(
        url, headers=headers,
        json={"expected_version": 1, "target": "completed"},
    ).status_code == 409
    assert client.post(
        url, headers=headers,
        json={"expected_version": 1, "target": "leased"},
    ).status_code == 200
    assert client.post(
        url, headers=headers,
        json={"expected_version": 1, "target": "paused"},
    ).status_code == 409
