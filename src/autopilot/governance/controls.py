"""Owner controls and atomic finite budget reservations."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from autopilot.audit.ledger import AuditEvent, append_audit
from autopilot.governance.models import (
    BudgetReservation,
    GlobalControl,
    VentureControl,
)
from autopilot.governance.policy import authorize
from autopilot.identity.models import Actor, ActorKind
from autopilot.ventures.models import Venture, VentureStatus


class ControlDenied(Exception):
    pass


def _owner(session: Session, owner_id: uuid.UUID) -> Actor:
    actor = session.get(Actor, owner_id)
    if (
        actor is None or not actor.active
        or actor.kind != ActorKind.owner or actor.level != 4
    ):
        raise ControlDenied("Owner authority required")
    return actor


def configure_global_budget(
    session: Session, owner_id: uuid.UUID, ceiling_minor: int,
) -> GlobalControl:
    owner = _owner(session, owner_id)
    if ceiling_minor < 0:
        raise ControlDenied("Negative budget")
    row = session.scalar(select(GlobalControl).where(
        GlobalControl.organization_id == owner.organization_id
    ).with_for_update())
    if row is None:
        row = GlobalControl(
            organization_id=owner.organization_id,
            stopped=False, budget_ceiling_minor=ceiling_minor, reserved_minor=0,
        )
        session.add(row)
    elif ceiling_minor < row.reserved_minor:
        raise ControlDenied("Ceiling below existing reservations")
    else:
        row.budget_ceiling_minor = ceiling_minor
    session.flush()
    append_audit(session, AuditEvent(
        "budget.global_configured", actor_id=str(owner_id),
        subject_id=str(owner.organization_id),
    ))
    return row


def configure_venture_budget(
    session: Session, owner_id: uuid.UUID, venture_id: uuid.UUID,
    ceiling_minor: int,
) -> VentureControl:
    owner = _owner(session, owner_id)
    venture = session.get(Venture, venture_id)
    if (
        venture is None or venture.organization_id != owner.organization_id
        or ceiling_minor < 0
    ):
        raise ControlDenied("Invalid venture or budget")
    row = session.scalar(select(VentureControl).where(
        VentureControl.venture_id == venture_id
    ).with_for_update())
    if row is None:
        row = VentureControl(
            venture_id=venture_id, frozen=False,
            budget_ceiling_minor=ceiling_minor, reserved_minor=0,
        )
        session.add(row)
    elif ceiling_minor < row.reserved_minor:
        raise ControlDenied("Ceiling below existing reservations")
    else:
        row.budget_ceiling_minor = ceiling_minor
    session.flush()
    append_audit(session, AuditEvent(
        "budget.venture_configured", actor_id=str(owner_id),
        subject_id=str(venture_id),
    ))
    return row


def set_global_stop(
    session: Session, owner_id: uuid.UUID, enabled: bool,
) -> None:
    owner = _owner(session, owner_id)
    row = session.scalar(select(GlobalControl).where(
        GlobalControl.organization_id == owner.organization_id
    ).with_for_update())
    if row is None:
        raise ControlDenied("Configure finite global budget first")
    row.stopped = enabled
    session.flush()
    append_audit(session, AuditEvent(
        "control.global_stop_changed", actor_id=str(owner_id),
        subject_id=str(owner.organization_id),
    ))


def set_venture_freeze(
    session: Session, owner_id: uuid.UUID, venture_id: uuid.UUID, enabled: bool,
) -> None:
    owner = _owner(session, owner_id)
    venture = session.get(Venture, venture_id)
    if venture is None or venture.organization_id != owner.organization_id:
        raise ControlDenied("Venture unavailable")
    # Lock global before venture for a consistent lock order.
    global_row = session.scalar(select(GlobalControl).where(
        GlobalControl.organization_id == owner.organization_id
    ).with_for_update())
    if global_row is None:
        raise ControlDenied("Configure finite global budget first")
    row = session.scalar(select(VentureControl).where(
        VentureControl.venture_id == venture_id
    ).with_for_update())
    if row is None:
        raise ControlDenied("Configure finite venture budget first")
    row.frozen = enabled
    session.flush()
    append_audit(session, AuditEvent(
        "control.venture_freeze_changed", actor_id=str(owner_id),
        subject_id=str(venture_id),
    ))


def check_controls(
    session: Session, organization_id: uuid.UUID, venture_id: uuid.UUID,
) -> tuple[GlobalControl, VentureControl]:
    global_row = session.scalar(select(GlobalControl).where(
        GlobalControl.organization_id == organization_id
    ).with_for_update())
    if global_row is None or global_row.stopped:
        raise ControlDenied("Global control missing or stopped")
    venture_row = session.scalar(select(VentureControl).where(
        VentureControl.venture_id == venture_id
    ).with_for_update())
    if venture_row is None or venture_row.frozen:
        raise ControlDenied("Venture control missing or frozen")
    return global_row, venture_row


def reserve_budget(
    session: Session, actor_id: uuid.UUID, venture_id: uuid.UUID,
    amount_minor: int, idempotency_key: str,
) -> BudgetReservation:
    actor = session.get(Actor, actor_id)
    venture = session.get(Venture, venture_id)
    if (
        actor is None or not actor.active or venture is None
        or actor.organization_id != venture.organization_id
        or venture.status != VentureStatus.active
        or amount_minor <= 0 or not idempotency_key
        or len(idempotency_key) > 128
    ):
        raise ControlDenied("Invalid reservation")
    global_row, venture_row = check_controls(
        session, actor.organization_id, venture_id
    )
    existing = session.scalar(select(BudgetReservation).where(
        BudgetReservation.actor_id == actor_id,
        BudgetReservation.idempotency_key == idempotency_key,
    ))
    if existing is not None:
        if existing.venture_id != venture_id or existing.amount_minor != amount_minor:
            raise ControlDenied("Idempotency key conflict")
        return existing
    if actor.kind != ActorKind.owner:
        decision = authorize(
            session, actor_id, venture_id, "reserve_budget", "budget",
            amount_minor, datetime.now(UTC),
        )
        if not decision.allowed:
            raise ControlDenied("Budget grant required")
    if (
        global_row.reserved_minor + amount_minor > global_row.budget_ceiling_minor
        or venture_row.reserved_minor + amount_minor
        > venture_row.budget_ceiling_minor
    ):
        raise ControlDenied("Budget exceeded")
    global_row.reserved_minor += amount_minor
    venture_row.reserved_minor += amount_minor
    reservation = BudgetReservation(
        actor_id=actor_id, venture_id=venture_id,
        amount_minor=amount_minor, idempotency_key=idempotency_key,
    )
    session.add(reservation)
    session.flush()
    append_audit(session, AuditEvent(
        "budget.reserved", actor_id=str(actor_id),
        subject_id=str(reservation.id),
    ))
    return reservation
