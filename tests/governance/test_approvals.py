import uuid
from datetime import UTC, datetime, timedelta

import pytest

from autopilot.governance.approvals import request_action
from autopilot.governance.decisions import ApprovalDenied, decide_approval
from autopilot.governance.gateway import (
    PermitDenied,
    authorize_execution,
    consume_permit,
)
from autopilot.identity.models import ActorKind
from autopilot.identity.service import bootstrap_owner, create_agent
from autopilot.ventures.service import create_venture

NOW = datetime(2026, 10, 23, tzinfo=UTC)


def setup_request(session, monkeypatch):
    monkeypatch.setenv("AUTOPILOT_BOOTSTRAP_SECRET", "test-secret")
    owner, _ = bootstrap_owner(session, "test-secret")
    venture = create_venture(session, owner, "Approval tests")
    request = request_action(
        session, owner, venture.id, "payment", "invoice",
        {"amount": 100}, str(uuid.uuid4()),
    )
    return owner, venture, request


def test_owner_only_pending_denial_and_expiry(db_session, monkeypatch):
    owner, _, request = setup_request(db_session, monkeypatch)
    agent, _ = create_agent(db_session, owner, ActorKind.specialist)
    assert request.status == "pending_owner"
    with pytest.raises(PermitDenied):
        authorize_execution(db_session, request.id, NOW)
    with pytest.raises(ApprovalDenied):
        decide_approval(db_session, agent.id, request.id, "approved", NOW)
    with pytest.raises(ApprovalDenied):
        decide_approval(
            db_session, owner.id, request.id, "approved", NOW,
            expires_at=NOW - timedelta(seconds=1),
        )
    denied = decide_approval(db_session, owner.id, request.id, "denied", NOW)
    assert denied.decision == "denied"
    with pytest.raises(PermitDenied):
        authorize_execution(db_session, request.id, NOW)
    with pytest.raises(ApprovalDenied):
        decide_approval(db_session, owner.id, request.id, "approved", NOW)


def test_exact_single_use_and_expired_approval(db_session, monkeypatch):
    owner, venture, request = setup_request(db_session, monkeypatch)
    decide_approval(
        db_session, owner.id, request.id, "approved", NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    with pytest.raises(PermitDenied):
        authorize_execution(db_session, request.id, NOW + timedelta(minutes=6))
    permit = authorize_execution(db_session, request.id, NOW)
    with pytest.raises(PermitDenied):
        authorize_execution(db_session, request.id, NOW)
    with pytest.raises(PermitDenied):
        consume_permit(db_session, permit.id, {"amount": 101}, NOW)
    consume_permit(db_session, permit.id, {"amount": 100}, NOW)
    with pytest.raises(PermitDenied):
        consume_permit(db_session, permit.id, {"amount": 100}, NOW)
    assert venture.id == request.venture_id


def test_revoked_grant_after_approval(db_session, monkeypatch):
    from autopilot.governance.policy import GrantInput, revoke_grant, set_grant

    owner, venture, _ = setup_request(db_session, monkeypatch)
    agent, _ = create_agent(db_session, owner, ActorKind.specialist)
    grant = set_grant(db_session, owner.id, GrantInput(
        actor_id=agent.id, venture_id=venture.id, action="write",
        resource="venture", budget_ceiling_minor=0,
        expires_at=NOW + timedelta(days=10),
    ))
    action_grant = set_grant(db_session, owner.id, GrantInput(
        actor_id=agent.id, venture_id=venture.id, action="payment",
        resource="invoice", budget_ceiling_minor=0,
        expires_at=NOW + timedelta(days=10),
    ))
    request = request_action(
        db_session, agent, venture.id, "payment", "invoice",
        {"amount": 100}, str(uuid.uuid4()),
    )
    decide_approval(db_session, owner.id, request.id, "approved", NOW)
    revoke_grant(db_session, owner.id, action_grant.id)
    with pytest.raises(PermitDenied):
        authorize_execution(db_session, request.id, NOW)
    assert grant.active


def test_grant_revoked_before_consumption(db_session, monkeypatch):
    from autopilot.governance.policy import GrantInput, revoke_grant, set_grant

    owner, venture, _ = setup_request(db_session, monkeypatch)
    agent, _ = create_agent(db_session, owner, ActorKind.specialist)
    set_grant(db_session, owner.id, GrantInput(
        actor_id=agent.id, venture_id=venture.id, action="write",
        resource="venture", budget_ceiling_minor=0,
        expires_at=NOW + timedelta(days=10),
    ))
    action_grant = set_grant(db_session, owner.id, GrantInput(
        actor_id=agent.id, venture_id=venture.id, action="payment",
        resource="invoice", budget_ceiling_minor=0,
        expires_at=NOW + timedelta(days=10),
    ))
    request = request_action(
        db_session, agent, venture.id, "payment", "invoice",
        {"amount": 100}, str(uuid.uuid4()),
    )
    decide_approval(db_session, owner.id, request.id, "approved", NOW)
    permit = authorize_execution(db_session, request.id, NOW)
    revoke_grant(db_session, owner.id, action_grant.id)
    with pytest.raises(PermitDenied):
        consume_permit(db_session, permit.id, {"amount": 100}, NOW)


def test_concurrent_consumption_has_exactly_one_winner(
    database_engine, monkeypatch,
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy import delete
    from sqlalchemy.orm import Session

    from autopilot.governance.models import ActionRequest, Approval, ExecutionPermit
    from autopilot.identity.models import Actor
    from autopilot.ventures.models import Venture

    monkeypatch.setenv("AUTOPILOT_BOOTSTRAP_SECRET", "permit-race-secret")
    with Session(database_engine) as setup:
        owner, _ = bootstrap_owner(setup, "permit-race-secret")
        venture = create_venture(setup, owner, "Permit race")
        request = request_action(
            setup, owner, venture.id, "payment", "invoice",
            {"amount": 100}, "permit-race-key",
        )
        decide_approval(setup, owner.id, request.id, "approved", NOW)
        permit = authorize_execution(setup, request.id, NOW)
        owner_id, venture_id = owner.id, venture.id
        request_id, permit_id = request.id, permit.id
        setup.commit()

    barrier = Barrier(2)

    def attempt():
        with Session(database_engine) as session:
            barrier.wait(timeout=10)
            try:
                consume_permit(session, permit_id, {"amount": 100}, NOW)
                session.commit()
                return "success"
            except PermitDenied:
                session.rollback()
                return "denied"

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(attempt)
            second = pool.submit(attempt)
            assert sorted((first.result(timeout=20), second.result(timeout=20))) == [
                "denied", "success",
            ]
        with Session(database_engine) as verify:
            assert verify.get(ExecutionPermit, permit_id).used_at is not None
    finally:
        with database_engine.begin() as cleanup:
            cleanup.execute(delete(ExecutionPermit).where(
                ExecutionPermit.id == permit_id
            ))
            cleanup.execute(delete(Approval).where(Approval.request_id == request_id))
            cleanup.execute(delete(ActionRequest).where(
                ActionRequest.id == request_id
            ))
            cleanup.execute(delete(Venture).where(Venture.id == venture_id))
            cleanup.execute(delete(Actor).where(Actor.id == owner_id))
