"""Create single-owner actor identity baseline.

Revision ID: 0001_core_foundation
Revises:
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001_core_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    kind = postgresql.ENUM("owner", "executive", "specialist", name="actor_kind")
    kind.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "actors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", kind, nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("credential_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind != 'owner' OR level = 4", name="ck_owner_level"),
        sa.CheckConstraint("kind = 'owner' OR level < 4", name="ck_agent_not_l4"),
        sa.UniqueConstraint("credential_hash", name="uq_actor_credential_hash"),
    )
    op.create_index("ix_actors_organization_id", "actors", ["organization_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_single_owner "
        "ON actors ((kind)) WHERE kind = 'owner'"
    )


def downgrade() -> None:
    op.drop_index("uq_single_owner", table_name="actors")
    op.drop_index("ix_actors_organization_id", table_name="actors")
    op.drop_table("actors")
    postgresql.ENUM(name="actor_kind").drop(op.get_bind(), checkfirst=True)
