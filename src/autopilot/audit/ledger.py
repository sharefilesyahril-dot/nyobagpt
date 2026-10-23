import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from autopilot.audit.models import AuditEntry, AuditHead

GENESIS = "0" * 64
REDACTED_KEYS = frozenset((
    "password", "secret", "token", "api_key", "credential",
    "authorization", "private_key", "access_token", "refresh_token",
))


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    actor_id: str | None = None
    subject_id: str | None = None
    metadata: dict | None = None
    occurred_at: datetime | None = None


@dataclass(frozen=True)
class VerificationResult:
    valid: bool
    first_invalid_sequence: int | None = None


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    )


def redact(value):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key.lower() in REDACTED_KEYS
            else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def digest(entry):
    payload = {
        "sequence": entry.sequence,
        "previous_hash": entry.previous_hash,
        "event_type": entry.event_type,
        "actor_id": entry.actor_id,
        "subject_id": entry.subject_id,
        "metadata": json.loads(entry.metadata_json),
        "occurred_at": entry.occurred_at.isoformat(),
    }
    return hashlib.sha256(canonical(payload).encode()).hexdigest()


def append_audit(session: Session, event: AuditEvent) -> AuditEntry:
    timestamp = event.occurred_at or datetime.now(UTC)
    if timestamp.tzinfo is None or not event.event_type:
        raise ValueError("Invalid audit event")
    head = session.scalar(
        select(AuditHead).where(AuditHead.id == 1).with_for_update()
    )
    if head is None:
        raise ValueError("Audit chain not initialized")
    entry = AuditEntry(
        sequence=head.sequence + 1,
        previous_hash=head.hash,
        event_type=event.event_type,
        actor_id=event.actor_id,
        subject_id=event.subject_id,
        metadata_json=canonical(redact(event.metadata or {})),
        occurred_at=timestamp,
    )
    entry.entry_hash = digest(entry)
    session.add(entry)
    head.sequence = entry.sequence
    head.hash = entry.entry_hash
    session.flush()
    return entry


def verify_audit_chain(
    session: Session, start_sequence: int = 1, end_sequence: int | None = None,
) -> VerificationResult:
    if start_sequence < 1:
        raise ValueError("Invalid start")
    prior = GENESIS
    if start_sequence > 1:
        previous = session.get(AuditEntry, start_sequence - 1)
        if previous is None or previous.entry_hash != digest(previous):
            return VerificationResult(False, start_sequence - 1)
        prior = previous.entry_hash
    query = select(AuditEntry).where(AuditEntry.sequence >= start_sequence)
    if end_sequence is not None:
        query = query.where(AuditEntry.sequence <= end_sequence)
    expected = start_sequence
    for entry in session.scalars(query.order_by(AuditEntry.sequence)):
        if (
            entry.sequence != expected or entry.previous_hash != prior
            or entry.entry_hash != digest(entry)
        ):
            return VerificationResult(False, expected)
        prior = entry.entry_hash
        expected += 1
    head = session.get(AuditHead, 1)
    if end_sequence is None and head is not None:
        if head.sequence != expected - 1 or head.hash != prior:
            return VerificationResult(False, expected)
    elif end_sequence is not None and expected <= end_sequence:
        return VerificationResult(False, expected)
    return VerificationResult(True)
