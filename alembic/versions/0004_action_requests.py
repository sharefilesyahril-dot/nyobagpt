"""Governed action requests.

Revision ID: 0004_action_requests
Revises: 0003_venture_registry
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004_action_requests"
down_revision = "0003_venture_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "action_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "actor_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("actors.id"), nullable=False,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "venture_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ventures.id"), nullable=False,
        ),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("target", sa.String(256), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("parameters_hash", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("risk", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "actor_id", "idempotency_key", name="uq_action_actor_idempotency"
        ),
    )
    op.create_index(
        "ix_action_requests_venture", "action_requests", ["venture_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_action_requests_venture", table_name="action_requests")
    op.drop_table("action_requests")
