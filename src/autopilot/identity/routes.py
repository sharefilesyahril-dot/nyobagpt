import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from autopilot.audit.ledger import AuditEvent, append_audit
from autopilot.db import get_session
from autopilot.identity.models import Actor, ActorKind
from autopilot.identity.service import (
    AuthenticationError,
    PermissionDenied,
    authenticate,
    create_agent,
)

router = APIRouter()


class AgentInput(BaseModel):
    kind: ActorKind


class AgentOutput(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    kind: ActorKind
    level: int
    credential: str


def current_actor(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> Actor:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")
    try:
        return authenticate(session, authorization.removeprefix("Bearer "))
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED") from exc


@router.post("/agents", response_model=AgentOutput, status_code=201)
def add_agent(
    payload: AgentInput,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> AgentOutput:
    try:
        agent, credential = create_agent(session, actor, payload.kind)
        append_audit(session, AuditEvent(
            event_type="identity.agent_created", actor_id=str(actor.id),
        ))
        session.commit()
    except PermissionDenied as exc:
        raise HTTPException(status_code=403, detail="FORBIDDEN") from exc
    return AgentOutput(
        id=agent.id,
        organization_id=agent.organization_id,
        kind=agent.kind,
        level=agent.level,
        credential=credential,
    )
