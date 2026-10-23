import hashlib
import json
import uuid
from typing import Literal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from autopilot.governance.models import ActionRequest
from autopilot.identity.models import Actor
from autopilot.ventures.service import get_venture

Risk = Literal["low", "medium", "high", "prohibited"]

LOW = {"draft", "research", "internal_draft", "internal_research"}
MEDIUM = {"internal_update", "internal_review"}
HIGH = {
    "payment", "public_outreach", "public_launch", "contract",
    "access_change", "production_deploy", "customer_change",
}
PROHIBITED = {
    "self_escalation", "disable_audit", "gateway_bypass",
    "unauthorized_credentials",
}
SECRET_KEYS = {
    "password", "secret", "token", "api_key", "apikey", "credential",
    "private_key", "authorization", "access_token", "refresh_token",
}


class RequestConflict(Exception):
    pass


class InvalidAction(Exception):
    pass


def classify_risk(action: str) -> Risk:
    if action in PROHIBITED:
        return "prohibited"
    if action in HIGH:
        return "high"
    if action in MEDIUM:
        return "medium"
    if action in LOW:
        return "low"
    return "prohibited"


def _canonical(value: object) -> str:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise InvalidAction("Parameters must be finite JSON values") from exc


def _reject_secrets(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise InvalidAction("Parameter keys must be strings")
            normalized = key.lower().replace("-", "_")
            if normalized in SECRET_KEYS or any(
                normalized.endswith("_" + secret) for secret in SECRET_KEYS
            ):
                raise InvalidAction("Secret fields are not accepted")
            _reject_secrets(child)
    elif isinstance(value, list):
        for child in value:
            _reject_secrets(child)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def request_action(
    session: Session, actor: Actor, venture_id: uuid.UUID, action: str,
    target: str, parameters: dict, idempotency_key: str,
) -> ActionRequest:
    if not actor.active:
        raise InvalidAction("Inactive actor")
    if not action or len(action) > 128 or not target or len(target) > 256:
        raise InvalidAction("Invalid action or target")
    if not idempotency_key or len(idempotency_key) > 128:
        raise InvalidAction("Invalid idempotency key")
    if not isinstance(parameters, dict):
        raise InvalidAction("Parameters must be a JSON object")
    _reject_secrets(parameters)
    canonical = _canonical(parameters)
    risk = classify_risk(action)
    if risk == "prohibited":
        raise InvalidAction("Prohibited or unclassified action")
    parameters_hash = _hash(canonical)
    request_hash = _hash(_canonical({
        "venture_id": str(venture_id), "action": action,
        "target": target, "parameters": parameters,
    }))
    # A repeated key cannot probe another venture or bypass scoped access.
    get_venture(session, actor, venture_id, "write")
    existing = session.scalar(select(ActionRequest).where(
        ActionRequest.actor_id == actor.id,
        ActionRequest.idempotency_key == idempotency_key,
    ))
    if existing is not None:
        if existing.request_hash != request_hash:
            raise RequestConflict("Idempotency key reused for different request")
        return existing
    record = ActionRequest(
        actor_id=actor.id, organization_id=actor.organization_id,
        venture_id=venture_id, action=action, target=target,
        parameters=json.loads(canonical), parameters_hash=parameters_hash,
        request_hash=request_hash, idempotency_key=idempotency_key,
        risk=risk, status="pending_owner" if risk == "high" else "recorded",
    )
    # Nested transaction isolates uniqueness races without poisoning caller session.
    try:
        with session.begin_nested():
            session.add(record)
            session.flush()
    except IntegrityError:
        existing = session.scalar(select(ActionRequest).where(
            ActionRequest.actor_id == actor.id,
            ActionRequest.idempotency_key == idempotency_key,
        ))
        if existing is None or existing.request_hash != request_hash:
            raise RequestConflict("Idempotency key reused for different request") from None
        return existing
    return record
