"""Add scoped grants.

Revision ID: 0002_scoped_grants
Revises: 0001_core_foundation
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0002_scoped_grants"
down_revision = "0001_core_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "actor_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("actors.id"), nullable=False,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("venture_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("resource", sa.String(length=256), nullable=False),
        sa.Column("budget_ceiling_minor", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "budget_ceiling_minor >= 0", name="ck_grant_budget_nonnegative"
        ),
    )
    op.create_index("ix_grants_actor_venture", "grants", ["actor_id", "venture_id"])


def downgrade() -> None:
    op.drop_index("ix_grants_actor_venture", table_name="grants")
    op.drop_table("grants")
