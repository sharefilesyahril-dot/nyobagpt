"""Exact approval decisions; no external action is executed here."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from autopilot.governance.models import ActionRequest, Approval
from autopilot.identity.models import Actor, ActorKind


class ApprovalDenied(Exception):
    pass


def decide_approval(
    session: Session, owner_id: uuid.UUID, request_id: uuid.UUID,
    decision: str, now: datetime, expires_at: datetime | None = None,
) -> Approval:
    if now.tzinfo is None or decision not in {"approved", "denied"}:
        raise ApprovalDenied("Invalid decision or timestamp")
    owner = session.get(Actor, owner_id)
    if (
        owner is None or not owner.active
        or owner.kind != ActorKind.owner or owner.level != 4
    ):
        raise ApprovalDenied("Owner authority required")
    request = session.scalar(
        select(ActionRequest).where(ActionRequest.id == request_id).with_for_update()
    )
    if request is None or request.organization_id != owner.organization_id:
        raise ApprovalDenied("Request unavailable")
    if request.risk != "high" or request.status != "pending_owner":
        raise ApprovalDenied("Request is not pending owner decision")
    if expires_at is None:
        expires_at = now + timedelta(minutes=15)
    if expires_at.tzinfo is None or expires_at <= now:
        raise ApprovalDenied("Approval must have a future expiry")
    record = Approval(
        request_id=request.id, owner_id=owner.id, decision=decision,
        request_hash=request.request_hash, decided_at=now, expires_at=expires_at,
    )
    request.status = decision
    session.add(record)
    session.flush()
    return record
