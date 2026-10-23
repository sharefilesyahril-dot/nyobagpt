import uuid

from autopilot.audit.ledger import AuditEvent, append_audit
from sqlalchemy import update
from sqlalchemy.orm import Session

from autopilot.governance.policy import authorize
from autopilot.identity.models import Actor, ActorKind
from autopilot.ventures.models import TaskState, Venture, VentureStatus, VentureTask


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


TRANSITIONS = {
    TaskState.queued: {TaskState.leased, TaskState.paused, TaskState.cancelled},
    TaskState.leased: {TaskState.running, TaskState.queued, TaskState.cancelled},
    TaskState.running: {
        TaskState.awaiting_review, TaskState.failed, TaskState.paused,
        TaskState.cancelled,
    },
    TaskState.awaiting_review: {
        TaskState.completed, TaskState.running, TaskState.failed,
    },
    TaskState.awaiting_approval: {TaskState.queued, TaskState.cancelled},
    TaskState.paused: {TaskState.queued, TaskState.cancelled},
    TaskState.failed: {TaskState.queued, TaskState.cancelled},
    TaskState.completed: set(),
    TaskState.cancelled: set(),
}


def _scope(session: Session, actor: Actor, venture: Venture, action: str) -> None:
    if not actor.active or venture.organization_id != actor.organization_id:
        raise NotFound("Resource unavailable")
    if actor.kind == ActorKind.owner and actor.level == 4:
        return
    from datetime import UTC, datetime

    decision = authorize(
        session, actor.id, venture.id, action, "venture", 0, datetime.now(UTC)
    )
    if not decision.allowed:
        raise NotFound("Resource unavailable")


def create_venture(session: Session, actor: Actor, name: str) -> Venture:
    if not actor.active or actor.kind != ActorKind.owner or actor.level != 4:
        raise NotFound("Resource unavailable")
    if not name.strip():
        raise ValueError("Venture name required")
    venture = Venture(organization_id=actor.organization_id, name=name.strip())
    session.add(venture)
    session.flush()
    append_audit(session, AuditEvent(
        "venture.created", actor_id=str(actor.id), subject_id=str(venture.id),
    ))
    return venture


def get_venture(
    session: Session, actor: Actor, venture_id: uuid.UUID, action: str = "read"
) -> Venture:
    venture = session.get(Venture, venture_id)
    if venture is None:
        raise NotFound("Resource unavailable")
    _scope(session, actor, venture, action)
    return venture


def create_task(
    session: Session, actor: Actor, venture_id: uuid.UUID,
    title: str, acceptance_criteria: str,
) -> VentureTask:
    venture = get_venture(session, actor, venture_id, "write")
    if venture.status != VentureStatus.active:
        raise Conflict("Venture is not active")
    if not title.strip() or not acceptance_criteria.strip():
        raise ValueError("Title and acceptance criteria required")
    task = VentureTask(
        venture_id=venture.id, title=title.strip(),
        acceptance_criteria=acceptance_criteria.strip(),
    )
    session.add(task)
    session.flush()
    append_audit(session, AuditEvent(
        "task.created", actor_id=str(actor.id), subject_id=str(task.id),
    ))
    return task


def get_task(
    session: Session, actor: Actor, venture_id: uuid.UUID, task_id: uuid.UUID,
) -> VentureTask:
    get_venture(session, actor, venture_id)
    task = session.get(VentureTask, task_id)
    if task is None or task.venture_id != venture_id:
        raise NotFound("Resource unavailable")
    return task


def transition_task(
    session: Session, actor: Actor, venture_id: uuid.UUID, task_id: uuid.UUID,
    expected_version: int, target: TaskState, approved_action: bool = False,
) -> VentureTask:
    venture = get_venture(session, actor, venture_id, "write")
    if venture.status != VentureStatus.active:
        raise Conflict("Venture is not active")
    task = session.get(VentureTask, task_id)
    if task is None or task.venture_id != venture_id:
        raise NotFound("Resource unavailable")
    if task.version != expected_version:
        raise Conflict("Task version mismatch")
    allowed = target in TRANSITIONS[task.state]
    if task.state == TaskState.queued and target == TaskState.awaiting_approval:
        allowed = approved_action
    if not allowed:
        raise Conflict("Illegal task transition")
    result = session.execute(
        update(VentureTask).where(
            VentureTask.id == task_id,
            VentureTask.venture_id == venture_id,
            VentureTask.version == expected_version,
            VentureTask.state == task.state,
        ).values(state=target, version=expected_version + 1)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise Conflict("Concurrent task update")
    session.expire(task)
    session.flush()
    append_audit(session, AuditEvent(
        "task.transitioned", actor_id=str(actor.id), subject_id=str(task.id),
        metadata={"target": target.value},
    ))
    return task
