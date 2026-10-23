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


def test_agent_without_grant_sees_only_not_found(db_session, monkeypatch):
    import uuid

    from autopilot.identity.models import ActorKind
    from autopilot.identity.service import create_agent
    from autopilot.ventures.service import create_task, create_venture

    monkeypatch.setenv("AUTOPILOT_BOOTSTRAP_SECRET", "test-secret")
    owner, _ = bootstrap_owner(db_session, "test-secret")
    agent, token = create_agent(db_session, owner, ActorKind.specialist)
    venture = create_venture(db_session, owner, "Private")
    other = create_venture(db_session, owner, "Other")
    task = create_task(db_session, owner, venture.id, "Private task", "Evidence")
    app = create_app()

    def test_session():
        yield db_session

    app.dependency_overrides[get_session] = test_session
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    assert agent.active
    for venture_id in (venture.id, other.id, uuid.uuid4()):
        assert client.get(
            f"/ventures/{venture_id}", headers=headers
        ).status_code == 404
        assert client.post(
            f"/ventures/{venture_id}/tasks", headers=headers,
            json={"title": "Probe", "acceptance_criteria": "Probe"},
        ).status_code == 404
    assert client.get(
        f"/ventures/{venture.id}/tasks/{task.id}", headers=headers
    ).status_code == 404
    assert client.post(
        f"/ventures/{venture.id}/tasks/{task.id}/transition",
        headers=headers, json={"expected_version": 1, "target": "leased"},
    ).status_code == 404
