from fastapi.testclient import TestClient

from autopilot.app import create_app
from autopilot.audit.ledger import AuditEvent, append_audit
from autopilot.db import get_session
from autopilot.identity.models import ActorKind
from autopilot.identity.service import bootstrap_owner, create_agent


def test_audit_is_owner_only_and_paginated(db_session, monkeypatch):
    monkeypatch.setenv("AUTOPILOT_BOOTSTRAP_SECRET", "audit-api-secret")
    owner, token = bootstrap_owner(db_session, "audit-api-secret")
    _, agent_token = create_agent(db_session, owner, ActorKind.specialist)
    append_audit(db_session, AuditEvent(
        "test.api", actor_id=str(owner.id), metadata={"token": "hidden"},
    ))
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    client = TestClient(app)
    assert client.get("/audit").status_code == 401
    assert client.get(
        "/audit", headers={"Authorization": f"Bearer {agent_token}"},
    ).status_code == 403
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/audit?offset=0&limit=1", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["metadata"]["token"] == "[REDACTED]"
    assert client.get("/audit/verify", headers=headers).json()["valid"]
