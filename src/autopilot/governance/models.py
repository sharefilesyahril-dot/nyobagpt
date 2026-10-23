import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from autopilot.db import Base


class Grant(Base):
    __tablename__ = "grants"
    __table_args__ = (
        CheckConstraint(
            "budget_ceiling_minor >= 0", name="ck_grant_budget_nonnegative"
        ),
        Index("ix_grants_actor_venture", "actor_id", "venture_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("actors.id"), nullable=False
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    venture_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource: Mapped[str] = mapped_column(String(256), nullable=False)
    budget_ceiling_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ActionRequest(Base):
    __tablename__ = "action_requests"
    __table_args__ = (
        UniqueConstraint(
            "actor_id", "idempotency_key", name="uq_action_actor_idempotency"
        ),
        Index("ix_action_requests_venture", "venture_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("actors.id"), nullable=False
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    venture_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ventures.id"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    target: Mapped[str] = mapped_column(String(256), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False)
    parameters_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    risk: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("action_requests.id"),
        nullable=False, unique=True,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("actors.id"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ExecutionPermit(Base):
    __tablename__ = "execution_permits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("action_requests.id"),
        nullable=False, unique=True,
    )
    parameters_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class GlobalControl(Base):
    __tablename__ = "global_controls"
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    stopped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    budget_ceiling_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    __table_args__ = (
        CheckConstraint(
            "budget_ceiling_minor >= 0 AND reserved_minor >= 0 "
            "AND reserved_minor <= budget_ceiling_minor",
            name="ck_global_budget_bounds",
        ),
    )


class VentureControl(Base):
    __tablename__ = "venture_controls"
    venture_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ventures.id"), primary_key=True
    )
    frozen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    budget_ceiling_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    __table_args__ = (
        CheckConstraint(
            "budget_ceiling_minor >= 0 AND reserved_minor >= 0 "
            "AND reserved_minor <= budget_ceiling_minor",
            name="ck_venture_budget_bounds",
        ),
    )


class BudgetReservation(Base):
    __tablename__ = "budget_reservations"
    __table_args__ = (
        UniqueConstraint(
            "actor_id", "idempotency_key", name="uq_budget_actor_key"
        ),
        CheckConstraint("amount_minor > 0", name="ck_reservation_positive"),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("actors.id"), nullable=False
    )
    venture_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ventures.id"), nullable=False
    )
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
