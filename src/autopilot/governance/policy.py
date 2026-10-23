import uuid
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, Field
from autopilot.audit.ledger import AuditEvent, append_audit

from sqlalchemy import select
from sqlalchemy.orm import Session

from autopilot.governance.models import Grant
from autopilot.identity.models import Actor, ActorKind
from autopilot.identity.service import PermissionDenied


class GrantInput(BaseModel):
    actor_id: uuid.UUID
    venture_id: uuid.UUID
    action: str = Field(min_length=1, max_length=128)
    resource: str = Field(min_length=1, max_length=256)
    budget_ceiling_minor: int = Field(ge=0)
    expires_at: datetime


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason_code: str
    grant_id: uuid.UUID | None = None


def _require_owner(session: Session, owner_id: uuid.UUID) -> Actor:
    owner = session.get(Actor, owner_id)
    if owner is None or not owner.active or owner.kind != ActorKind.owner:
        raise PermissionDenied("Owner authority required")
    if owner.level != 4:
        raise PermissionDenied("L4 owner authority required")
    return owner


def set_grant(session: Session, owner_id: uuid.UUID, grant: GrantInput) -> Grant:
    owner = _require_owner(session, owner_id)
    actor = session.get(Actor, grant.actor_id)
    if (
        actor is None
        or not actor.active
        or actor.organization_id != owner.organization_id
    ):
        raise PermissionDenied("Target actor unavailable")
    if actor.kind == ActorKind.owner:
        raise PermissionDenied("Owner authority cannot be delegated")
    if grant.expires_at.tzinfo is None:
        raise ValueError("Grant expiry must be timezone-aware")
    record = Grant(
        actor_id=actor.id,
        organization_id=owner.organization_id,
        venture_id=grant.venture_id,
        action=grant.action,
        resource=grant.resource,
        budget_ceiling_minor=grant.budget_ceiling_minor,
        expires_at=grant.expires_at,
    )
    session.add(record)
    session.flush()
    append_audit(session, AuditEvent("grant.created", subject_id=str(record.id)))
    return record


def revoke_grant(session: Session, owner_id: uuid.UUID, grant_id: uuid.UUID) -> None:
    owner = _require_owner(session, owner_id)
    record = session.get(Grant, grant_id)
    if record is None or record.organization_id != owner.organization_id:
        raise PermissionDenied("Grant unavailable")
    record.active = False
    session.flush()
    append_audit(session, AuditEvent("grant.revoked", subject_id=str(record.id)))


def authorize(
    session: Session,
    actor_id: uuid.UUID,
    venture_id: uuid.UUID,
    action: str,
    resource: str,
    budget_minor: int,
    now: datetime,
) -> PolicyDecision:
    actor = session.get(Actor, actor_id)
    if actor is None or not actor.active:
        return PolicyDecision(False, "INACTIVE_OR_UNKNOWN_ACTOR")
    if budget_minor < 0 or now.tzinfo is None:
        return PolicyDecision(False, "INVALID_REQUEST")
    if actor.kind == ActorKind.owner and actor.level == 4:
        return PolicyDecision(True, "OWNER_AUTHORITY")
    if actor.level >= 4:
        return PolicyDecision(False, "INVALID_AGENT_LEVEL")
    matches = session.scalars(
        select(Grant).where(
            Grant.actor_id == actor.id,
            Grant.organization_id == actor.organization_id,
            Grant.venture_id == venture_id,
            Grant.action == action,
            Grant.resource == resource,
            Grant.active.is_(True),
            Grant.expires_at > now,
            Grant.budget_ceiling_minor >= budget_minor,
        ).order_by(Grant.id)
    ).first()
    if matches is None:
        return PolicyDecision(False, "NO_MATCHING_GRANT")
    return PolicyDecision(True, "GRANTED", matches.id)
