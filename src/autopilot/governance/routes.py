import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from autopilot.db import get_session
from autopilot.governance.approvals import (
    InvalidAction,
    RequestConflict,
    request_action,
)
from autopilot.governance.controls import (
    ControlDenied,
    configure_global_budget,
    configure_venture_budget,
    reserve_budget,
    set_global_stop,
    set_venture_freeze,
)
from autopilot.governance.decisions import ApprovalDenied, decide_approval
from autopilot.identity.models import Actor
from autopilot.identity.routes import current_actor
from autopilot.ventures.service import NotFound

router = APIRouter()


class ActionInput(BaseModel):
    venture_id: uuid.UUID
    action: str = Field(min_length=1, max_length=128)
    target: str = Field(min_length=1, max_length=256)
    parameters: dict
    idempotency_key: str = Field(min_length=1, max_length=128)


class ActionOutput(BaseModel):
    id: uuid.UUID
    risk: str
    status: str
    parameters_hash: str


@router.post("/action-requests", response_model=ActionOutput, status_code=201)
def add_action_request(
    payload: ActionInput,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
):
    try:
        record = request_action(
            session, actor, payload.venture_id, payload.action,
            payload.target, payload.parameters, payload.idempotency_key,
        )
        result = ActionOutput.model_validate(record, from_attributes=True)
        session.commit()
        return result
    except NotFound as exc:
        raise HTTPException(status_code=404, detail="NOT_FOUND") from exc
    except RequestConflict as exc:
        raise HTTPException(status_code=409, detail="CONFLICT") from exc
    except InvalidAction as exc:
        raise HTTPException(status_code=422, detail="INVALID_ACTION") from exc


class DecisionInput(BaseModel):
    decision: str
    expires_at: datetime | None = None


class DecisionOutput(BaseModel):
    id: uuid.UUID
    request_id: uuid.UUID
    decision: str
    expires_at: datetime


@router.post(
    "/action-requests/{request_id}/decision",
    response_model=DecisionOutput,
    status_code=201,
)
def decide_action_request(
    request_id: uuid.UUID,
    payload: DecisionInput,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
):
    try:
        approval = decide_approval(
            session, actor.id, request_id, payload.decision,
            datetime.now(UTC), payload.expires_at,
        )
        result = DecisionOutput.model_validate(approval, from_attributes=True)
        session.commit()
        return result
    except ApprovalDenied as exc:
        raise HTTPException(status_code=403, detail="APPROVAL_DENIED") from exc


class CeilingInput(BaseModel):
    ceiling_minor: int = Field(ge=0)


class ToggleInput(BaseModel):
    enabled: bool


class ReservationInput(BaseModel):
    venture_id: uuid.UUID
    amount_minor: int = Field(gt=0)
    idempotency_key: str = Field(min_length=1, max_length=128)


@router.put("/governance/global-budget")
def global_budget(
    payload: CeilingInput,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
):
    try:
        row = configure_global_budget(session, actor.id, payload.ceiling_minor)
        session.commit()
        return {"ceiling_minor": row.budget_ceiling_minor}
    except ControlDenied as exc:
        raise HTTPException(status_code=403, detail="CONTROL_DENIED") from exc


@router.put("/governance/ventures/{venture_id}/budget")
def venture_budget(
    venture_id: uuid.UUID,
    payload: CeilingInput,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
):
    try:
        row = configure_venture_budget(
            session, actor.id, venture_id, payload.ceiling_minor
        )
        session.commit()
        return {"ceiling_minor": row.budget_ceiling_minor}
    except ControlDenied as exc:
        raise HTTPException(status_code=403, detail="CONTROL_DENIED") from exc


@router.put("/governance/global-stop")
def global_stop(
    payload: ToggleInput,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
):
    try:
        set_global_stop(session, actor.id, payload.enabled)
        session.commit()
        return {"enabled": payload.enabled}
    except ControlDenied as exc:
        raise HTTPException(status_code=403, detail="CONTROL_DENIED") from exc


@router.put("/governance/ventures/{venture_id}/freeze")
def venture_freeze(
    venture_id: uuid.UUID,
    payload: ToggleInput,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
):
    try:
        set_venture_freeze(session, actor.id, venture_id, payload.enabled)
        session.commit()
        return {"enabled": payload.enabled}
    except ControlDenied as exc:
        raise HTTPException(status_code=403, detail="CONTROL_DENIED") from exc


@router.post("/governance/reservations", status_code=201)
def add_reservation(
    payload: ReservationInput,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
):
    try:
        row = reserve_budget(
            session, actor.id, payload.venture_id,
            payload.amount_minor, payload.idempotency_key,
        )
        result = {"id": row.id, "amount_minor": row.amount_minor}
        session.commit()
        return result
    except ControlDenied as exc:
        raise HTTPException(status_code=403, detail="CONTROL_DENIED") from exc
