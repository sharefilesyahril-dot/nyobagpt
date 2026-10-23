"""Audit chain and append-only enforcement.

Revision ID: 0007_audit_ledger
Revises: 0006_governance_controls
"""

import sqlalchemy as sa

from alembic import op

revision = "0007_audit_ledger"
down_revision = "0006_governance_controls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_heads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False),
    )
    op.create_table(
        "audit_entries",
        sa.Column("sequence", sa.BigInteger(), primary_key=True),
        sa.Column("previous_hash", sa.String(64), nullable=False),
        sa.Column("entry_hash", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("actor_id", sa.String(36)),
        sa.Column("subject_id", sa.String(36)),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute(
        "INSERT INTO audit_heads (id, sequence, hash) "
        "VALUES (1, 0, repeat('0', 64))"
    )
    op.execute("""
        CREATE FUNCTION reject_audit_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit entries are append-only';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER audit_entries_immutable
        BEFORE UPDATE OR DELETE ON audit_entries
        FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER audit_entries_immutable ON audit_entries")
    op.execute("DROP FUNCTION reject_audit_mutation()")
    op.drop_table("audit_entries")
    op.drop_table("audit_heads")
