import pytest
from fastapi.testclient import TestClient

from autopilot.app import create_app
from autopilot.db import get_session
from autopilot.identity.models import ActorKind
from autopilot.identity.service import bootstrap_owner, create_agent


def test_agents_require_valid_owner_credentials(db_session, monkeypatch):
    monkeypatch.setenv("AUTOPILOT_BOOTSTRAP_SECRET", "test-bootstrap-secret")
    owner, token = bootstrap_owner(db_session, "test-bootstrap-secret")
    agent, agent_token = create_agent(db_session, owner, ActorKind.specialist)
    app = create_app()

    def test_session():
        yield db_session

    app.dependency_overrides[get_session] = test_session
    client = TestClient(app)
    assert client.post("/agents", json={"kind": "executive"}).status_code == 401
    assert client.post(
        "/agents",
        headers={"Authorization": "Bearer invalid"},
        json={"kind": "executive"},
    ).status_code == 401
    assert client.post(
        "/agents",
        headers={"Authorization": f"Bearer {agent_token}"},
        json={"kind": "executive"},
    ).status_code == 403
    response = client.post(
        "/agents",
        headers={"Authorization": f"Bearer {token}"},
        json={"kind": "executive"},
    )
    assert response.status_code == 201
    assert response.json()["level"] < 4
    assert response.json()["organization_id"] == str(owner.organization_id)
    agent.active = False
    db_session.flush()
    assert client.post(
        "/agents",
        headers={"Authorization": f"Bearer {agent_token}"},
        json={"kind": "executive"},
    ).status_code == 401
