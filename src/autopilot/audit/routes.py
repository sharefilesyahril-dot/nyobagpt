import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from autopilot.audit.ledger import verify_audit_chain
from autopilot.audit.models import AuditEntry
from autopilot.db import get_session
from autopilot.identity.models import Actor, ActorKind
from autopilot.identity.routes import current_actor

router = APIRouter()


@router.get("/audit")
def read_audit(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
):
    if not actor.active or actor.kind != ActorKind.owner or actor.level != 4:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    entries = session.scalars(
        select(AuditEntry).order_by(AuditEntry.sequence)
        .offset(offset).limit(limit)
    ).all()
    return [
        {
            "sequence": entry.sequence,
            "event_type": entry.event_type,
            "actor_id": entry.actor_id,
            "subject_id": entry.subject_id,
            "metadata": json.loads(entry.metadata_json),
            "occurred_at": entry.occurred_at,
            "entry_hash": entry.entry_hash,
        }
        for entry in entries
    ]


@router.get("/audit/verify")
def verify_audit(
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
):
    if not actor.active or actor.kind != ActorKind.owner or actor.level != 4:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    result = verify_audit_chain(session)
    return {
        "valid": result.valid,
        "first_invalid_sequence": result.first_invalid_sequence,
    }
