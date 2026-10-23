import hashlib
import os
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from autopilot.identity.models import Actor, ActorKind


class IdentityError(Exception):
    pass


class AuthenticationError(IdentityError):
    pass


class PermissionDenied(IdentityError):
    pass


class IdentityConflict(IdentityError):
    pass


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_actor(session: Session, actor_id: uuid.UUID) -> Actor | None:
    return session.get(Actor, actor_id)


def authenticate(session: Session, token: str) -> Actor:
    if not token:
        raise AuthenticationError("Invalid credentials")
    actor = session.scalar(select(Actor).where(Actor.credential_hash == _digest(token)))
    if actor is None or not actor.active:
        raise AuthenticationError("Invalid credentials")
    return actor


def bootstrap_owner(session: Session, supplied_secret: str) -> tuple[Actor, str]:
    expected = os.environ.get("AUTOPILOT_BOOTSTRAP_SECRET", "")
    if not expected or not secrets.compare_digest(supplied_secret, expected):
        raise PermissionDenied("Invalid bootstrap secret")
    # Serialize competing bootstrap attempts against the PostgreSQL transaction lock.
    session.execute(text("SELECT pg_advisory_xact_lock(8675309)"))
    existing_owner = session.scalar(
        select(Actor.id).where(Actor.kind == ActorKind.owner)
    )
    if existing_owner is not None:
        raise IdentityConflict("Owner already bootstrapped")
    token = secrets.token_urlsafe(32)
    actor = Actor(
        organization_id=uuid.uuid4(),
        kind=ActorKind.owner,
        level=4,
        credential_hash=_digest(token),
        created_at=datetime.now(UTC),
    )
    session.add(actor)
    session.flush()
    return actor, token


def create_agent(session: Session, owner: Actor, kind: ActorKind) -> tuple[Actor, str]:
    if not owner.active or owner.kind != ActorKind.owner or owner.level != 4:
        raise PermissionDenied("Only the owner can create agents")
    if kind not in (ActorKind.executive, ActorKind.specialist):
        raise PermissionDenied("Cannot create another owner")
    token = secrets.token_urlsafe(32)
    actor = Actor(
        organization_id=owner.organization_id,
        kind=kind,
        level=2 if kind == ActorKind.executive else 1,
        credential_hash=_digest(token),
        created_at=datetime.now(UTC),
    )
    session.add(actor)
    session.flush()
    return actor, token
