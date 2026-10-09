# TRACE-X Hackathon V1 MVP — Implementation Plan

**Purpose:** build handoff for the hackathon prototype and its judge-facing walkthrough  
**Product:** TRACE-X — follow the victim's money through one institution's ledger and produce an evidence-backed recommendation document  
**Scope:** one complete backend-led workflow with a sample client/API contract; no full production administration suite  
**Target:** reliably demonstrate the prototype during VISTERA evaluation  
**Primary references:** `D:\AmbiFlow\Requirements4.md`, `D:\Downloads\TRACE-X_HANDOFF.md`, and `TRACE-X_Backend_Implementation_Handoff.md`

> This is the hackathon MVP plan, not the complete bank-deployment plan. “V1 MVP” here means a coherent prototype with real backend behavior and explicit limitations. It must not be described as ready for a bank to use with live customer data.

---

## 1. Goal

Deliver a repeatable end-to-end demonstration that starts from a synthetic fraud complaint, resolves the reported transaction, traces attributed value through a transaction ledger, explains where the trace stops, lets an analyst draft a recommendation, requires a different supervisor to approve it, and exports a verifiable case file.

The prototype should prove TRACE-X’s core claim: it follows the reported victim’s funds through a known ledger and shows the investigator which in-scope accounts have an **upper-bound estimate** of attributed value, with transaction evidence and explicit institutional boundaries.

### 1.1 Stage success criteria

- Judges understand the product and the scope limitation quickly.
- The team can complete the same prepared demo path repeatedly without editing data manually between runs.
- A selected complaint resolves to the correct seed transaction or is refused clearly if it does not.
- A multi-branch trace conserves the seed amount exactly and never spends a sibling branch’s amount twice.
- A click on any displayed graph/account/timeline item retrieves details from the same stored trace result.
- The demo shows the reason and last observed evidence for each trace cutoff.
- A recommendation is drafted by one user and approved by another; self-approval is denied by both service logic and a database constraint.
- Approval creates a document only. The prototype cannot freeze, block, or contact a bank.
- All demo data is labelled synthetic. No unmeasured model, recovery, or performance metric is shown as fact.

### 1.2 MVP definition

The MVP is **complete when the complaint → trace → evidence → independent review → export workflow works end to end**. It is not complete merely because a graph renders or an endpoint returns mocked values.

---

## 2. Scope and cut line

### 2.1 Must build for the prototype

1. A small, deterministic synthetic transaction ledger with the golden worked example and at least one boundary branch.
2. A minimal repeatable dataset load path: seed command or small CSV/JSONL upload; seed command is the guaranteed path.
3. Structured complaint intake and exact transaction reference resolution.
4. Pure proportional pooled-inflow trace engine with shared sibling budget, UTC ordering, paise-safe arithmetic, confidence, bounds, and boundary terminal nodes.
5. Persistence of complaints, cases, trace inputs/parameters/results, evidence, recommendation drafts/decisions, and core audit events.
6. API responses for graph, account detail, recent transactions, money decomposition, hop timeline, and accounts-to-review from one canonical trace result.
7. Analyst and supervisor identities with server-side role checks and different-user approval enforcement.
8. JSON case/recommendation export with canonical content hash. PDF is optional after the full flow works.
9. Docker Compose backend with one-command startup and seeded demo state.
10. A stable OpenAPI contract and sample client handoff; the UI mock/reference is not implemented by this backend plan.

### 2.2 Explicitly defer

- Full 2 GB uploads, streaming ingestion, scheduled directory/object prefix watcher, and complete data-administration screens.
- Full OIDC/SAML institutional setup, user-management UI, and multi-tenant deployments. Keep role enforcement real; use seeded synthetic demo users.
- PII vault or customer identity resolution. Store pseudonymous account identifiers only.
- Account risk scoring, logistic-regression training, and AMLworld evaluation unless a working, independently evaluated model is ready without putting the trace workflow at risk. Never display fake scores.
- PDF exports unless JSON export and workflow are already stable.
- Production retention scheduler, full backup/restore operations, 10-user load target, Tier 2/3 benchmarking, and external security certification.
- Voice/screenshot complaint parsing, Slack/calendar, NCRP/CFCFRMS integration, live core banking, inter-bank trace continuation, and globe backend location enrichment.
- Any automatic freeze or external bank action.

### 2.3 Preserve these even when cutting scope

- Proportional pooled-inflow is the only active v1 rule.
- Each account has one shared remaining-money budget across its outgoing siblings.
- Decimal arithmetic and paise rounding; no float equality for money.
- Causality: credits must have arrived before attributed outgoing transfers.
- Four separate account values: traced in, traced out, unmoved upper bound, available balance.
- Unknown balance is explicitly “balance unknown.”
- Out-of-institution transfers end the branch and report the amount that crossed.
- Search-bound termination and natural terminal endpoints have different reasons.
- No automatic freeze; second-person supervisor approval is real.
- No invented metrics and no claims that synthetic trace results are measured bank recovery.

---

## 3. Demonstration scenario

Use a deterministic synthetic case with internally consistent values. The primary fixture must match the locked golden example:

- Victim sends ₹1,00,000 to account A at 10:00.
- A receives ₹50,000 unrelated funds at 10:05.
- A sends ₹60,000 to B at 10:10 and ₹30,000 to C at 10:20.
- Pooled inflow at first outgoing transfer: ₹1,50,000; proportional fraction is 2/3.
- Attribute ₹40,000 to B. Shared remaining budget becomes ₹60,000.
- At second outgoing transfer, attribute ₹12,000 to C. Remaining at A is ₹48,000.
- `₹40,000 + ₹12,000 + ₹48,000 = ₹1,00,000` exactly.

Add a second seeded branch from one traced account to a known external institution or ATM terminal so the demo can show a real cutoff explanation. Do not edit the golden example to improve visual drama. Keep a separate showcase fixture if needed, and ensure its values also reconcile exactly.

### Synthetic fixture content

- Masked/pseudonymous account keys only.
- Transaction IDs, timestamps with offsets, INR amounts, payment rails, completion status, institution codes, and source row evidence.
- At least one complete-history account with opening balance for demonstrating available balance.
- At least one account without balance completeness for demonstrating “balance unknown.”
- At least one out-of-institution boundary and one explicit ATM cash-out terminal if the source row supports it.
- A separate ground-truth label file for evaluation; the trace engine never receives it.
- Visible synthetic-data label in API metadata and any sample client.

Provide a deterministic `reset-demo` operation that restores the fixture, users, complaint, and pending recommendation state. It must not wipe audit history silently; reset creates a labelled demo-reset audit event or uses an isolated database reset command intended only for local rehearsal.

---

## 4. Minimal architecture for the hackathon

### 4.1 Services

For this prototype, use the minimum stable runtime:

```text
Sample client / Swagger UI
          |
          v
FastAPI API  <----> PostgreSQL 16
                  trace/case/audit data
          |
          +-- optional Celery worker + Redis only if a task exceeds request budget
```

Start with API + PostgreSQL in Docker Compose. Add Redis/Celery and MinIO only if the selected upload/export path needs them or the job exceeds the 30-second HTTP budget. This is a deliberate hackathon simplification; the full backend handoff retains the complete five-service on-prem architecture.

Do not put business logic in route functions. The API calls services; the services call repositories and the pure trace engine. No frontend code is part of this implementation assignment.

### 4.2 Recommended code structure

```text
backend/
  pyproject.toml
  Dockerfile
  docker-compose.yml
  alembic.ini
  src/tracex/
    api/                  # v1 routers, auth dependencies, OpenAPI
    domain/               # immutable inputs/results/enums
    engine/               # pure trace algorithm and value math
    ingestion/            # fixture loader and small file parser
    repositories/         # SQLAlchemy persistence
    services/             # complaint, trace, case, review, export use cases
    auth/                 # seeded users, password/JWT, role checks
    audit/                # append-only critical-action log
    exports/              # canonical JSON case bundle and hashing
    settings.py
  migrations/versions/
  tests/
    unit/
    property/
    integration/
    fixtures/
  scripts/
    seed_demo.py
    reset_demo.py
    benchmark_tier1.py
  docs/
    openapi.json
    demo-runbook.md
```

The `engine/` package must not import `api/`, repositories/database code, services, Celery, or networking. Keep the engine callable from plain Python tests.

### 4.3 MVP deployment

- Python 3.12; FastAPI; Pydantic v2; SQLAlchemy 2.0; Alembic; PostgreSQL 16.
- Docker Compose with `api` and `postgres` required.
- Redis/Celery optional for long-running ingest/export jobs; use synchronous trace for the small fixture only if measured to remain under 30 seconds.
- No cloud model or external API required for the trace workflow.
- Use environment variables for local secrets. Do not commit credentials.
- `GET /health/live`, `GET /health/ready`, and `/docs` enabled for local demo.

---

## 5. MVP data model

Use three PostgreSQL schemas even if the hackathon implementation has fewer tables than full v1. This preserves a clear boundary for later expansion.

### `core`

- `institutions(id, code, name, is_operating_institution)`
- `accounts(id, pseudonymous_key, institution_id, opening_balance, opening_balance_at, history_complete, account_type)`
- `transactions(id, transaction_id, source_account_id, destination_account_id, amount NUMERIC(18,2), currency, timestamp_utc, original_offset, status, channel, source_institution_id, destination_institution_id, dataset_id)`
- `datasets(id, name, source, checksum, is_synthetic, row_counts, start/end timestamps, created_by)`

For the prototype dataset, a single unpartitioned transaction table is acceptable. Keep transaction schema compatible with monthly partitioning later. Uniqueness must be namespaced by source-system/institution and transaction ID. Re-uploading the same fixture/file must not duplicate rows.

### `app`

- `users`, `roles`, `user_roles` (at minimum seeded analyst and supervisor; optional seeded admin/auditor).
- `complaints` (victim pseudonym, disputed transaction reference, disputed amount, fraud/report timestamps, channel, match status, assigned analyst).
- `cases` (complaint link, status, disposition).
- `trace_runs` (case, dataset/version hash, seed, rule/version, parameters, status, canonical result JSON, result hash, created time).
- `trace_nodes`, `trace_edges`, `trace_boundaries` may be normalized tables or represented in canonical result JSON plus indexed IDs; choose one shape before API contract freeze.
- `recommendation_drafts`, `recommendation_accounts`, `recommendation_decisions`.
- `evidence_snapshots`, `case_exports`.

### `audit`

- `audit_events(id, occurred_at, actor_user_id, actor_role, action, target_type, target_id, case_id, request_id, reason, previous_hash, event_hash, redacted_payload)`.
- Append-only: API DB role can insert/select; direct update/delete rejected by database policy/trigger.

### MVP transaction fields

CSV or JSONL fields: transaction ID, source/destination pseudonymous account, decimal amount, INR currency, ISO timestamp with offset, status (`completed`, `reversed`, `pending`), channel, and source/destination institution. Only completed INR transactions enter the trace. Invalid currency, timestamp, amount, or required IDs produce row errors.

### Persisted trace response shape

One canonical trace result supplies every later view. Minimum top-level fields:

```json
{
  "trace_id": "...",
  "case_id": "...",
  "dataset_id": "...",
  "dataset_checksum": "...",
  "engine_version": "...",
  "attribution_rule": {
    "id": "proportional-pooled-inflow",
    "assumption": "Account is treated as a pool; amounts are upper bounds."
  },
  "parameters": {"max_hops": 6, "horizon_hours": 72, "min_amount": "1000.00", "work_budget_edges": 50000},
  "seed_amount": "100000.00",
  "nodes": [],
  "edges": [],
  "boundaries": [],
  "stopping_reasons": [],
  "complete": true,
  "result_hash": "..."
}
```

Every node includes separately: traced-in, traced-out, unmoved upper bound, available balance or `null`, freezable estimate or `null`, confidence, hop, institution/coverage status, evidence IDs. Every edge includes raw amount and attributed amount separately, transaction ID, UTC timestamp, source/destination, channel, confidence, and observed status. Serialize money as decimal strings.

---

## 6. Trace algorithm implementation

### 6.1 Algorithm flow

1. Start from the uniquely resolved seed transaction and its victim-to-first-destination direction.
2. Create a frontier of attributed branches, each retaining account, arrival time, amount, confidence, parent/evidence lineage, and hop depth.
3. At each hop, group query work by account but preserve distinct arrival times and lineage. Query all outgoing edges for the frontier in one indexed bulk query and all relevant pool credits in one bulk query; do not query once per account.
4. Sort by timestamp UTC, then transaction ID for determinism. Before processing an outgoing edge, add only credits that arrived at or before that edge time.
5. Apply `proportional-pooled-inflow`. Decrement the single account-level remaining traced budget after every attributed outgoing edge. Sibling transfers share that budget.
6. If destination is outside the operating institution, emit a terminal dashed-boundary record and crossed amount; do not query onward transactions beyond that point.
7. Continue breadth-first until there are no attributed transfers or a trace bound is reached.
8. Persist input version, parameters, rule, result, result hash, and stopping reason.

### 6.2 Rule and monetary precision

```python
def attribute(edge_amount: Decimal,
              remaining: Decimal,
              pool_inflow: Decimal) -> tuple[Decimal, Decimal]:
    if pool_inflow <= 0 or remaining <= 0:
        return Decimal("0.00"), Decimal("0")
    fraction = min(Decimal("1"), remaining / pool_inflow)
    attributed = min(remaining, edge_amount * fraction)
    return floor_to_paise(attributed), fraction
```

- Use Python `Decimal` end to end for money and fractions; database `NUMERIC`.
- Floor attributed values to two decimal places. Keep rounding residue at the parent so conservation holds exactly.
- Never use binary floats for amount equality or accumulation.
- Confidence for an edge is the attribution fraction multiplied by the confidence on its parent lineage; it must not rise with depth.
- Preserve lineage at account merges; query one account-level budget and never duplicate the total into each sibling path.

### 6.3 Hard bounds

Default and persist:

- Maximum hops: 6.
- Time horizon: 72 hours after seed.
- Minimum attributed amount: ₹1,000.
- Work budget: 50,000 examined edges.

Store the termination reason as a machine-readable enum and explanatory text: natural end, external-institution boundary, ATM terminal, hop limit, horizon, min amount, work budget, unresolved/missing ledger. A natural terminal and an incomplete search must not look the same.

### 6.4 Values and invariants

Per account:

- `traced_in`
- `traced_out`
- `unmoved_traced_value = max(0, traced_in - traced_out)`, upper-bound label
- `available_balance` only if opening balance and complete history are known; otherwise null
- `freezable_estimate = min(unmoved_traced_value, available_balance)` only if both values exist

At trace level, report crossed-boundary value. The completed golden path must satisfy `sum(unmoved terminal values) + crossed_boundary_value == seed_amount` exactly. At a search bound, mark `complete=false`, preserve frontier upper bounds and exact stop reason; do not claim that unexplored value is permanently lost.

Property-test over generated graphs:

1. Attributed outflow ≤ attributed inflow per node.
2. Sibling branches never spend more than their shared remaining budget.
3. Every attribution respects time causality.
4. Exact money conservation including paise residue and boundary values.
5. Confidence does not rise on a path.
6. Bounds stop at the configured point and report the correct reason.
7. Same dataset, inputs, rule, and bounds yield byte-identical canonical JSON.

---

## 7. Backend API required by the sample client

Use FastAPI-generated OpenAPI under `/api/v1`. All money values are decimal strings. Times are UTC in API responses; clients display local time. Every error contains stable `code`, safe `message`, optional field errors, and `request_id`.

### 7.1 Required endpoints

| Method/path | Purpose | Required behavior |
|---|---|---|
| `POST /api/v1/auth/login` | Demo login | Return short-lived token and actor/role; seeded demo accounts only |
| `GET /api/v1/auth/me` | Current actor | Role and display identity for review separation |
| `GET /api/v1/health/ready` | Dependency state | DB readiness, service version, seeded demo mode |
| `GET /api/v1/complaints` | Queue | Sorted by elapsed time; includes server `as_of` timestamp |
| `POST /api/v1/complaints` | Intake | Exact seed reference resolution; create complaint/case or return unresolved/ambiguous status |
| `GET /api/v1/complaints/{id}` | Complaint detail | Match status, matched transaction, report metadata, case link |
| `POST /api/v1/complaints/{id}/traces` | Run trace | Refuse unresolved complaint; accept bounds/rule only from allowed set |
| `GET /api/v1/traces/{id}` | Stored trace | Canonical graph/timeline/table data plus values, evidence, rule, bounds, completeness and hash |
| `POST /api/v1/traces/{id}/rerun` | Re-run | Creates a new immutable trace run, never mutates prior result |
| `GET /api/v1/accounts/{id}?trace_id=...` | Account detail | Pseudonymous account, four amounts, confidence, coverage, latest transactions/evidence |
| `GET /api/v1/transactions/{id}?trace_id=...` | Transaction detail | Raw and attributed amounts separately, timestamp, channel, evidence |
| `POST /api/v1/cases/{id}/recommendations` | Draft recommendation | Analyst role, amount validation, justification required |
| `GET /api/v1/recommendations?status=pending` | Supervisor inbox | Supervisor role; drafts only |
| `POST /api/v1/recommendations/{id}/decision` | Approve/reject | Different supervisor, written reason, DB check; creates document only |
| `GET /api/v1/recommendations/{id}/document` | Approved document | Read only after approval; no external side effect |
| `POST /api/v1/cases/{id}/exports` | JSON case pack | Evidence snapshot, canonical JSON, content hash, exporter ID |
| `GET /api/v1/exports/{id}` | Export metadata/download | Authorized, audited, immutable content |

### 7.2 Minimal MVP job model

Trace and seed loading can be synchronous for the small demo fixture only after timing it. Every request must stay under 30 seconds. If it may exceed that, return `202 Accepted` with `{job_id, status_url, request_id}` and expose status/progress. Do not block an HTTP worker on unbounded ingestion or export.

### 7.3 Authentication and authorization

- Seed one analyst, one different supervisor, and optionally admin/auditor roles.
- Use Argon2id password hashes and server-side role checks for every endpoint.
- Keep credentials in local demo documentation/environment, never source control.
- TOTP/OIDC may be deferred for the hackathon build, but label the auth mode as local demo mode and do not claim production authentication readiness.
- No role switching through a client-supplied `role` field. A demo may log out and back in as the seeded supervisor.
- The review API must verify current actor != draft author and role is supervisor.

---

## 8. Recommendation, audit, and export workflow

### 8.1 Recommendation data and rules

Draft contains case ID, source trace ID/hash, selected account IDs, proposed amounts, amount basis, evidence snapshot hash, written justification, author ID, status, and timestamps.

- If balance is known, recommended amount cannot exceed the freezable estimate.
- If balance is unknown, do not describe the upper bound as confirmed funds. Require an explicit “balance unknown / upper-bound only” basis and clear document caveat, or disable draft according to the demo policy.
- Only a different supervisor can approve or reject; both decisions require a written reason.
- Database has a constraint that author and decision-maker differ; service checks supervisor role.
- Approval changes state to approved and enables document generation only. It does not make an HTTP call, update an account, or tell a bank to freeze.

### 8.2 Audit minimum for demo

Append an audit event for login/logout, complaint create/match, trace start/complete, account/transaction evidence access, recommendation draft, decision, export, and demo reset. Include actor, role, action, target, case, timestamp, request ID, and reason where required. Redact raw PII/secrets. Use hash chaining and block update/delete at DB role/trigger level if feasible within the stage-critical path; the audit row itself must not be editable from the API.

### 8.3 Export

Mandatory export is a JSON bundle containing:

- schema version, case and complaint metadata;
- source dataset ID/checksum and synthetic-data marker;
- exact trace result/hash, rule, engine version, parameters, and stopping reasons;
- evidence transaction references and money decomposition;
- recommendation, justification, approval/rejection actor and reason;
- exporter identity and UTC export time;
- deterministic content hash over canonical JSON.

PDF is optional. Never export credentials, secrets, or unmasked customer identity.

---

## 9. Team plan and integration ownership

Use the five teammates around independent vertical slices with one shared contract. Reassign based on actual experience, but avoid splitting the trace algorithm across multiple owners.

| Owner | Primary responsibility | Must deliver |
|---|---|---|
| Sunil Dehru (lead) | Scope, integration, API/demo acceptance, judge narrative | Frozen scenario, OpenAPI contract review, final build/runbook, demo rehearsal |
| Sri Charan Reddy | FastAPI app shell, auth/RBAC, complaint/case/recommendation routes | Working API startup, role checks, two-user approval path |
| Srinivasula Avinash | Trace engine and value invariants | Pure engine, golden fixture, property tests, deterministic result contract |
| Sai Charan Sathwik | Data model, fixture/generator, ingestion and PostgreSQL repository | Seed/reset, idempotent ledger load, bulk transaction queries |
| Bhavadeep | API client integration/sample screen contract, export polish, integration verification | Consume OpenAPI, complete screen walkthrough against real API, export preview |

The assignment does not require a new frontend implementation if a separate agent/team member is already building the sample UI. In that case Bhavadeep (or the UI owner) should integrate against the OpenAPI contract and report missing backend fields early.

### Integration rules

- Freeze core Pydantic result models by the first integration checkpoint.
- Keep one shared `Project/Complaint/TraceResult/Recommendation` contract; do not create parallel schemas.
- Commit small working vertical slices; keep the seed/demo scenario runnable at all times.
- Frontend uses API/OpenAPI only; it never queries Postgres or calculates trace amounts.
- Merge the trace fixture before graph rendering so UI data and tests use the same output.

---

## 10. Relative 36-hour schedule and judge checkpoints

The event schedule provided by the team has overnight time entries; align these relative phases with the organizer’s current checkpoint times. The goal is to have a usable prototype before the first working-prototype evaluation, not to defer integration until the end.

| Relative time | Build target | Exit condition |
|---|---|---|
| Hours 0–2 | Lock scenario, repository, Compose, domain/API contract | API and DB start; golden fixture agreed |
| Hours 2–6 | Schema, seed loader, complaint intake, stub OpenAPI | UI/sample client can load case and complaint from API |
| Hours 6–12 | Trace engine and PostgreSQL bulk query path | Golden result correct; no-amplification and causality checks pass |
| Hours 12–16 | Persist trace, return nodes/edges/bounds/account values | One end-to-end complaint-to-trace flow works in the sample client |
| Hours 16–21 | Account detail, evidence, recommendation draft | Analyst can inspect evidence and draft; no unsupported amount claims |
| Hours 21–25 | Supervisor login, independent approval, JSON export | Self-approval denied; approved document/hash can be downloaded |
| Hours 25–28 | Integration freeze and full walkthrough | Full demo runs twice from reset; no critical path depends on internet |
| Hours 28–36 | Feature freeze, bug fixes, polish, backup, rehearsal | Build and fixture stable; presentation and fallback ready |

Map to the supplied VISTERA checkpoints: show the scenario and architecture at evaluation 1; demonstrate a real vertical slice by the working-prototype milestone; use later evaluations for a stable walkthrough and limitations; freeze features before the final submission window. If the build starts late, cut PDF, model scoring, broad ingestion, and admin breadth first—never cut trace correctness, recommendation boundary, or second-person approval.

---

## 11. Implementation milestones and acceptance

### MVP-0: runnable skeleton

**Implement:** Compose API+PostgreSQL, settings, Alembic baseline, request ID middleware, health/readiness, structured errors, OpenAPI docs.

**Accept when:** clean startup works; database migration applies; `/health/ready` checks the database; a synthetic-data badge is returned in demo metadata.

### MVP-1: deterministic data and complaint

**Implement:** golden fixture, reset script, seed users, transaction schema, complaint creation, exact ID match, complaint queue.

**Accept when:** reset creates the same data every time; exact match succeeds; unresolved ID is refused; queue sorts by elapsed time; all times are UTC in API.

### MVP-2: trace engine and persistence

**Implement:** proportional pooled inflow, one shared account budget, frontier bulk queries, bounds, terminal boundaries, confidence, value decomposition, trace persistence and canonical hash.

**Accept when:** golden fixture matches expected values exactly; 10,000 generated graph properties pass; repeated run is byte-identical; boundary branch terminates; balance unknown is null in API and labelled by client.

### MVP-3: evidence and case flow

**Implement:** account/transaction detail, evidence IDs, case record, notes or a minimal case timeline, recommendation draft.

**Accept when:** every graph edge maps to a ledger transaction; account detail shows recent transactions from same result; draft references saved trace hash and parameters.

### MVP-4: reviewer and export

**Implement:** two demo actors, role authorization, DB author/approver constraint, decision reason, JSON export hash, audit trail.

**Accept when:** analyst can draft; analyst cannot approve own draft; different supervisor can approve/reject with reason; approval creates no external action; exported hash verifies.

### MVP-5: polish and rehearsal

**Implement:** data consistency checks, log redaction, API docs, launch script, demo reset, demo runbook, known limitations.

**Accept when:** two clean end-to-end runs succeed on the presentation machine; no external service is required for core workflow; team can explain each estimate and cutoff.

---

## 12. Test and verification checklist

These are implementation acceptance checks, not claims that tests have already been run.

### Trace correctness

- Golden fixture: B ₹40,000; C ₹12,000; A upper-bound unmoved ₹48,000.
- Sibling transfers share one account budget; attributed out never exceeds attributed in.
- Pool includes only credits received by each outgoing transfer time.
- Reversed and pending transactions are excluded.
- Amount rounding residue stays with parent; exact conservation in paise.
- Same inputs and parameters produce identical canonical JSON/hash.
- Each cutoff type is separately surfaced and tested.
- Confidence compounds and does not rise with hop depth.

### Workflow and access control

- Complaint resolves to exact transaction or refuses/asks for explicit disambiguation.
- Trace saves parameters, dataset checksum, engine/rule version, and evidence references.
- Every amount in graph/table/API comes from the same stored trace result.
- Analyst drafts, supervisor approves/rejects with reason, author cannot self-approve.
- Database rejects self-approval even if API validation is bypassed.
- Auditor is read-only if included in demo.
- Approval produces a document only; static check confirms no outbound freeze client.

### Privacy and demo safety

- Synthetic label appears in metadata and export.
- No personal names or full customer identifiers in logs/errors.
- No placeholder risk scores, precision/recall, recovery rates, or performance figures.
- Unknown balance is not zero; unmoved value is always “up to”/upper bound.
- External institution and ATM endpoints show the last observed evidence and why no further trace exists.

---

## 13. Three-minute prototype walkthrough

1. **Problem (20 sec):** “A complaint identifies one transfer; current workflows often stop at the first receiving account. TRACE-X follows the attributed value through this institution’s ledger and makes the evidence reviewable.”
2. **Complaint (20 sec):** open the synthetic case; show the reported amount, timestamp, exact matched transaction, and dataset badge.
3. **Trace (60 sec):** run the trace; show the branch graph; animate/replay one path; select an account to show evidence, confidence, separate traced-in/out, and balance unknown or supported balance.
4. **Boundary (25 sec):** click an out-of-institution or ATM terminal; show the last observed transaction and exact reason. State that the system does not pretend to see beyond this ledger.
5. **Decision (35 sec):** analyst drafts a recommendation; sign in as a different supervisor; show self-approval is prevented and independent approval creates a document only.
6. **Trust and close (20 sec):** download/verify JSON case pack; explain proportional pooled-inflow and shared sibling budget; identify synthetic data and unmeasured metrics honestly.

If the live UI/API fails, use a local seeded result or prerecorded fallback only if clearly labelled as a fallback. Do not simulate a real bank action.

---

## 14. Requirement coverage for the hackathon slice

| Requirement IDs | MVP treatment |
|---|---|
| FR-01–04 | Seeded fixture required; small upload/idempotency preferred; 2 GB streaming deferred |
| FR-05–06 | Implement UTC normalization, original offset, dataset manifest |
| FR-07 | Defer watched directory/object prefix pickup |
| FR-08 | Implement deterministic seeded generator or equivalent fixed fixture |
| FR-09, FR-42 | Defer full retention/deletion UI; do not silently erase audit/evidence |
| FR-10–14 | Implement core complaint, exact match, queue and assignment; complaint linking optional |
| FR-15–23 | Implement core trace, persistence, rerun, bounds, graph/timeline/table API shape |
| FR-24–30 | Defer scoring unless trained/evaluated; return no score rather than fake value |
| FR-31–36 | Implement draft, second-person approval, document export only, no external action |
| FR-37–41 | Implement minimal case/evidence snapshot/export and audit of critical workflow; full audit search deferred |
| FR-43–46 | Seeded role users and health; full admin screens/configuration/evaluation deferred |
| FR-47–54 | Implement all value/boundary/confidence/resolution semantics in trace result |
| NFR-01–03, 05–08 | Tier 1 baseline only if time; no Tier 2/concurrency promises without measurements |
| NFR-04, 11, 13, 18, 20, 25–27 | Implement request budget, readiness, JSON logs/request ID, role checks, secrets hygiene, migration, v1 API, one-command seed |
| NFR-09–10, 12, 14–17, 19, 21–24 | Production-grade portions staged; preserve rollback/idempotency and engine testing; full operations/security hardening deferred |
| NFR-28–31 | API provides explanations/time data; full UI usability/accessibility depends on separate frontend work |
| SR-01–08 | No automatic action, lead framing, no discriminatory features, second approval, upper-bound semantics; scoring-only SRs deferred if no model |
| PR-01–06 | Pseudonymous identifiers, no vault for MVP, audit resolution if ever enabled, clear synthetic retention, hashed export, redacted logs |

Maintain a requirement status sheet with `Implemented`, `Deferred`, or `Not in MVP`, evidence/test reference, and owner. Do not mark a requirement complete because an endpoint exists without its acceptance behavior.

---

## 15. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Too many features dilute the demo | Protect the six-step vertical slice; defer scoring, OIDC, PDF, and broad ingestion |
| Trace arithmetic produces invented money | Shared sibling budget, Decimal arithmetic, golden fixture, property invariants |
| Large import consumes the event | Seeded fixture is the guaranteed path; keep upload small and optional |
| AI/model claim is challenged | Trace is deterministic arithmetic; no fake score; report dataset source for any model metrics |
| Graph and API show different values | One persisted trace result is the source for every projection |
| Approval is only enforced in UI | API role check plus PostgreSQL author/approver constraint |
| Team cannot finish production authentication | Demo auth uses seeded identities with real server authorization; mark TOTP/OIDC as deferred |
| Presentation internet or provider fails | No external service required for seed, trace, approval, or export |
| Globe/location visuals imply unsupported facts | Backend provides sourced location only; otherwise map is hidden or labelled synthetic; coverage is institution-based |

---

## 16. Agent handoff instructions

1. Start by verifying the code repository path and current branch; the requirements folder is documentation, not the code repository.
2. Create the backend skeleton and Compose foundation before feature work.
3. Implement the golden trace fixture and pure engine before broad ingestion, scoring, or admin work.
4. Publish the Pydantic/OpenAPI trace result contract early so the UI agent can integrate against it.
5. Keep a working seeded complaint-to-trace path on the main branch after every milestone.
6. Do not implement the frontend or globe in this assignment; provide sample API responses/Swagger and a stable contract for the UI owner.
7. Do not add unapproved scope mid-build. Put it in the deferred list.
8. Report unimplemented requirements and known limitations explicitly at handoff.

---

## 17. Final recommendation

Build the hackathon MVP as a deliberately narrow, real workflow: **synthetic complaint → exact transaction resolution → deterministic trace → evidence inspection → analyst draft → independent supervisor approval → hashed case export**. Keep the backend small enough to finish and truthful enough to defend. The full backend handoff remains the post-hackathon roadmap; this file is the scope the implementation agent should optimize for during the prototype stage.
