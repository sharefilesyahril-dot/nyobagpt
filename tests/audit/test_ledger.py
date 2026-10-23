import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from autopilot.audit.ledger import (
    AuditEvent,
    append_audit,
    verify_audit_chain,
)
from autopilot.audit.models import AuditHead


def test_linkage_redaction_and_rollback(db_session):
    first = append_audit(db_session, AuditEvent(
        "test.first", metadata={"secret": "hidden", "nested": {"token": "hidden"}},
        occurred_at=datetime(2026, 10, 23, tzinfo=UTC),
    ))
    second = append_audit(db_session, AuditEvent("test.second"))
    assert second.sequence == first.sequence + 1
    assert second.previous_hash == first.entry_hash
    assert verify_audit_chain(db_session).valid
    assert "hidden" not in second.metadata_json
    assert "hidden" not in first.metadata_json
    assert json.loads(first.metadata_json)["secret"] == "[REDACTED]"


def test_update_delete_rejected(db_session):
    entry = append_audit(db_session, AuditEvent("test.immutable"))
    with pytest.raises(DBAPIError):
        db_session.execute(
            text("UPDATE audit_entries SET event_type='changed' WHERE sequence=:seq"),
            {"seq": entry.sequence},
        )
    db_session.rollback()


def test_rollback_removes_entry_and_head_change(db_session):
    before = db_session.get(AuditHead, 1).sequence
    nested = db_session.begin_nested()
    append_audit(db_session, AuditEvent("test.rolled_back"))
    nested.rollback()
    db_session.expire_all()
    assert db_session.get(AuditHead, 1).sequence == before
    assert verify_audit_chain(db_session).valid
