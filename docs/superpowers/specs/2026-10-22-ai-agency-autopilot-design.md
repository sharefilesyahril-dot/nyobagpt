# AI Agency Autopilot — Architecture Design Specification v1.0

**Status:** Approved by Human Owner  
**Date:** 2026-10-22  
**Method:** Superpowers Architectural Brainstorming

## 1. Purpose and agreed decisions
Build a highly autonomous AI Venture Studio that discovers opportunities, validates ventures, builds digital MVPs and manages an adaptive portfolio while the Human Owner retains authority over sensitive actions. Agreed decisions: Hybrid Hierarchical + Dynamic Teams; Adaptive Venture Portfolio; Dynamic Capacity; Hybrid Agent Runtime; Event-Driven + Shared Workspace; Hierarchical Memory; Policy-Driven Autonomous Governance. This specification is a proposed system, not a claim that an application is running.

## 2. Scope and success criteria
The first deliverable is a single-owner, single-organization MVP that demonstrates one complete venture lifecycle from idea to reviewed MVP proposal. It must support multiple venture records with dynamic admission based on configured resource limits, but it does not automatically incorporate businesses, spend money, contact customers, or deploy publicly. Success means: a task can be delegated, resumed after worker failure, reviewed, traced to source artifacts and policy decisions, and stopped by the owner without unauthorized external side effects. Portfolio recommendations must expose evidence and uncertainty, not assert commercial success.

Out of scope for MVP: autonomous payments, contract execution, unsupervised public launch, self-modifying permissions, unrestricted agent spawning, multi-tenant SaaS, guaranteed revenue, and fully autonomous legal or financial decisions.

## 3. Organizational model
Human Owner: defines objectives, budgets, policies, and approvals. AI CEO: plans strategy, proposes venture priorities, delegates and escalates. Executives: COO (operations), CTO (engineering), CMO (growth), CFO (budget analysis, not payment authority), CPO (product), Research Director (evidence), Quality Director (independent review). Specialist workers are ephemeral per task. Executive identity, configuration and memory persist, but compute is event/schedule activated. Quality reviewer cannot approve its own work; policy enforcement is independent of agent prompts.

## 4. Logical architecture and boundaries
- Human Dashboard: venture views, task states, spend and usage estimates, approval inbox, freeze and stop controls.
- AI CEO and Executive Layer: propose tasks and strategies; cannot invoke external side effects directly.
- Portfolio Engine: evaluates ventures and proposes accelerate, continue, pivot, pause, or stop; stop means no new work, not deletion or service shutdown.
- Portfolio Capacity Controller (PCC): admission and scheduling using remaining owner-defined budget, compute quotas, workload, time and risk. It cannot increase limits.
- Event Bus + durable Task Queue: routes commands and events; worker leasing, retry and dead-letter handling.
- Dynamic Specialist Runtime: sandboxed workers with scoped capabilities, context, execution limits and checkpointing.
- Shared Workspace: authoritative venture/task/artifact/decision state.
- Hierarchical Memory: company, venture, agent and temporary working context, with explicit promotion and access checks.
- Governance Layer and Tool Gateway: policy enforcement on every external side effect, approvals, credentials and audit.

## 5. Venture lifecycle and scoring
Stages: Discovery -> Evidence Collection -> Validation -> Selection -> MVP Proposal/Build -> Quality Review -> Owner-approved Launch -> Growth Review. Each transition requires a stage-specific evidence artifact and review status. Initial score hypothesis: market opportunity 25%, customer validation 25%, revenue potential 20%, technical feasibility 15%, risk/resource efficiency 15%. Every criterion is scored 0–5 with evidence, confidence and missing-data flags. Missing evidence is not scored as proof of success; recommendations include uncertainty. These weights are defaults subject to later empirical calibration. Portfolio decisions are recommendations constrained by governance; launch, payment, public outreach and production changes require owner approval.

## 6. Event and task contracts
Events are immutable records with event_id, schema_version, event_type, occurred_at, organization_id, venture_id, task_id, correlation_id, causation_id, actor_id, payload_ref. Commands contain task_id, requested_action, input_refs, acceptance_criteria, scoped_permissions, budget_limit, deadline, idempotency_key. Event payloads carry references rather than raw secrets or full conversations. Store state changes and outbound events atomically using a transactional outbox. Consumers deduplicate by event_id/idempotency_key. At-least-once delivery is assumed, never exactly-once. Worker leases expire; bounded retries use backoff and dead-letter queues. External effects use explicit idempotency and reconciliation rather than blind retries.

Example: venture.created -> research.requested -> research.completed -> validation.requested -> quality.reviewed -> venture.scored -> decision.proposed -> policy.checked -> (approved/denied/pending) -> authorized action. A failed review returns to rework with a capped iteration count.

## 7. Memory and data ownership
Company Memory holds approved policies, strategy and vetted reusable learning. Venture Memory isolates research, artifacts and decisions per venture. Agent Memory stores role, scoped preferences and task history; Working Memory is short-lived and expires. Promotion from venture to company memory requires source provenance, quality review and access-policy checks. The workspace database is the source of truth; retrieval indexes are derived and rebuildable. Use venture-scoped authorization for reads, writes and search. Retention and deletion are policy-controlled, and audit records are access-restricted.

## 8. Governance and approval
Four permission levels: L1 Observe; L2 Analyze; L3 Execute within granted scope; L4 Govern reserved to Human Owner. Permissions are scoped by venture, action, resource, duration and budget. Risk classes: low (internal drafts/research) may auto-run; medium (internal changes within prior policy) require automated policy checks; high (payments, public launch/outreach, contracts, access changes, production deployment or customer-impacting actions) require explicit owner approval; prohibited (self-escalation, disabling audit, bypassing gateway, unauthorized credentials) are blocked. No-response is never approval. Approval tokens bind exact action, actor, target, expiry and parameters; changed parameters require new approval. The gateway rechecks policy at execution time. Prompt injection and retrieved content are untrusted and cannot alter policy.

Controls: global stop prevents new work and cancels cancellable jobs; venture freeze scopes the same to one venture; budget circuit breaker denies excess requests; append-only tamper-evident audit captures who requested, checked, approved and executed each action. Already-completed external actions may need compensation, not fictitious rollback. Secrets stay in a vault, never in event payloads or agent memory.

## 9. Dynamic capacity
Admission is based on configured owner ceilings: remaining monetary budget, token/compute quotas, concurrent worker slots, task deadlines and risk exposure. No fixed venture count is required, but finite hard ceilings and per-venture quotas are mandatory. PCC prioritizes approved tasks, reserves resources atomically, pauses lower-priority work when saturated and reports utilization. It cannot create new funding, permissions or unbounded workers. Cost estimates and actual usage are tracked separately.

## 10. Error handling and observability
Every task has states queued, leased, running, awaiting_review, awaiting_approval, completed, failed, paused or cancelled. Checkpoints are durable; workers resume from the last safe point. Retry only transient errors; validation failures go to rework; policy denials stop execution; exhausted retries go to a dead-letter queue with human-visible diagnosis. Record traces across correlation IDs, latency, token usage, cost, queue depth, error rates, approval delays and quality outcomes. Never claim task completion without persisted artifacts and verification evidence.

## 11. Suggested MVP technology (not yet approved as implementation)
Modular monolith API and workers; Python/FastAPI for orchestration; PostgreSQL for transactional workspace, outbox and policy/audit metadata; Redis-backed task queue as a replaceable adapter; object storage for artifacts; retrieval index derived from authorized documents; provider-agnostic LLM adapter; simple owner dashboard. The architecture contracts, not a particular framework, are binding. Evaluate hosting, cost and compliance before selecting production providers. Agency Agents role prompts can be adapted as templates, not installed as a native ChatGPT runtime.

## 12. Delivery decomposition
A. Core governance, identity, venture/task records and audit (independently testable foundation).
B. Event bus, durable task execution, worker leases, checkpoint and retry.
C. Hybrid agent runtime, scoped tools, hierarchical memory and review workflow.
D. Portfolio scoring, capacity controller and venture lifecycle.
E. Owner dashboard, approval inbox, stop/freeze, end-to-end venture demonstration.
Each subsystem requires its own implementation plan and acceptance tests; build sequentially against stable interfaces. No implementation begins before written-spec approval and review of the implementation plan.

## 13. Verification strategy
TDD for domain policies, transitions, scoring, scheduling and event contracts. Contract tests for executive/specialist interfaces; integration tests for outbox, deduplication, workspace permissions and worker recovery; end-to-end simulated venture from discovery to approval. Security tests include prompt injection, cross-venture memory leakage, self-escalation, approval replay, changed approval parameters, credential exposure and kill-switch races. Reliability tests include duplicate/out-of-order events, worker crashes, budget exhaustion, partial tool failures, timeout and retries. Quality evaluation checks source attribution, unsupported claims, reviewer independence and decision explainability. External-effect tests use mocks/sandboxes; no live payment or publication during MVP testing.

## 14. Acceptance criteria
1. An owner can configure hard ceilings and scoped permissions, and AI CEO cannot override them.
2. A simulated venture traverses discovery, validation, scoring and reviewed MVP proposal with linked evidence.
3. Every delegated task has traceable ownership, acceptance criteria, state and artifacts.
4. Duplicate events do not create duplicate state transitions or external actions.
5. Restarting a worker resumes safely or escalates without silently losing work.
6. Venture-scoped memory cannot be read by another venture without explicit policy grant.
7. High-risk actions remain pending until exact, valid owner approval; expired or changed requests fail closed.
8. Global stop and venture freeze block new work within their scope, with cancellation limitations reported.
9. The capacity controller never exceeds configured resource ceilings and exposes why work is deferred.
10. Audit and quality evidence are available for every proposed portfolio decision.

## 15. Assumptions for review
Single Human Owner and one organization in MVP; actual financial ceiling and deployment location are owner-configured at setup, not hardcoded. Default deny for unspecified external permissions. No autonomous production launch or spending. The proposed technology stack and numerical scoring weights are recommendations, not previously approved decisions. Repository: `sharefilesyahril-dot/nyobagpt`.