import uuid
from datetime import UTC, datetime, timedelta

import pytest

from autopilot.governance.policy import GrantInput, authorize, revoke_grant, set_grant
from autopilot.identity.models import ActorKind
from autopilot.identity.service import PermissionDenied, bootstrap_owner, create_agent


def test_scoped_grants_default_deny_expiry_budget_and_revoke(db_session, monkeypatch):
    monkeypatch.setenv("AUTOPILOT_BOOTSTRAP_SECRET", "test-secret")
    owner, _ = bootstrap_owner(db_session, "test-secret")
    agent, _ = create_agent(db_session, owner, ActorKind.specialist)
    venture = uuid.uuid4()
    other = uuid.uuid4()
    now = datetime.now(UTC)
    check = lambda v, amount, at=now: authorize(
        db_session, agent.id, v, "draft", "document", amount, at
    )
    assert check(venture, 1).reason_code == "NO_MATCHING_GRANT"
    data = GrantInput(
        actor_id=agent.id, venture_id=venture, action="draft", resource="document",
        budget_ceiling_minor=100, expires_at=now + timedelta(hours=1),
    )
    with pytest.raises(PermissionDenied):
        set_grant(db_session, agent.id, data)
    grant = set_grant(db_session, owner.id, data)
    assert check(venture, 100).grant_id == grant.id
    assert not check(other, 1).allowed
    assert not check(venture, 101).allowed
    assert not check(venture, 1, now + timedelta(hours=2)).allowed
    with pytest.raises(PermissionDenied):
        revoke_grant(db_session, agent.id, grant.id)
    revoke_grant(db_session, owner.id, grant.id)
    assert not check(venture, 1).allowed
    agent.active = False
    db_session.flush()
    assert check(venture, 1).reason_code == "INACTIVE_OR_UNKNOWN_ACTOR"


def test_no_owner_delegation_or_cross_organization(db_session, monkeypatch):
    monkeypatch.setenv("AUTOPILOT_BOOTSTRAP_SECRET", "test-secret")
    owner, _ = bootstrap_owner(db_session, "test-secret")
    agent, _ = create_agent(db_session, owner, ActorKind.executive)
    now = datetime.now(UTC)
    data = GrantInput(
        actor_id=owner.id, venture_id=uuid.uuid4(), action="admin",
        resource="agents", budget_ceiling_minor=0,
        expires_at=now + timedelta(hours=1),
    )
    with pytest.raises(PermissionDenied):
        set_grant(db_session, owner.id, data)
    assert not authorize(
        db_session, agent.id, data.venture_id, "admin", "agents", 0, now
    ).allowed
