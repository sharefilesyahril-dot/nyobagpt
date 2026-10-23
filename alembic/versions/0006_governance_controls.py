"""Finite stop, freeze and budget controls.

Revision ID: 0006_governance_controls
Revises: 0005_exact_approvals
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0006_governance_controls"
down_revision = "0005_exact_approvals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "global_controls",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("stopped", sa.Boolean(), nullable=False),
        sa.Column("budget_ceiling_minor", sa.Integer(), nullable=False),
        sa.Column("reserved_minor", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "budget_ceiling_minor >= 0 AND reserved_minor >= 0 "
            "AND reserved_minor <= budget_ceiling_minor",
            name="ck_global_budget_bounds",
        ),
    )
    op.create_table(
        "venture_controls",
        sa.Column(
            "venture_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ventures.id"), primary_key=True,
        ),
        sa.Column("frozen", sa.Boolean(), nullable=False),
        sa.Column("budget_ceiling_minor", sa.Integer(), nullable=False),
        sa.Column("reserved_minor", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "budget_ceiling_minor >= 0 AND reserved_minor >= 0 "
            "AND reserved_minor <= budget_ceiling_minor",
            name="ck_venture_budget_bounds",
        ),
    )
    op.create_table(
        "budget_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "actor_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("actors.id"), nullable=False,
        ),
        sa.Column(
            "venture_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ventures.id"), nullable=False,
        ),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.UniqueConstraint(
            "actor_id", "idempotency_key", name="uq_budget_actor_key",
        ),
        sa.CheckConstraint("amount_minor > 0", name="ck_reservation_positive"),
    )


def downgrade() -> None:
    op.drop_table("budget_reservations")
    op.drop_table("venture_controls")
    op.drop_table("global_controls")
