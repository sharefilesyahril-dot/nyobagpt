import pytest

from autopilot.identity.service import bootstrap_owner
from autopilot.ventures.models import TaskState
from autopilot.ventures.service import (
    Conflict,
    NotFound,
    create_task,
    create_venture,
    get_task,
    transition_task,
)


def test_registry_scope_and_optimistic_transitions(db_session, monkeypatch):
    monkeypatch.setenv("AUTOPILOT_BOOTSTRAP_SECRET", "test-secret")
    owner, _ = bootstrap_owner(db_session, "test-secret")
    first = create_venture(db_session, owner, "First")
    second = create_venture(db_session, owner, "Second")
    with pytest.raises(ValueError):
        create_task(db_session, owner, first.id, "Research", " ")
    task = create_task(db_session, owner, first.id, "Research", "Evidence required")
    with pytest.raises(NotFound):
        get_task(db_session, owner, second.id, task.id)
    with pytest.raises(Conflict):
        transition_task(db_session, owner, first.id, task.id, 1, TaskState.completed)
    updated = transition_task(
        db_session, owner, first.id, task.id, 1, TaskState.leased
    )
    assert updated.version == 2
    with pytest.raises(Conflict):
        transition_task(db_session, owner, first.id, task.id, 1, TaskState.paused)


def test_approval_gate(db_session, monkeypatch):
    monkeypatch.setenv("AUTOPILOT_BOOTSTRAP_SECRET", "test-secret")
    owner, _ = bootstrap_owner(db_session, "test-secret")
    venture = create_venture(db_session, owner, "Approval")
    task = create_task(db_session, owner, venture.id, "Action", "Owner approval")
    with pytest.raises(Conflict):
        transition_task(
            db_session, owner, venture.id, task.id, 1, TaskState.awaiting_approval
        )
    assert transition_task(
        db_session, owner, venture.id, task.id, 1,
        TaskState.awaiting_approval, approved_action=True,
    ).version == 2
