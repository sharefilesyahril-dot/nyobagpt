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


def test_concurrent_appends_have_unique_order(database_engine):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from sqlalchemy.orm import Session

    ready = Event()

    def writer(number):
        assert ready.wait(timeout=15)
        with Session(database_engine) as session:
            entry = append_audit(session, AuditEvent(
                "test.concurrent", metadata={"writer": number},
            ))
            sequence = entry.sequence
            session.commit()
            return sequence

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(writer, i) for i in range(4)]
        ready.set()
        sequences = [future.result(timeout=30) for future in futures]
    assert len(set(sequences)) == 4
    assert sorted(sequences) == list(range(min(sequences), max(sequences) + 1))
    with Session(database_engine) as session:
        assert verify_audit_chain(session).valid
