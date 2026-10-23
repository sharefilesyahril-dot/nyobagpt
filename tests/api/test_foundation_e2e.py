"""HTTP-only foundation handoff: no live external effects."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from autopilot.app import create_app
from autopilot.db import get_session
from autopilot.governance.models import Approval
from autopilot.identity.service import bootstrap_owner


def test_foundation_http_workflow_and_security(db_session, monkeypatch):
    monkeypatch.setenv("AUTOPILOT_BOOTSTRAP_SECRET", "e2e-secret")
    _, owner_token = bootstrap_owner(db_session, "e2e-secret")
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    client = TestClient(app)
    owner = {"Authorization": f"Bearer {owner_token}"}

    assert client.post("/ventures", json={"name": "No auth"}).status_code == 401
    venture = client.post("/ventures", headers=owner, json={"name": "E2E"})
    assert venture.status_code == 201
    venture_id = venture.json()["id"]
    other = client.post("/ventures", headers=owner, json={"name": "Other"})
    other_id = other.json()["id"]
    task = client.post(
        f"/ventures/{venture_id}/tasks", headers=owner,
        json={"title": "Fake action", "acceptance_criteria": "Recorded only"},
    )
    assert task.status_code == 201

    agent = client.post("/agents", headers=owner, json={"kind": "executive"})
    assert agent.status_code == 201
    agent_id = agent.json()["id"]
    executive = {"Authorization": f"Bearer {agent.json()['credential']}"}
    assert client.get(f"/ventures/{venture_id}", headers=executive).status_code == 404
    expiry = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    for action, resource in (
        ("read", "venture"), ("write", "venture"), ("payment", "fake-target"),
    ):
        grant = client.post("/governance/grants", headers=owner, json={
            "actor_id": agent_id, "venture_id": venture_id,
            "action": action, "resource": resource,
            "budget_ceiling_minor": 1000, "expires_at": expiry,
        })
        assert grant.status_code == 201, grant.text
    assert client.get(f"/ventures/{venture_id}", headers=executive).status_code == 200
    assert client.get(f"/ventures/{other_id}", headers=executive).status_code == 404
    assert client.post(
        "/governance/global-budget", headers=executive,
        json={"ceiling_minor": 1000},
    ).status_code == 405
    assert client.put(
        "/governance/global-budget", headers=owner, json={"ceiling_minor": 1000},
    ).status_code == 200
    assert client.put(
        f"/governance/ventures/{venture_id}/budget", headers=owner,
        json={"ceiling_minor": 500},
    ).status_code == 200

    body = {
        "venture_id": venture_id, "action": "payment", "target": "fake-target",
        "parameters": {"amount": 10}, "idempotency_key": "e2e-1",
    }
    assert client.post(
        "/action-requests", headers=executive,
        json={**body, "action": "unknown_action"},
    ).status_code == 422
    requested = client.post("/action-requests", headers=executive, json=body)
    assert requested.status_code == 201, requested.text
    request_id = requested.json()["id"]
    repeated = client.post("/action-requests", headers=executive, json=body)
    assert repeated.status_code == 201
    assert repeated.json()["id"] == request_id
    assert client.post(
        "/action-requests", headers=executive,
        json={**body, "parameters": {"amount": 20}},
    ).status_code == 409
    assert client.post(
        "/action-requests", headers=executive,
        json={**body, "venture_id": other_id, "idempotency_key": "e2e-2"},
    ).status_code == 404
    assert client.post(
        f"/action-requests/{request_id}/decision", headers=executive,
        json={"decision": "approved"},
    ).status_code == 403
    approval = client.post(
        f"/action-requests/{request_id}/decision", headers=owner,
        json={"decision": "approved"},
    )
    assert approval.status_code == 201, approval.text
    approval_row = db_session.get(Approval, UUID(approval.json()["id"]))
    original_hash = approval_row.request_hash
    approval_row.request_hash = "f" * 64
    db_session.flush()
    assert client.post(
        f"/action-requests/{request_id}/permit", headers=executive,
    ).status_code == 403
    approval_row.request_hash = original_hash
    db_session.flush()
    permit = client.post(
        f"/action-requests/{request_id}/permit", headers=executive,
    )
    assert permit.status_code == 201, permit.text
    permit_id = permit.json()["id"]
    assert client.post(
        f"/permits/{permit_id}/consume", headers=executive,
        json={"parameters": {"amount": 20}},
    ).status_code == 403
    assert client.put(
        "/governance/global-stop", headers=owner, json={"enabled": True},
    ).status_code == 200
    assert client.post(
        f"/permits/{permit_id}/consume", headers=executive,
        json={"parameters": {"amount": 10}},
    ).status_code == 403
    assert client.put(
        "/governance/global-stop", headers=owner, json={"enabled": False},
    ).status_code == 200
    assert client.put(
        f"/governance/ventures/{venture_id}/freeze", headers=owner,
        json={"enabled": True},
    ).status_code == 200
    assert client.post(
        f"/permits/{permit_id}/consume", headers=executive,
        json={"parameters": {"amount": 10}},
    ).status_code == 403
    assert client.put(
        f"/governance/ventures/{venture_id}/freeze", headers=owner,
        json={"enabled": False},
    ).status_code == 200
    assert client.post(
        f"/permits/{permit_id}/consume", headers=executive,
        json={"parameters": {"amount": 10}},
    ).json() == {"consumed": True}
    assert client.post(
        f"/permits/{permit_id}/consume", headers=executive,
        json={"parameters": {"amount": 10}},
    ).status_code == 403
    assert client.get("/audit/verify", headers=owner).json()["valid"]
    assert client.get("/audit", headers=executive).status_code == 403
    assert client.get(f"/ventures/{uuid4()}", headers=executive).status_code == 404
