import uuid

import pytest

from autopilot.governance.approvals import (
    InvalidAction,
    RequestConflict,
    classify_risk,
    request_action,
)
from autopilot.identity.service import bootstrap_owner
from autopilot.ventures.service import create_venture


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        ("draft", "low"), ("research", "low"),
        ("internal_update", "medium"), ("payment", "high"),
        ("public_launch", "high"), ("contract", "high"),
        ("access_change", "high"), ("production_deploy", "high"),
        ("customer_change", "high"), ("self_escalation", "prohibited"),
        ("disable_audit", "prohibited"), ("gateway_bypass", "prohibited"),
        ("unauthorized_credentials", "prohibited"),
        ("unknown_external_effect", "prohibited"),
    ],
)
def test_risk_table(action, expected):
    assert classify_risk(action) == expected


def test_canonical_idempotency_and_conflict(db_session, monkeypatch):
    monkeypatch.setenv("AUTOPILOT_BOOTSTRAP_SECRET", "test-secret")
    owner, _ = bootstrap_owner(db_session, "test-secret")
    venture = create_venture(db_session, owner, "Requests")

    def submit(parameters, key="key-one", action="payment"):
        return request_action(
            db_session, owner, venture.id, action, "target", parameters, key
        )

    first = submit({"b": 2, "a": {"z": 1, "y": 2}})
    assert first.risk == "high"
    assert first.status == "pending_owner"
    same = submit({"a": {"y": 2, "z": 1}, "b": 2})
    assert same.id == first.id
    assert same.parameters_hash == first.parameters_hash
    with pytest.raises(RequestConflict):
        submit({"b": 3})
    with pytest.raises(RequestConflict):
        submit({"b": 2, "a": {"z": 1, "y": 2}}, action="draft")
    with pytest.raises(RequestConflict):
        request_action(
            db_session, owner, uuid.uuid4(), "payment",
            "target", {"b": 2}, "key-one",
        )


def test_fail_closed_and_recursive_secret_rejection(db_session, monkeypatch):
    monkeypatch.setenv("AUTOPILOT_BOOTSTRAP_SECRET", "test-secret")
    owner, _ = bootstrap_owner(db_session, "test-secret")
    venture = create_venture(db_session, owner, "Requests")

    def submit(action, parameters):
        return request_action(
            db_session, owner, venture.id, action, "target", parameters,
            str(uuid.uuid4()),
        )

    for action in ("unknown_effect", "disable_audit", "self_escalation"):
        with pytest.raises(InvalidAction):
            submit(action, {})
    for params in (
        {"password": "hidden"}, {"nested": [{"api_key": "hidden"}]},
        {"Authorization": "hidden"}, {"private-key": "hidden"},
    ):
        with pytest.raises(InvalidAction):
            submit("draft", params)
    with pytest.raises(InvalidAction):
        submit("draft", {"not_json": float("nan")})
    assert submit("draft", {"safe": True}).status == "recorded"
