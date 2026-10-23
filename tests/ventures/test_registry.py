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


def test_two_transactions_same_version_only_one_wins(
    database_engine, monkeypatch,
):
    """Use committed setup and independent connections, not fixture savepoints."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy.orm import Session

    monkeypatch.setenv("AUTOPILOT_BOOTSTRAP_SECRET", "concurrency-secret")
    with Session(database_engine) as setup:
        owner, _ = bootstrap_owner(setup, "concurrency-secret")
        venture = create_venture(setup, owner, "Concurrency")
        task = create_task(setup, owner, venture.id, "Race", "One winner")
        actor_id, venture_id, task_id = owner.id, venture.id, task.id
        setup.commit()

    barrier = Barrier(2)

    def attempt(target):
        from autopilot.identity.models import Actor

        with Session(database_engine) as session:
            actor = session.get(Actor, actor_id)
            loaded = get_task(session, actor, venture_id, task_id)
            assert loaded.version == 1
            barrier.wait(timeout=10)
            try:
                transition_task(
                    session, actor, venture_id, task_id, 1, target
                )
                session.commit()
                return "success"
            except Conflict:
                session.rollback()
                return "conflict"

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(attempt, TaskState.leased)
            second = pool.submit(attempt, TaskState.paused)
            assert sorted((first.result(timeout=20), second.result(timeout=20))) == [
                "conflict", "success",
            ]
        with Session(database_engine) as verify:
            from autopilot.ventures.models import VentureTask

            saved = verify.get(VentureTask, task_id)
            assert saved.version == 2
            assert saved.state in (TaskState.leased, TaskState.paused)
    finally:
        with database_engine.begin() as cleanup:
            from sqlalchemy import delete

            from autopilot.identity.models import Actor
            from autopilot.ventures.models import Venture, VentureTask

            cleanup.execute(delete(VentureTask).where(VentureTask.id == task_id))
            cleanup.execute(delete(Venture).where(Venture.id == venture_id))
            cleanup.execute(delete(Actor).where(Actor.id == actor_id))
