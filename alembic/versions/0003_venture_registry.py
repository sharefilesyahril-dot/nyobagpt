"""Venture registry migration."""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "0003_venture_registry"
down_revision = "0002_scoped_grants"
branch_labels = None
depends_on = None

stage = postgresql.ENUM("discovery", "evidence_collection", "validation", "selection", "mvp_proposal", "quality_review", "launch_pending", "growth_review", name="venture_stage", create_type=False)
status = postgresql.ENUM("active", "paused", "stopped", name="venture_status", create_type=False)
state = postgresql.ENUM("queued", "leased", "running", "awaiting_review", "awaiting_approval", "completed", "failed", "paused", "cancelled", name="task_state", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    for kind in (stage, status, state):
        kind.create(bind, checkfirst=True)
    op.create_table(
        "ventures",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("stage", stage, nullable=False),
        sa.Column("status", status, nullable=False),
    )
    op.create_index("ix_ventures_org", "ventures", ["organization_id"])
    op.create_table(
        "venture_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("venture_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ventures.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("acceptance_criteria", sa.Text(), nullable=False),
        sa.Column("state", state, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_task_version_positive"),
        sa.CheckConstraint("length(trim(acceptance_criteria)) > 0", name="ck_task_acceptance_nonempty"),
    )
    op.create_index("ix_tasks_venture", "venture_tasks", ["venture_id"])


def downgrade() -> None:
    op.drop_index("ix_tasks_venture", table_name="venture_tasks")
    op.drop_table("venture_tasks")
    op.drop_index("ix_ventures_org", table_name="ventures")
    op.drop_table("ventures")
    for kind in (state, status, stage):
        kind.drop(op.get_bind(), checkfirst=True)
