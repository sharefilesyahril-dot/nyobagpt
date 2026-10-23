"""Exact owner approvals and execution permits.

Revision ID: 0005_exact_approvals
Revises: 0004_action_requests
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005_exact_approvals"
down_revision = "0004_action_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "request_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("action_requests.id"), nullable=False, unique=True,
        ),
        sa.Column(
            "owner_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("actors.id"), nullable=False,
        ),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "execution_permits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "request_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("action_requests.id"), nullable=False, unique=True,
        ),
        sa.Column("parameters_sha256", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("execution_permits")
    op.drop_table("approvals")
