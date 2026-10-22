# AI Agency Autopilot — Core Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a standalone, tested single-owner foundation for identities, scoped policy enforcement, venture/task records, approval decisions, and tamper-evident audit evidence, without invoking live external tools.

**Architecture:** A modular-monolith FastAPI application backed by PostgreSQL. Domain services enforce authorization and state transitions in database transactions; an independent policy service and action gateway fail closed. An append-only audit ledger records decisions, with a hash chain to detect modification (not a substitute for externally anchored logs).

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL 16, psycopg 3, pytest, httpx, Ruff. Versions are proposed implementation selections, not mandates of the approved design. Docker Compose is optional for local PostgreSQL.

**Spec:** `docs/superpowers/specs/2026-10-22-ai-agency-autopilot-design.md` (approved v1.0).

## Global Constraints

- One organization and one Human Owner in MVP; no multi-tenant product.
- AI CEO cannot increase budgets, grant itself permissions, change policy, or bypass gateway.
- L1 Observe, L2 Analyze, L3 scoped Execute, L4 Govern reserved to Human Owner.
- Default-deny unspecified external permissions; high-risk action requires exact, unexpired owner approval; silence is not approval.
- Permissions scoped by venture, action, resource, duration, and budget; reads/writes are venture-isolated.
- No live payments, public launch, customer outreach, production deployment, or autonomous contract execution in MVP.
- Audit is append-only and access-restricted; secrets never enter event payloads or agent memory.
- Global stop and venture freeze block new work; already-completed external effects are not falsely rolled back.
- TDD for domain policy and transitions; run integration tests against real PostgreSQL, not SQLite substitutes.
- This plan covers only subsystem A. Event delivery, agent runtime, hierarchical retrieval, portfolio scoring, capacity scheduling, and dashboard are later plans.

## File Map

- `pyproject.toml`: runtime and test dependencies, lint/test configuration.
- `src/autopilot/app.py`: API composition and exception mapping.
- `src/autopilot/db.py`: session and transaction setup.
- `src/autopilot/identity/models.py`, `service.py`, `routes.py`: owner, agents, immutable actor identity, authentication and role assignment.
- `src/autopilot/governance/models.py`, `policy.py`, `approvals.py`, `gateway.py`, `routes.py`: scoped grants, risk classification, approvals, stop/freeze and execution authorization.
- `src/autopilot/ventures/models.py`, `service.py`, `routes.py`: venture and task records and legal transitions.
- `src/autopilot/audit/models.py`, `ledger.py`, `routes.py`: append-only ledger, verification, restricted retrieval.
- `src/autopilot/contracts.py`: shared enums, typed request/response contracts, error codes.
- `alembic/versions/0001_core_foundation.py`: constraints, indexes, foreign keys, unique idempotency keys and audit write restrictions.
- `tests/conftest.py`: PostgreSQL transaction-isolated fixtures, fixed clock and owner/agent factories.
- `tests/{identity,governance,ventures,audit,api}/test_*.py`: domain, integration and HTTP tests.

## Stable Interfaces and Data Contracts

Use UUID identifiers and UTC-aware timestamps. Persist organization_id on all records and venture_id on venture-scoped records. Public API returns stable errors: `UNAUTHENTICATED` (401), `FORBIDDEN` (403), `NOT_FOUND` (404, including inaccessible venture), `CONFLICT` (409), `VALIDATION_ERROR` (422), `POLICY_DENIED` (403), `APPROVAL_REQUIRED` (409), `STOP_ACTIVE` (409). Do not expose sensitive policy context in cross-venture 404 responses.

- `Actor(id, organization_id, kind: owner|executive|specialist, active)`; only owner may have L4.
- `Grant(id, actor_id, organization_id, venture_id|null, action, resource_pattern, level, expires_at, max_budget_minor|null)`; absence is denial.
- `Venture(id, organization_id, name, stage, status, version, created_by)`; `Task(id, venture_id, owner_actor_id, title, acceptance_criteria, status, artifact_refs, version)`.
- `ActionRequest(id, actor_id, venture_id|null, action, target, canonical_parameters, parameters_sha256, risk, requested_at, expires_at, idempotency_key)`.
- `Approval(id, action_request_id, owner_id, decision, parameters_sha256, expires_at, consumed_at|null)`; one decision per request; approval is single-use for an effect.
- `AuditEntry(id, sequence, occurred_at, actor_id, organization_id, venture_id|null, action, subject_id, outcome, metadata_redacted, previous_hash, entry_hash)`.
- `authorize(actor_id: UUID, venture_id: UUID|None, action: str, resource: str, budget_minor: int, now: datetime) -> PolicyDecision`.
- `request_action(actor_id: UUID, action: str, target: str, parameters: dict, venture_id: UUID|None, idempotency_key: str, now: datetime) -> ActionRequest`.
- `decide_approval(owner_id: UUID, request_id: UUID, decision: Literal['approve','deny'], now: datetime) -> Approval`.
- `authorize_execution(request_id: UUID, now: datetime) -> ExecutionPermit` validates actor, policy, stop/freeze, parameter digest and approval in one transaction; no live tool is called in subsystem A.
- `create_venture(actor_id: UUID, name: str) -> Venture`; `create_task(actor_id: UUID, venture_id: UUID, title: str, acceptance_criteria: list[str]) -> Task`; `transition_task(actor_id: UUID, task_id: UUID, expected_version: int, next_status: TaskStatus) -> Task`.
- `append_audit(session, event: AuditEvent) -> AuditEntry`; `verify_audit_chain(session, start_sequence: int, end_sequence: int) -> VerificationResult`.

## Review Focus

1. Cross-venture UUID probing must return 404 without disclosing whether the record exists (Task 3).
2. Concurrent task updates with the same version must allow exactly one transition (Task 4).
3. Approval replay, expiry, and changed parameters must fail closed (Task 6).
4. Concurrent global stop versus permit issuance must serialize through a governance lock; after stop commits, no new permit may be issued (Task 7).
5. Failed business transactions must not leave success audit entries, and a deliberately altered audit row must fail verification (Task 8).

---

### Task 1: Runnable service and transactional database baseline

**Files:** Create `pyproject.toml`, `src/autopilot/{__init__,app,db,contracts}.py`, `alembic.ini`, `alembic/env.py`, `tests/conftest.py`, `tests/api/test_health.py`, `README.md`.

**Interfaces:** Produces `create_app() -> FastAPI`, `get_session() -> Iterator[Session]`, `GET /health` returning `{"status":"ok"}`; config from environment; database fixture with rollback isolation.

- [ ] Write failing HTTP test `test_health_returns_ok` asserting status 200 and exact JSON, and database integration test asserting a transaction rollback leaves no persisted row.
- [ ] Run `pytest tests/api/test_health.py -v`; expect failure because app/fixture is absent.
- [ ] Implement minimum app, PostgreSQL connection/session lifecycle and test fixture; document `DATABASE_URL`, migration and local test commands.
- [ ] Run `pytest tests/api/test_health.py -v` and `ruff check .`; expect pass.
- [ ] Commit: `git add pyproject.toml src tests alembic.ini alembic README.md && git commit -m "chore: establish core service and test database"`.

### Task 2: Actor identity and owner-only administration

**Files:** Create `src/autopilot/identity/{models,service,routes}.py`, `tests/identity/test_identity.py`, `tests/api/test_identity.py`; extend `alembic/versions/0001_core_foundation.py`.

**Interfaces:** `get_actor(actor_id: UUID) -> Actor`; `create_agent(owner_id: UUID, kind: Literal['executive','specialist']) -> Actor`; authenticated actor context from validated credentials (no trusted caller-supplied actor header); `POST /agents` owner-only. Bootstrap owner through one-time administrative CLI/environment secret, never unauthenticated HTTP.

- [ ] Write failing tests: one owner bootstrap only, non-owner cannot create actors or obtain L4, invalid/missing credentials yield 401, deactivated actors fail authentication.
- [ ] Run `pytest tests/identity tests/api/test_identity.py -v`; expect failures for missing models/service/routes.
- [ ] Implement actors, secure bootstrap, auth dependency and owner-only creation; persist constraints and migration.
- [ ] Run focused tests and `ruff check .`; expect pass.
- [ ] Commit: `git add src/autopilot/identity tests/identity tests/api/test_identity.py alembic && git commit -m "feat: add owner and agent identity"`.

### Task 3: Scoped grants and policy evaluation

**Files:** Create `src/autopilot/governance/{models,policy}.py`, `tests/governance/test_policy.py`; extend migration.

**Interfaces:** `authorize(actor_id, venture_id, action, resource, budget_minor, now) -> PolicyDecision(allowed: bool, reason_code: str, grant_id: UUID|None)`; `set_grant(owner_id: UUID, grant: GrantInput) -> Grant`; `revoke_grant(owner_id: UUID, grant_id: UUID) -> None`. Require active actor, same organization, explicit matching scope, non-expired grant and budget ceiling; L4 owner only.

- [ ] Write failing tests for default deny, owner-only grant mutation, cross-venture grant isolation, expired grant, budget overrun, self-escalation and inactive actor. Cross-venture probing must not disclose existence through API errors.
- [ ] Run `pytest tests/governance/test_policy.py -v`; expect fail.
- [ ] Implement explicit scoped grants and deterministic policy evaluation, DB constraints and indexes.
- [ ] Run focused tests; expect pass.
- [ ] Commit: `git add src/autopilot/governance tests/governance alembic && git commit -m "feat: enforce scoped grants"`.

### Task 4: Venture and task registry with optimistic transitions

**Files:** Create `src/autopilot/ventures/{models,service,routes}.py`, `tests/ventures/test_registry.py`, `tests/api/test_ventures.py`; extend migration.

**Interfaces:** `create_venture`, `create_task`, `transition_task` as above. MVP venture stages: `discovery, evidence_collection, validation, selection, mvp_proposal, quality_review, launch_pending, growth_review`; status `active, paused, stopped`. Task states: `queued, leased, running, awaiting_review, awaiting_approval, completed, failed, paused, cancelled`. In subsystem A expose record/transition operations but do not start workers. Allowed task transitions: queued→leased|paused|cancelled; leased→running|queued|cancelled; running→awaiting_review|failed|paused|cancelled; awaiting_review→completed|running|failed; awaiting_approval→queued|cancelled; paused→queued|cancelled; failed→queued|cancelled; terminal completed/cancelled have no outgoing transitions. `awaiting_approval` is entered from queued when a task requires an approved action.

- [ ] Write failing tests for scoped create/read, mandatory nonempty acceptance criteria, illegal transition 409, version mismatch 409, cross-venture access 404, and two concurrent updates of one version producing one success and one conflict.
- [ ] Run `pytest tests/ventures tests/api/test_ventures.py -v`; expect fail.
- [ ] Implement venture/task models, access checks, compare-and-swap version update and HTTP routes; add foreign keys and organization/venture indexes.
- [ ] Run focused tests; expect pass.
- [ ] Commit: `git add src/autopilot/ventures tests/ventures tests/api/test_ventures.py alembic && git commit -m "feat: record ventures and tasks with safe transitions"`.

### Task 5: Action requests and risk classification

**Files:** Create `src/autopilot/governance/{approvals,routes}.py`, `tests/governance/test_requests.py`; extend migration.

**Interfaces:** `request_action(...) -> ActionRequest`; `classify_risk(action: str) -> Literal['low','medium','high','prohibited']`. High: payments, public outreach/launch, contracts, access changes, production deploy, customer-impacting changes. Prohibited: self-escalation, audit disabling, gateway bypass, unauthorized credentials. Unknown external actions default to high/deny pending explicit classification; prohibit unknown effects until policy is configured. Canonicalize JSON deterministically and hash parameters; unique `(actor_id, idempotency_key)`; reject same key with different request body.

- [ ] Write failing tests for risk table, unknown action fail-closed, secret-field rejection, duplicate same-key same-body returns same request, same-key changed body conflicts, and canonical JSON order equivalence.
- [ ] Run `pytest tests/governance/test_requests.py -v`; expect fail.
- [ ] Implement request persistence, classification, canonical hashing and idempotency uniqueness.
- [ ] Run focused tests; expect pass.
- [ ] Commit: `git add src/autopilot/governance tests/governance alembic && git commit -m "feat: register governed action requests"`.

### Task 6: Exact owner approvals and one-time permits

**Files:** Modify `src/autopilot/governance/{approvals,routes}.py`; create `src/autopilot/governance/gateway.py`, `tests/governance/test_approvals.py`; extend migration.

**Interfaces:** `decide_approval(owner_id, request_id, decision, now) -> Approval`; `authorize_execution(request_id, now) -> ExecutionPermit(id, request_id, parameters_sha256, expires_at)`; `consume_permit(permit_id: UUID, parameters: dict, now: datetime) -> None` atomically marks used. A permit is a recorded authorization for later gateway integration, not a live effect. Only the owner may approve; expiry is explicit; approval binds actor, target, action and canonical parameters digest.

- [ ] Write failing tests for owner-only decision, denial, no-response pending, expired approval, replay of consumed permit, changed parameters, revoked grant after approval, and concurrent consumption yielding one success.
- [ ] Run `pytest tests/governance/test_approvals.py -v`; expect fail.
- [ ] Implement exact approval, transactional permit issuance and consumption; re-evaluate current policy at issuance and consumption.
- [ ] Run focused tests; expect pass.
- [ ] Commit: `git add src/autopilot/governance tests/governance alembic && git commit -m "feat: enforce exact single-use owner approvals"`.

### Task 7: Global stop, venture freeze and budget gates

**Files:** Modify `src/autopilot/governance/{models,policy,gateway,routes}.py`, `tests/governance/test_controls.py`; extend migration.

**Interfaces:** `set_global_stop(owner_id: UUID, enabled: bool) -> None`; `set_venture_freeze(owner_id: UUID, venture_id: UUID, enabled: bool) -> None`; `reserve_budget(actor_id: UUID, venture_id: UUID, amount_minor: int, idempotency_key: str) -> BudgetReservation`. Owner configures finite global/per-venture ceilings; reservations use row locks and never permit negative available balance. Global stop and permit issuance lock the same governance row before decision/commit; freezing venture similarly locks its control row.

- [ ] Write failing tests for agent cannot change limits, over-budget rejection, same-key reservation deduplication, global stop blocks permits, venture freeze only affects scoped venture, and stop/permit concurrency: after stop commits no new permit succeeds.
- [ ] Run `pytest tests/governance/test_controls.py -v`; expect fail.
- [ ] Implement controls, transaction ordering, budget reservations and routes; add database constraints.
- [ ] Run focused tests; expect pass.
- [ ] Commit: `git add src/autopilot/governance tests/governance alembic && git commit -m "feat: enforce stop freeze and finite budgets"`.

### Task 8: Append-only audit and transaction-linked evidence

**Files:** Create `src/autopilot/audit/{models,ledger,routes}.py`, `tests/audit/test_ledger.py`, `tests/api/test_audit.py`; modify service transaction boundaries and migration.

**Interfaces:** `append_audit(session, event: AuditEvent) -> AuditEntry`; `verify_audit_chain(session, start_sequence, end_sequence) -> VerificationResult(valid: bool, first_invalid_sequence: int|None)`; `GET /audit` owner-only, paginated and redacted. Use canonical serialization, SHA-256 chain over sequence, previous_hash and entry fields; serialize writers using a locked chain-head row. Restrict UPDATE/DELETE for application DB role. Commit state mutation and its audit entry in the same transaction. A chain detects changes but stronger tamper resistance requires external anchoring in a later subsystem.

- [ ] Write failing tests for sequential linkage, owner-only read, no secrets in metadata, direct mutation rejected under app DB role, altered row detected under privileged test role, rollback leaves neither business state nor success audit, and concurrent append has unique ordered sequence.
- [ ] Run `pytest tests/audit tests/api/test_audit.py -v`; expect fail.
- [ ] Implement ledger, DB role restrictions, redaction and transaction-linked audit calls for identity, grants, venture/task changes, approvals, permits and stop/freeze.
- [ ] Run focused tests; expect pass.
- [ ] Commit: `git add src/autopilot/audit src/autopilot/identity src/autopilot/governance src/autopilot/ventures tests/audit tests/api/test_audit.py alembic && git commit -m "feat: record transaction-linked append-only audit"`.

### Task 9: API integration, security regression and handoff

**Files:** Create `tests/api/test_foundation_e2e.py`, `docs/core-foundation-api.md`; modify `README.md`, `src/autopilot/app.py`.

**Interfaces:** HTTP workflow: authenticate owner → create scoped executive → set grant/budget → create venture/task → request action → owner approval → issue/consume permit → verify audit; stop/freeze must block further permits. Document response schemas and error codes for subsystem B consumers.

- [ ] Write failing end-to-end test for full workflow and negative paths: anonymous actor, cross-venture access, changed approval body, unknown action, global stop, duplicate idempotency key and audit verification.
- [ ] Run `pytest tests/api/test_foundation_e2e.py -v`; expect fail until routes and wiring are complete.
- [ ] Wire routers, standardize exception responses, document API contracts and migration setup; use fake actions only, no live external tools.
- [ ] Run `alembic upgrade head && pytest -q && ruff check .` on a clean PostgreSQL test DB; expect all tests pass, no lint errors. Verify downgrade/upgrade on a disposable database.
- [ ] Commit: `git add src tests README.md docs/core-foundation-api.md && git commit -m "test: verify core foundation end to end"`.

## Completion Gate and Handoff

- No task is marked done without a witnessed red→green test cycle and commit; run all verification commands at completion.
- Review permissions, transactional consistency, data isolation, concurrent approval/stop behavior and audit integrity independently before merging.
- Deliver migration instructions, API contract, test evidence, limitations, and exact interfaces required by subsystem B.
- Never claim the code or tests are complete merely because this plan exists. Execution begins only after human review and choice of method.