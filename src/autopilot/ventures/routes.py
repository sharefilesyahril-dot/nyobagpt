import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from autopilot.db import get_session
from autopilot.identity.models import Actor
from autopilot.identity.routes import current_actor
from autopilot.ventures.models import TaskState, VentureStage, VentureStatus
from autopilot.ventures.service import (
    Conflict,
    NotFound,
    create_task,
    create_venture,
    get_task,
    get_venture,
    transition_task,
)

router = APIRouter()


class VentureInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class VentureOutput(BaseModel):
    id: uuid.UUID
    name: str
    stage: VentureStage
    status: VentureStatus


class TaskInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    acceptance_criteria: str = Field(min_length=1)


class TaskOutput(BaseModel):
    id: uuid.UUID
    venture_id: uuid.UUID
    title: str
    acceptance_criteria: str
    state: TaskState
    version: int


class TransitionInput(BaseModel):
    expected_version: int = Field(ge=1)
    target: TaskState
    approved_action: bool = False


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFound):
        return HTTPException(status_code=404, detail="NOT_FOUND")
    if isinstance(exc, Conflict):
        return HTTPException(status_code=409, detail="CONFLICT")
    return HTTPException(status_code=422, detail="INVALID_INPUT")


@router.post("/ventures", response_model=VentureOutput, status_code=201)
def add_venture(
    payload: VentureInput,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
):
    try:
        venture = create_venture(session, actor, payload.name)
        result = VentureOutput.model_validate(venture, from_attributes=True)
        session.commit()
        return result
    except (NotFound, ValueError) as exc:
        raise _error(exc) from exc


@router.get("/ventures/{venture_id}", response_model=VentureOutput)
def read_venture(
    venture_id: uuid.UUID,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
):
    try:
        return VentureOutput.model_validate(
            get_venture(session, actor, venture_id), from_attributes=True
        )
    except NotFound as exc:
        raise _error(exc) from exc


@router.post(
    "/ventures/{venture_id}/tasks", response_model=TaskOutput, status_code=201
)
def add_task(
    venture_id: uuid.UUID,
    payload: TaskInput,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
):
    try:
        task = create_task(
            session, actor, venture_id, payload.title, payload.acceptance_criteria
        )
        result = TaskOutput.model_validate(task, from_attributes=True)
        session.commit()
        return result
    except (NotFound, Conflict, ValueError) as exc:
        raise _error(exc) from exc


@router.get("/ventures/{venture_id}/tasks/{task_id}", response_model=TaskOutput)
def read_task(
    venture_id: uuid.UUID,
    task_id: uuid.UUID,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
):
    try:
        return TaskOutput.model_validate(
            get_task(session, actor, venture_id, task_id), from_attributes=True
        )
    except NotFound as exc:
        raise _error(exc) from exc


@router.post(
    "/ventures/{venture_id}/tasks/{task_id}/transition",
    response_model=TaskOutput,
)
def change_task(
    venture_id: uuid.UUID,
    task_id: uuid.UUID,
    payload: TransitionInput,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
):
    try:
        task = transition_task(
            session, actor, venture_id, task_id,
            payload.expected_version, payload.target, payload.approved_action,
        )
        result = TaskOutput.model_validate(task, from_attributes=True)
        session.commit()
        return result
    except (NotFound, Conflict) as exc:
        raise _error(exc) from exc
