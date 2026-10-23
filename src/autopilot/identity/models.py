import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from autopilot.db import Base


class ActorKind(enum.StrEnum):
    owner = "owner"
    executive = "executive"
    specialist = "specialist"


class Actor(Base):
    __tablename__ = "actors"
    __table_args__ = (
        CheckConstraint("kind != 'owner' OR level = 4", name="ck_owner_level"),
        CheckConstraint("kind = 'owner' OR level < 4", name="ck_agent_not_l4"),
        UniqueConstraint("credential_hash", name="uq_actor_credential_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    kind: Mapped[ActorKind] = mapped_column(
        Enum(ActorKind, name="actor_kind"), nullable=False
    )
    level: Mapped[int] = mapped_column(nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    credential_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
