import uuid

import pytest
from sqlalchemy import select

from autopilot.identity.models import Actor, ActorKind
from autopilot.identity.service import (
    AuthenticationError,
    IdentityConflict,
    PermissionDenied,
    authenticate,
    bootstrap_owner,
    create_agent,
)


def test_owner_bootstrap_and_agent_authorization(db_session, monkeypatch):
    monkeypatch.setenv("AUTOPILOT_BOOTSTRAP_SECRET", "test-bootstrap-secret")
    with pytest.raises(PermissionDenied):
        bootstrap_owner(db_session, "wrong")
    owner, owner_token = bootstrap_owner(db_session, "test-bootstrap-secret")
    assert owner.level == 4
    assert authenticate(db_session, owner_token).id == owner.id
    with pytest.raises(IdentityConflict):
        bootstrap_owner(db_session, "test-bootstrap-secret")
    agent, token = create_agent(db_session, owner, ActorKind.executive)
    assert agent.level < 4
    assert agent.organization_id == owner.organization_id
    assert authenticate(db_session, token).id == agent.id
    with pytest.raises(PermissionDenied):
        create_agent(db_session, agent, ActorKind.specialist)
    with pytest.raises(PermissionDenied):
        create_agent(db_session, owner, ActorKind.owner)
    agent.active = False
    db_session.flush()
    with pytest.raises(AuthenticationError):
        authenticate(db_session, token)
    with pytest.raises(AuthenticationError):
        authenticate(db_session, "invalid")


def test_database_enforces_single_owner(db_session, monkeypatch):
    monkeypatch.setenv("AUTOPILOT_BOOTSTRAP_SECRET", "test-bootstrap-secret")
    owner, _ = bootstrap_owner(db_session, "test-bootstrap-secret")
    assert db_session.scalar(select(Actor).where(Actor.id == owner.id)) is owner
    assert owner.organization_id != uuid.UUID(int=0)
