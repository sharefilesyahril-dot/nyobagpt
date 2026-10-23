import uuid
from datetime import UTC, datetime

import pytest

from autopilot.governance.approvals import request_action
from autopilot.governance.controls import (
    ControlDenied,
    configure_global_budget,
    configure_venture_budget,
    reserve_budget,
    set_global_stop,
    set_venture_freeze,
)
from autopilot.governance.decisions import decide_approval
from autopilot.governance.gateway import PermitDenied, authorize_execution
from autopilot.identity.models import ActorKind
from autopilot.identity.service import bootstrap_owner, create_agent
from autopilot.ventures.service import create_venture

NOW = datetime(2026, 10, 23, tzinfo=UTC)


def setup(db_session, monkeypatch):
    monkeypatch.setenv("AUTOPILOT_BOOTSTRAP_SECRET", "controls-secret")
    owner, _ = bootstrap_owner(db_session, "controls-secret")
    first = create_venture(db_session, owner, "First")
    second = create_venture(db_session, owner, "Second")
    configure_global_budget(db_session, owner.id, 100)
    configure_venture_budget(db_session, owner.id, first.id, 60)
    configure_venture_budget(db_session, owner.id, second.id, 60)
    return owner, first, second


def approved(session, owner, venture):
    request = request_action(
        session, owner, venture.id, "payment", "invoice",
        {"amount": 1}, str(uuid.uuid4()),
    )
    decide_approval(session, owner.id, request.id, "approved", NOW)
    return request


def test_owner_only_limits_and_bounded_idempotent_reservations(
    db_session, monkeypatch,
):
    owner, first, _ = setup(db_session, monkeypatch)
    agent, _ = create_agent(db_session, owner, ActorKind.specialist)
    with pytest.raises(ControlDenied):
        configure_global_budget(db_session, agent.id, 100000)
    with pytest.raises(ControlDenied):
        set_global_stop(db_session, agent.id, True)
    with pytest.raises(ControlDenied):
        configure_venture_budget(db_session, agent.id, first.id, 100000)
    reservation = reserve_budget(db_session, owner.id, first.id, 40, "one")
    repeated = reserve_budget(db_session, owner.id, first.id, 40, "one")
    assert repeated.id == reservation.id
    with pytest.raises(ControlDenied):
        reserve_budget(db_session, owner.id, first.id, 41, "one")
    with pytest.raises(ControlDenied):
        reserve_budget(db_session, owner.id, first.id, 21, "two")
    with pytest.raises(ControlDenied):
        configure_venture_budget(db_session, owner.id, first.id, 39)


def test_stop_and_freeze_scope(db_session, monkeypatch):
    owner, first, second = setup(db_session, monkeypatch)
    first_request = approved(db_session, owner, first)
    second_request = approved(db_session, owner, second)
    set_venture_freeze(db_session, owner.id, first.id, True)
    with pytest.raises(PermitDenied):
        authorize_execution(db_session, first_request.id, NOW)
    assert authorize_execution(db_session, second_request.id, NOW)
    set_global_stop(db_session, owner.id, True)
    with pytest.raises(PermitDenied):
        authorize_execution(db_session, first_request.id, NOW)
    with pytest.raises(ControlDenied):
        reserve_budget(db_session, owner.id, second.id, 1, "stopped")


def test_stop_commit_precedes_waiting_permit(database_engine, monkeypatch):
    """A permit waiting on the stop row must observe the committed stop."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from sqlalchemy import delete, select
    from sqlalchemy.orm import Session

    from autopilot.governance.models import (
        ActionRequest,
        Approval,
        GlobalControl,
        VentureControl,
    )
    from autopilot.identity.models import Actor
    from autopilot.ventures.models import Venture

    monkeypatch.setenv("AUTOPILOT_BOOTSTRAP_SECRET", "stop-race-secret")
    with Session(database_engine) as session:
        owner, _ = bootstrap_owner(session, "stop-race-secret")
        venture = create_venture(session, owner, "Stop race")
        configure_global_budget(session, owner.id, 100)
        configure_venture_budget(session, owner.id, venture.id, 100)
        request = approved(session, owner, venture)
        owner_id = owner.id
        organization_id = owner.organization_id
        venture_id = venture.id
        request_id = request.id
        session.commit()

    stop_locked = Event()
    permit_started = Event()

    def stop_first():
        with Session(database_engine) as session:
            row = session.scalar(
                select(GlobalControl).where(
                    GlobalControl.organization_id == organization_id
                ).with_for_update()
            )
            assert row is not None
            stop_locked.set()
            assert permit_started.wait(timeout=15)
            set_global_stop(session, owner_id, True)
            session.commit()

    def attempt_permit():
        assert stop_locked.wait(timeout=15)
        with Session(database_engine) as session:
            permit_started.set()
            try:
                authorize_execution(session, request_id, NOW)
            except PermitDenied:
                session.rollback()
                return "denied"
            session.commit()
            return "issued"

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            stop_future = pool.submit(stop_first)
            permit_future = pool.submit(attempt_permit)
            stop_future.result(timeout=25)
            assert permit_future.result(timeout=25) == "denied"
    finally:
        with database_engine.begin() as cleanup:
            cleanup.execute(delete(Approval).where(Approval.request_id == request_id))
            cleanup.execute(delete(ActionRequest).where(
                ActionRequest.id == request_id
            ))
            cleanup.execute(delete(VentureControl).where(
                VentureControl.venture_id == venture_id
            ))
            cleanup.execute(delete(GlobalControl).where(
                GlobalControl.organization_id == organization_id
            ))
            cleanup.execute(delete(Venture).where(Venture.id == venture_id))
            cleanup.execute(delete(Actor).where(Actor.id == owner_id))
