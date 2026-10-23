import enum
import uuid

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from autopilot.db import Base


class VentureStage(enum.StrEnum):
    discovery = "discovery"
    evidence_collection = "evidence_collection"
    validation = "validation"
    selection = "selection"
    mvp_proposal = "mvp_proposal"
    quality_review = "quality_review"
    launch_pending = "launch_pending"
    growth_review = "growth_review"


class VentureStatus(enum.StrEnum):
    active = "active"
    paused = "paused"
    stopped = "stopped"


class TaskState(enum.StrEnum):
    queued = "queued"
    leased = "leased"
    running = "running"
    awaiting_review = "awaiting_review"
    awaiting_approval = "awaiting_approval"
    completed = "completed"
    failed = "failed"
    paused = "paused"
    cancelled = "cancelled"


class Venture(Base):
    __tablename__ = "ventures"
    __table_args__ = (Index("ix_ventures_org", "organization_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    stage: Mapped[VentureStage] = mapped_column(
        Enum(VentureStage, name="venture_stage"), nullable=False,
        default=VentureStage.discovery,
    )
    status: Mapped[VentureStatus] = mapped_column(
        Enum(VentureStatus, name="venture_status"), nullable=False,
        default=VentureStatus.active,
    )


class VentureTask(Base):
    __tablename__ = "venture_tasks"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_task_version_positive"),
        CheckConstraint(
            "length(trim(acceptance_criteria)) > 0",
            name="ck_task_acceptance_nonempty",
        ),
        Index("ix_tasks_venture", "venture_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    venture_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ventures.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    acceptance_criteria: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[TaskState] = mapped_column(
        Enum(TaskState, name="task_state"), nullable=False, default=TaskState.queued
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
