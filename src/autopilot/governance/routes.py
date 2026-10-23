import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from autopilot.db import get_session
from autopilot.governance.approvals import (
    InvalidAction,
    RequestConflict,
    request_action,
)
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
