"""Recorded, single-use authorization only; never executes an external effect."""

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from autopilot.governance.approvals import _canonical, _hash
from autopilot.governance.controls import ControlDenied, check_controls
from autopilot.governance.models import ActionRequest, Approval, ExecutionPermit
from autopilot.governance.policy import authorize
from autopilot.identity.models import Actor, ActorKind
from autopilot.ventures.models import Venture, VentureStatus


class PermitDenied(Exception):
    pass


def _check_current_policy(session: Session, request: ActionRequest, now: datetime):
    actor = session.get(Actor, request.actor_id)
    venture = session.get(Venture, request.venture_id)
    if (
        actor is None or not actor.active or venture is None
        or venture.status != VentureStatus.active
        or actor.organization_id != request.organization_id
        or venture.organization_id != request.organization_id
    ):
        raise PermitDenied("Actor or venture unavailable")
    if actor.kind == ActorKind.owner and actor.level == 4:
        return
    decision = authorize(
        session, actor.id, venture.id, request.action, request.target, 0, now
    )
    if not decision.allowed:
        raise PermitDenied("Current grant does not authorize action")


def authorize_execution(
    session: Session, request_id: uuid.UUID, now: datetime,
) -> ExecutionPermit:
    if now.tzinfo is None:
        raise PermitDenied("Timezone-aware timestamp required")
    request = session.scalar(
        select(ActionRequest).where(ActionRequest.id == request_id).with_for_update()
    )
    if request is None or request.risk != "high" or request.status != "approved":
        raise PermitDenied("Exact owner approval required")
    approval = session.scalar(
        select(Approval).where(Approval.request_id == request_id)
    )
    if (
        approval is None or approval.decision != "approved"
        or approval.expires_at <= now
        or approval.request_hash != request.request_hash
    ):
        raise PermitDenied("Approval missing, expired or changed")
    try:
        check_controls(session, request.organization_id, request.venture_id)
    except ControlDenied as exc:
        raise PermitDenied("Stop or freeze blocks permit") from exc
    _check_current_policy(session, request, now)
    existing = session.scalar(select(ExecutionPermit).where(
        ExecutionPermit.request_id == request_id
    ))
    if existing is not None:
        raise PermitDenied("Permit already issued")
    record = ExecutionPermit(
        request_id=request.id, parameters_sha256=request.parameters_hash,
        request_hash=request.request_hash, expires_at=approval.expires_at,
    )
    session.add(record)
    session.flush()
    return record


def consume_permit(
    session: Session, permit_id: uuid.UUID, parameters: dict, now: datetime,
) -> None:
    if now.tzinfo is None or not isinstance(parameters, dict):
        raise PermitDenied("Invalid timestamp or parameters")
    permit = session.scalar(
        select(ExecutionPermit).where(
            ExecutionPermit.id == permit_id
        ).with_for_update()
    )
    if permit is None or permit.used_at is not None or permit.expires_at <= now:
        raise PermitDenied("Permit unavailable, used or expired")
    request = session.get(ActionRequest, permit.request_id)
    approval = session.scalar(select(Approval).where(
        Approval.request_id == permit.request_id
    ))
    if (
        request is None or request.status != "approved"
        or approval is None or approval.decision != "approved"
        or approval.expires_at <= now
        or request.request_hash != permit.request_hash
        or approval.request_hash != permit.request_hash
        or _hash(_canonical(parameters)) != permit.parameters_sha256
    ):
        raise PermitDenied("Permit parameters or approval invalid")
    try:
        check_controls(session, request.organization_id, request.venture_id)
    except ControlDenied as exc:
        raise PermitDenied("Stop or freeze blocks consumption") from exc
    _check_current_policy(session, request, now)
    result = session.execute(
        update(ExecutionPermit).where(
            ExecutionPermit.id == permit_id,
            ExecutionPermit.used_at.is_(None),
            ExecutionPermit.expires_at > now,
        ).values(used_at=now).execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise PermitDenied("Permit already consumed")
    session.expire(permit)
