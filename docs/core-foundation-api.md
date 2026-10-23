# Core Foundation HTTP contract (Subsystem B handoff)

This service records authorization decisions and single-use permits. It does **not**
execute payments, outreach, deployment or other external effects. Subsystem B
must invoke the gateway and verify exact parameters before any fake or real
adapter is added; real adapters are out of scope for this foundation.

## Setup and verification

Use Python 3.12 and a **disposable PostgreSQL 16** database, never the
user's Windows or production database. Install with `pip install -e ".[dev]"`,
set `DATABASE_URL=postgresql+psycopg://...`, set
`AUTOPILOT_BOOTSTRAP_SECRET` securely, then run:

```sh
alembic upgrade head
pytest -q -ra
ruff check .
```

Owner bootstrap is deliberately a service/CLI operation
(`autopilot.identity.service.bootstrap_owner(session, secret)`); do not
expose the bootstrap secret over the HTTP API. Store returned credentials
securely: only credential hashes are persisted. Requests use
`Authorization: Bearer <credential>`. Missing/invalid credentials return
401 `{"detail":"UNAUTHENTICATED"}`.

## HTTP routes

All routes below require authentication except `GET /health`. UUIDs are
strings; timestamps are timezone-aware ISO 8601; budget values are integer
minor currency units. Successful create endpoints return 201.

| Method and path | Request fields | Response fields |
| --- | --- | --- |
| GET /health | none | `status` |
| POST /agents | `kind` (executive/specialist), owner only | `id,organization_id,kind,level,credential` |
| POST /ventures | `name`, owner only | `id,name,stage,status` |
| GET /ventures/{id} | none, scoped | venture fields |
| POST /ventures/{id}/tasks | `title,acceptance_criteria`, scoped write | `id,venture_id,title,acceptance_criteria,state,version` |
| GET /ventures/{id}/tasks/{task_id} | none, scoped | task fields |
| POST /ventures/{id}/tasks/{task_id}/transition | `expected_version,target,approved_action` | task fields |
| POST /governance/grants | `actor_id,venture_id,action,resource,budget_ceiling_minor,expires_at`, owner only | `id,active` |
| POST /governance/grants/{id}/revoke | none, owner only | `active:false` |
| PUT /governance/global-budget | `ceiling_minor`, owner only | `ceiling_minor` |
| PUT /governance/ventures/{id}/budget | `ceiling_minor`, owner only | `ceiling_minor` |
| PUT /governance/global-stop | `enabled`, owner only | `enabled` |
| PUT /governance/ventures/{id}/freeze | `enabled`, owner only | `enabled` |
| POST /governance/reservations | `venture_id,amount_minor,idempotency_key` | `id,amount_minor` |
| POST /action-requests | `venture_id,action,target,parameters,idempotency_key` | `id,risk,status,parameters_hash` |
| POST /action-requests/{id}/decision | `decision` approved/denied, optional `expires_at`, owner only | `id,request_id,decision,expires_at` |
| POST /action-requests/{id}/permit | none, owner or request actor | `id,request_id,expires_at` |
| POST /permits/{id}/consume | `parameters` exact JSON object, owner or request actor | `consumed:true` |
| GET /audit?offset=0&limit=50 | owner only; limit 1–100 | array of sequence, event_type, actor_id, subject_id, redacted metadata, occurred_at, entry_hash |
| GET /audit/verify | owner only | `valid,first_invalid_sequence` |

Error envelopes use FastAPI `{"detail":"CODE"}`: 401
`UNAUTHENTICATED`, 403 `FORBIDDEN`, `APPROVAL_DENIED`,
`CONTROL_DENIED`, or `PERMIT_DENIED`; 404 `NOT_FOUND` for inaccessible
venture/task/permit resources; 409 `CONFLICT` for stale task version or
idempotency-key payload mismatch; 422 `INVALID_ACTION` for prohibited or
unknown actions, or FastAPI field-validation detail arrays. No endpoint
executes an external action.

## Subsystem B required sequence

1. Owner bootstraps, creates executive, venture and finite global/venture
   budgets; grants are scoped by actor, venture, action, resource, ceiling
   and expiry.
2. Executive creates a scoped action request with a stable idempotency key
   and canonical JSON parameters. Reusing the same key and body returns the
   same request; changed body conflicts.
3. High-risk requests require an exact Owner decision before issuing a
   permit. Permits are bound to request and parameters hashes, expire and
   can be consumed once only.
4. Global Stop and venture freeze are checked at issuance **and**
   consumption; Subsystem B must not interpret a previously issued permit
   as permission to bypass later stop/freeze.
5. Audit entries and business mutations commit atomically. PostgreSQL
   triggers reject audit-entry UPDATE/DELETE. Owner can verify the hash
   chain; verification is tamper-evident, not an external notarization.

**Limitations:** No external executor, live provider integration, automated
budget settlement, or cross-service distributed transaction is included.
A consumer must not treat a recorded permit as proof an external action ran.
