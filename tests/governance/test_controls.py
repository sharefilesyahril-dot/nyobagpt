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
    assert reserve_budget(db_session, owner.id, first.id, 40, "one").id == reservation.id
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
