# TRACE-X Backend Implementation Handoff

**Purpose:** implementation-ready backend plan for the agent building TRACE-X  
**Scope:** backend architecture, database, APIs, trace engine, evaluation, security, and operations  
**Explicitly excluded:** frontend implementation, UI styling, graph rendering, and globe rendering  
**Primary sources:** `D:\AmbiFlow\Requirements4.md`, `D:\AmbiFlow\Requirements3.md`, and `D:\Downloads\TRACE-X_HANDOFF.md`  
**Product:** TRACE-X — trace a fraud complaint through a single institution's transaction ledger and produce an evidence-backed, human-reviewed recommendation document.

> This document is an implementation handoff, not code. It fixes backend decisions for the implementing agent and identifies the few source-document conflicts that require explicit handling. The frontend should use the backend's versioned OpenAPI contract and must not recompute analysis.

---

## 1. Objective and backend boundary

Build a deployable, single-institution backend that accepts transaction datasets and fraud complaints, resolves a complaint to a ledger transaction, computes a deterministic forward trace, explains account scores, persists cases and decisions, enforces separation of duties, and exports an auditable case pack.

The v1 product boundary ends at a recommendation document. No API or worker may instruct a bank to freeze, block, report, or otherwise restrict an account. Do not add an outbound banking client. The freeze/recommendation service must have no outbound HTTP dependency.

### 1.1 Backend outcomes

- A repeat upload is idempotent and a failed ingest does not partially change committed ledger data.
- A complaint either resolves to a transaction with a documented match result or is refused for tracing.
- The trace is reproducible from persisted parameters and a snapshot of the input dataset version.
- Money attribution is exact to the paise, causal in time, bounded, and never amplified.
- Analysts can inspect evidence, prepare a recommendation, and submit it to an independent supervisor.
- The database rejects self-approval; authorization is also checked in application services.
- Audit records are append-only, actor-attributed, and retained according to the audit boundary.
- Model evaluation reports name their dataset; no placeholder metrics are represented as measured results.

### 1.2 Not in this backend build

- Frontend, graph canvas, globe, animation, or visual account map.
- Live core-banking, card-network, NCRP, or CFCFRMS integration.
- Cross-institution trace continuation without an authorized partner ledger.
- Automatic freeze or outbound action of any kind.
- Graph database, graph neural network, streaming/real-time ingestion, Kubernetes, multi-region operation, or multi-tenant SaaS.
- Customer identity resolution in the analyst database. A separate PII vault is optional and must remain a separately permissioned later module unless specifically needed by the pilot.
- Voice or screenshot complaint parsing as a blocking v1 dependency. Intake accepts structured fields; parsing can be added as an optional adapter after the core path works.
- Boundary-request resume loop. Preserve boundary evidence and schema extensibility, but defer resuming a trace from another bank's response until a formal requirement and authorized data exchange exist.

---

## 2. Binding decisions and source reconciliation

Treat the TRACE-X handoff's locked decisions as authoritative where present. Requirements4 is the latest requirements source and is available. Requirements3 was checked for its FR/NFR/SR/PR inventory; use it only where the two versions agree. Before requirement-to-test closure, produce a delta list if either document changes.

| Topic | Binding implementation choice |
|---|---|
| Backend stack | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, PostgreSQL 16, Redis + Celery, pandas, NumPy, scikit-learn; NetworkX only for bounded subgraph analysis |
| Deployment | One on-prem Docker Compose host: API, worker, PostgreSQL, Redis, MinIO |
| Database | PostgreSQL schemas `core`, `app`, `audit`; monthly transaction partitions; no graph database |
| Main transaction index | Partial index on `(source_account, timestamp)` where `status='completed'`; add destination-side and ID lookup indexes as specified below |
| Trace rule | `proportional-pooled-inflow` only in v1; FIFO and lowest-intermediate-balance are not implemented |
| Sibling transfers | A single account-level remaining-money budget is decremented after each attributed outgoing transfer; never give each child the full budget |
| Money fields | Keep traced-in, traced-out, unmoved upper bound, and available balance separate; absent balance is `balance unknown` |
| Trace bounds | Defaults: 6 hops, 72-hour horizon, ₹1,000 minimum attributed amount, 50,000 edge work budget; persist actual parameters and each stopping reason |
| Confidence | Attributed fraction compounded along each path; it cannot increase with depth |
| Institutional boundary | Out-of-institution transfers terminate in v1 with reason and crossed amount; do not invent downstream visibility |
| Approval | Analyst drafts; a different supervisor approves/rejects with a reason; approval creates an exportable document only |
| Scoring | Logistic regression; weights learned from benchmark labels, not hand-picked; account age alone and location are not model features |
| Evaluation | Detection on IBM AMLworld; trace/path recovery on own seeded generator; keep metrics separate and name the source dataset |
| Performance | Measure on team hardware and named dataset tier before committing budgets; do not present working targets as measured results |
| Engine boundary | `engine/` imports nothing from `api/`, `db/`, or `services/`; enforce with import-linter in CI |

### 2.1 Requirement numbering and test-map reconciliation

Requirements have FR-01 through FR-54, but FR-47 through FR-54 appear earlier in the document than FR-24 through FR-46. IDs are unique but ordering is nonsequential. Keep IDs as written; do not renumber silently. Build a machine-readable requirements-to-tests map and flag missing/duplicate IDs. Before calling a requirement covered, map every FR/NFR/SR/PR to its test or explicitly mark it deferred/out of scope for the hackathon slice.

### 2.2 Requirement conflicts to resolve in implementation

1. **Delete dataset vs retain decision evidence:** dataset deletion removes dataset-owned raw rows and derived operational artifacts; immutable case decision snapshots and append-only audit survive, while traces depending on the deleted dataset become stale and cannot back new recommendations. Implement and document this boundary.
2. **Freeze recommendation terminology:** internally the artifact may retain `freeze_recommendation`/`freeze_request` to match the requirements, but externally it is a draft recommendation document only. It never executes an account action.
3. **“Unmoved” vs actual balance:** `unmoved_traced_value` is a ledger-derived upper bound. `freezable_estimate` exists only when supported balance data is present, and equals the lower of the upper bound and available balance. Do not label an upper bound as a confirmed holding.
4. **Location and coverage:** location is forbidden as a scoring feature. If later used for a geographic view, it may only be displayed as sourced metadata and must not imply trace visibility. Institution coverage determines trace boundary, not country alone.

---

## 3. System architecture

### 3.1 Services

```text
Analyst / sample client
          |
          v
FastAPI API  -----------------------> PostgreSQL 16
  |  auth, RBAC, validation             core / app / audit schemas
  |                                      monthly transaction partitions
  +---- job submission ---> Redis ---> Celery worker
                                  |       ingestion / trace / scoring / export
                                  +----> MinIO
                                         source files / generated case packs
```

The sample UI talks only to the versioned HTTP API and consumes the generated OpenAPI schema. It does not access the database or call the trace engine directly.

### 3.2 Service responsibilities

- **API:** authentication, permission checks, request validation, idempotency keys, domain service invocation, job status/progress, audit context, response serialization.
- **Worker:** long ingestion, trace, score/evaluation, retention, and export jobs. Job messages contain identifiers and parameters, not large raw payloads.
- **PostgreSQL:** canonical ledger, app state, versioned analysis outputs, audit chain, and constraints.
- **Redis:** Celery broker/result coordination and rate-limit/short-lived session state only. Do not treat Redis as durable business storage.
- **MinIO:** uploaded source files, quarantined input, and generated export objects. Store object hash and metadata in PostgreSQL.
- **Trace engine:** pure deterministic library called by services/workers, with no API/DB/service imports and no network capability.

### 3.3 Backend module boundaries

Recommended repository layout:

```text
backend/
  pyproject.toml
  alembic.ini
  Dockerfile
  docker-compose.yml
  src/tracex/
    api/                 # FastAPI routers, dependencies, OpenAPI tags
    auth/                # password/OIDC, token rotation, permissions
    domain/              # immutable domain types and enums
    engine/              # pure trace and money-attribution logic
    ingestion/           # parsers, validation, staging, commit, generator
    features/            # deterministic feature builders and registry
    scoring/             # logistic model adapter, explanations, evaluations
    services/            # use cases and transaction boundaries
    repositories/        # SQLAlchemy persistence adapters
    jobs/                # Celery tasks, progress, retry policy
    exports/             # canonical JSON bundle and PDF generation
    audit/               # append-only audit writer and chain verification
    observability/       # structured logging, metrics, health checks
    settings.py
  migrations/versions/
  tests/
    unit/
    property/
    integration/
    contract/
    fixtures/
  scripts/               # seed, benchmark, restore-check, requirement-map
  docs/                  # API and operational runbooks
```

Only `engine/` is strictly framework- and persistence-free. Keep it importable directly by unit/property tests. `domain/` may be imported by all other packages; it must not import infrastructure.

### 3.4 Dependency rules

- `api -> services/domain`; never directly implements business policy.
- `services -> domain + repository interfaces + engine`; owns transactions/use-case orchestration.
- `repositories -> db/domain`; translates rows to domain types.
- `engine -> Python standard library/domain primitives only`; no API, DB, services, Celery, pandas, or network imports.
- `jobs -> services`; task functions are thin wrappers around application use cases.
- `scoring -> features/domain`; feature builder cannot import label tables.
- `freeze/recommendation service -> repositories/domain`; no HTTP client or network dependency.
- Enforce import direction in CI with import-linter and a dedicated static check that the freeze service has no outbound client dependency.

---

## 4. Data model and storage plan

Use SQLAlchemy 2.0 models and Alembic migrations. Use UTC `timestamptz` for normalized times and retain original source offset in ingestion records where required. Monetary values are `NUMERIC(18,2)` (Python `Decimal`) for INR. Never use floating point for amount arithmetic or equality comparisons.

### 4.1 PostgreSQL schemas

#### `core` — institution ledger

- `institutions`: institution code, display name, operating-institution flag, coverage metadata.
- `accounts`: pseudonymous account key, institution code, optional opening balance/time, history completeness, account type, KYC enum where authorized, opened date only as source metadata (not a scoring feature).
- `transaction_identity`: global unique transaction ID registry mapping an ID to event timestamp/partition and row key. Required because PostgreSQL partitioned unique constraints must include the partition key; this table gives global idempotency by transaction ID.
- `transactions`: monthly range-partitioned rows, transaction ID, source/destination pseudonymous keys, amount, currency INR, timestamp UTC, original offset, status, channel, source/destination institution, optional source balance-after, dataset ID, import row reference.
- `dataset_labels`: evaluation-only labels, isolated from feature tables/builders.
- Optional `account_history_coverage` metadata for balance completeness and coverage windows.

#### `app` — operational case state

- `users`, `roles`, `user_roles`, `sessions`, `refresh_tokens` (hashed), `oidc_identities`.
- `datasets`, `dataset_uploads`, `ingestion_jobs`, `ingestion_row_errors`, `dataset_deletion_jobs`.
- `complaints`, `transaction_match_results`, `assignments`, `complaint_links`, `cases`, `case_notes`, `case_dispositions`.
- `trace_runs`, `trace_parameters`, `trace_nodes`, `trace_edges`, `trace_boundaries`, `trace_progress` or equivalent normalized JSON result plus indexed lookup columns.
- `feature_sets`, `feature_values`, `score_configs`, `score_config_versions`, `model_artifacts`, `score_runs`, `score_explanations`, `evaluation_runs`, `analyst_feedback`.
- `recommendation_drafts`, `recommendation_accounts`, `recommendation_decisions`, `recommendation_outcomes`.
- `evidence_snapshots`, `case_exports`, `retention_policies`.

#### `audit` — append-only event history

- `audit_events`: event ID, prior hash, event hash, actor, role snapshot, action, target type/ID, case/dataset context, UTC time, request ID, reason, redacted metadata.
- Optional `audit_checkpoints`: periodic signed/checkpoint hash and verification metadata.

### 4.2 Indexes and partitions

Required handoff index:

```sql
CREATE INDEX ix_txn_src_ts
  ON core.transactions (source_account, timestamp)
  WHERE status = 'completed';
```

Add:

- `core.transactions(destination_account, timestamp)` partial on completed rows for pool inflow lookup.
- `core.transactions(dataset_id, timestamp)` for dataset lifecycle and time windows.
- `core.transaction_identity(transaction_id)` unique primary key for global deduplication.
- `app.complaints(reported_time, status)` for queue ordering.
- `app.trace_runs(case_id, created_at)` and `app.trace_runs(dataset_id, status)`.
- `app.recommendation_drafts(status, created_at)` for supervisor queue.
- Audit indexes on `(occurred_at)`, `(actor_user_id, occurred_at)`, `(case_id, occurred_at)`, `(target_type, target_id, occurred_at)`.

Partition `core.transactions` by month on UTC timestamp. Create the needed future partitions ahead of time. Unknown/out-of-range rows go to a controlled default partition or are rejected with a clear ingestion report; do not silently lose them. Deduplication identity is `(source_system/institution namespace, transaction_id)` so IDs from unrelated source systems cannot collide. For the single-institution demo, use one stable source namespace. Enforce it through `transaction_identity` in the same DB transaction as row commit. Define retry and cleanup behavior if the transaction registry and partition insert conflict.

### 4.3 Ingestion transaction model

1. Create upload record with checksum, uploader, source, declared format, chosen bad-row policy, and file object key.
2. Parse stream into bounded batches; do not load a 2 GB file into memory.
3. Validate schema and business constraints; write normalized good rows and row errors into staging tables tied to the upload.
4. Produce an immutable validation report: total rows, valid rows, invalid rows, duplicates, time range, currencies, checksums, field-level issues.
5. If policy is reject-whole-batch and any invalid row exists, keep staged data uncommitted and mark the upload rejected.
6. If policy is quarantine, commit only valid rows and preserve quarantined row references/report; dataset clearly records partial acceptance.
7. Commit accepted transactions idempotently via `transaction_identity`; update dataset manifest atomically.
8. Enqueue downstream feature/index refresh only after commit.
9. If any commit step fails, roll back ledger changes and mark job failed; make retry safe.

Dataset checksum is a file-level integrity key, not a substitute for transaction ID idempotency. Re-uploading the same file must add zero transactions and report duplicates.

### 4.4 Transaction input schema

Accept CSV and JSON Lines. Validate these fields:

| Field | Backend rule |
|---|---|
| `transaction_id` | Required, stable, unique within/global registry; preserve source string normalization policy |
| `source_account`, `destination_account` | Required pseudonymous keys; reject blank/self-transfer policy should be explicit and consistent |
| `amount` | Required `Decimal(18,2)`, > 0 |
| `currency` | ISO 4217 input; v1 accepts INR only and rejects other values |
| `timestamp` | Required ISO 8601 with offset; normalize UTC and retain original offset |
| `status` | `completed`, `reversed`, `pending`; only completed rows participate in trace/scoring windows |
| `channel` | Optional enum/string, normalized; examples UPI, IMPS, NEFT, RTGS, card, ATM, internal |
| `source_bank`, `destination_bank` | Optional institution codes used to identify operating-institution boundary |
| `balance_after_source` | Optional decimal, not sufficient alone to claim full account balance |
| `dataset_label` | Evaluation-only; must never enter feature builder or API output for operational analyst |

### 4.5 Data deletion, snapshots, and retention

- Every deletion is an authorized job with a dry-run summary and audit event.
- Delete dataset-owned transaction rows, upload objects, derived features, model input caches, and non-case operational results according to the chosen retention rule.
- Preserve append-only audit events.
- Preserve case decision evidence snapshots required for audit; snapshot must be pseudonymous/redacted and include dataset/trace version, calculation parameters, cited transactions, and artifact hash.
- Mark traces that depend on deleted or changed source data as stale. They cannot support a new recommendation.
- Do not silently rewrite or delete a previously approved decision snapshot. Apply retention/anonymization policy to its sensitive fields under the documented case/audit policy.

---

## 5. Trace engine specification

### 5.1 Pure engine contract

Implement `engine.trace(trace_input) -> TraceResult` as a deterministic pure function. `trace_input` contains a seed transaction/account, normalized completed transactions needed for the bounded horizon, account coverage metadata, trace parameters, and rule version. The engine must not query PostgreSQL, Redis, MinIO, HTTP, or any model.

The service/repository layer loads all relevant data for a hop frontier in batched queries, invokes the engine, persists the immutable result, and records the dataset version and parameters.

### 5.2 Frontier query plan: one query per edge direction per hop

Breadth-first forward walk in time:

1. Build the full frontier for the current hop and merge work by account for query efficiency while preserving arrival timestamps and lineage fragments.
2. Query completed outgoing transactions for the entire frontier in one indexed query, constrained by the trace horizon and timestamps after relevant arrivals.
3. Query incoming credits for the entire frontier in one indexed query to calculate pooled inflow available before each outgoing edge.
4. Group/sort rows by account and timestamp in deterministic order; process outflows in UTC timestamp order, with transaction ID as a stable tie-breaker.
5. Attribute each outgoing transfer once against a single shared account budget. Decrement that budget immediately after each attributed edge. Never let sibling edges each claim the full parent amount.
6. Create next-hop branches for attributed transfers and repeat until natural termination or a bound.

Do not issue one query per account. Do not use NetworkX or pandas as the main transaction index. If Postgres misses measured budgets, benchmark an in-memory index as an optimization without changing engine semantics.

### 5.3 Attribution rule

Implement only `proportional-pooled-inflow` in v1:

```python
class ProportionalAttribution:
    name = "proportional-pooled-inflow"
    assumption = (
        "Treats the account as a pool. Attributed amounts are upper bounds, "
        "not proof these specific funds are the victim's."
    )

    def attribute(self, edge_amount: Decimal,
                  remaining: Decimal,
                  pool_inflow: Decimal) -> tuple[Decimal, Decimal]:
        if pool_inflow <= 0 or remaining <= 0:
            return Decimal("0.00"), Decimal("0")
        fraction = min(Decimal("1"), remaining / pool_inflow)
        amount = min(remaining, edge_amount * fraction)
        return floor_to_paise(amount), fraction
```

Preserve the account-level shared budget after each edge. Preserve arrival time and branch lineage so funds arriving later are not used to explain earlier transfers. Where branches merge at one account, perform one account-level budget calculation and keep provenance fragments for output/evidence; never duplicate a merged amount into sibling branches. Make the fragment distribution deterministic and test it against the golden fixture before relying on it for path display.

Do not implement FIFO or lowest-intermediate-balance in v1. Define a strategy interface only if it does not broaden the implementation or obscure the one active rule.

### 5.4 Bounds and termination

Defaults:

- `max_hops = 6`
- `horizon = 72 hours` after seed transaction
- `min_amount = INR 1,000.00`
- `work_budget = 50,000` examined edges

Persist effective values and termination reason. Distinguish:

- natural stop: no later attributable transfer;
- institutional boundary: destination institution differs from operating institution;
- known terminal channel: e.g. ATM cash withdrawal, if the ledger evidence explicitly establishes it;
- max hops reached;
- horizon reached;
- min amount filtered;
- work budget exhausted;
- missing ledger coverage or unresolved data.

“Money stopped here” (known terminal endpoint/no later transaction in covered history) and “search stopped here” (a trace bound or missing coverage) must never share one generic status.

### 5.5 Money decomposition and conservation

Per account, persist distinct fields:

- `traced_in`: total attributed amount entering the account.
- `traced_out`: total attributed amount leaving the account.
- `unmoved_traced_value = max(0, traced_in - traced_out)`, labelled an upper bound everywhere.
- `available_balance`: populated only when an opening balance and complete account history support computation; otherwise null, rendered as “balance unknown.”
- `freezable_estimate`: null unless both unmoved upper bound and available balance exist; otherwise `min(unmoved_traced_value, available_balance)`.

At trace level, report amount crossing the institutional boundary separately. Under the locked trace-accounting rule, `sum(unmoved_terminal_values) + crossed_boundary_value == seed_amount` exactly for a completed in-scope trace. Keep rounding residue at the parent. Floor amounts to paise at attribution boundaries. Never compare floats for equality.

Where a trace stops because of a work bound/horizon/hop limit rather than a natural terminal path, identify the frontier as **search not completed** and do not falsely say the money stopped moving or was permanently lost. Retain the remaining attributed value as an upper-bound amount at that frontier, attach the exact stopping reason, and block new recommendations from a stale/incomplete trace unless policy explicitly permits a documented review path. Preserve the source's exact money-conservation invariant and four core per-account quantities; do not silently add a fifth user-facing “lost” amount.

### 5.6 Confidence and determinism

- Edge/hop confidence is the attributed fraction for that hop, compounded along the lineage.
- Confidence must not rise with depth for a single path.
- Use Decimal internally for fractions or a defined fixed precision; serialize deterministically.
- Sort nodes, edges, boundaries, and diagnostics by stable IDs/timestamp before canonical serialization.
- Given identical dataset version, seed, parameters, attribution version, and engine version, output canonical JSON bytes are identical.
- Persist rule name, version, assumptions, approximate/upper-bound marker, bounds, input dataset/version hash, and engine build identifier.

### 5.7 Required invariants

Run property-based tests on at least 10,000 generated graphs:

1. At every node, attributed outflow ≤ attributed inflow.
2. A shared parent budget cannot be spent more than once across siblings.
3. Every child transfer timestamp is ≥ its causal arrival time.
4. The trace's money decomposition conserves the seed amount exactly, including rounding and boundary residue.
5. No transaction is attributed beyond the configured horizon or bounds.
6. Confidence never increases with depth along a lineage.
7. Identical input and parameters produce byte-identical canonical result.
8. Completed/reversed/pending status filtering is respected.
9. Boundary destinations terminate and do not lead to transactions from another institution in this dataset.

Golden fixture: implement `tests/fixtures/worked_example.json` exactly as defined in the handoff. Victim sends ₹1,00,000 to A at 10:00; A gets ₹50,000 unrelated at 10:05; A sends ₹60,000 to B at 10:10 and ₹30,000 to C at 10:20. Expected attribution: B ₹40,000, C ₹12,000, A unmoved upper bound ₹48,000; exact total ₹1,00,000.

---

## 6. Complaint intake and transaction resolution

### 6.1 Complaint fields

Persist complaint ID, pseudonymous victim account, disputed transaction reference, reported/disputed amount, fraud time, reported time, report channel, optional fraud type, intake source, match result, assigned analyst, case link, status, created/updated timestamps.

### 6.2 Transaction matching

At intake, resolve the reported transaction against accepted dataset rows using transaction ID/reference first. If that fails and matching by secondary fields is supported, use a documented deterministic matcher over account, amount, timestamp window, channel, and institution; return candidate match confidence and evidence fields. Do not silently pick an ambiguous candidate.

- Exact unique ID match: return high/confirmed match state.
- No match: state `unresolved`; trace endpoint returns a conflict/validation error and does not create a trace.
- Multiple plausible matches: state `ambiguous`; require analyst selection, save the selection and audit it.
- Never label a probabilistic candidate as confirmed without user confirmation.

Voice/Telugu/Hindi/English parsing is a later input adapter. The core case service receives a validated structured complaint and remains deterministic.

### 6.3 Queue ordering

Queue API ordering is elapsed time since fraud/report (as defined by the requirement), not amount. Include report timestamp, elapsed seconds, latest trace timestamp, reachable share where a current trace exists, assigned user, and status. The UI computes a live elapsed clock from a server timestamp; backend sends UTC times and server-generated `as_of` time to avoid skew.

---

## 7. Feature engine and scoring

### 7.1 Feature computation

Compute account features over configurable 1h, 24h, 7d, and 30d windows, including the approved features from requirements/handoff: in/out counts and values, pass-through ratio, median hold seconds, distinct counterparties, concentration/Herfindahl, burstiness, baseline shift using median/MAD, cycle participation, new-counterparty rate, and night share.

Each feature record contains value, window, source transaction IDs, feature version, coverage/missing reason, and benign look-alike explanation where required. Missing is unknown, never zero/low risk. Account age alone and geographic/location attributes are prohibited scoring features.

### 7.2 Label isolation and evaluation

- Store AML labels in a separate schema/table accessible only to evaluation jobs.
- Feature builder receives a ledger-only repository interface with no label dependency.
- Add static/import boundary and integration tests proving feature construction cannot query labels.
- Split AMLworld train/test by network/scenario, never random transaction rows.
- Detection metrics: precision, recall, PR-AUC, false-positive rate on IBM AMLworld; report dataset variant and split.
- Trace/path recovery and traced-value error: own seeded generator only, with ground truth separated from the engine input.
- Never average detection and trace metrics or describe generator metrics as independent detection performance.

### 7.3 Logistic model and score config

Use logistic regression. Train weights from labeled benchmark data and version the model artifact and feature registry. A score response must expose at least:

- component name;
- observed value;
- window;
- threshold;
- point contribution;
- evidence transaction IDs;
- missing/coverage state;
- benign explanation;
- model/config version;
- lead-for-review framing.

An admin can edit a candidate score configuration, run validation/evaluation, then publish it as a new immutable version. Prior cases retain the version used. No hand-picked model weights may be presented as learned results. Until a model has been trained and benchmarked, disable or mark scores “not evaluated”; never fabricate demo values.

---

## 8. Cases, recommendations, separation of duties, and exports

### 8.1 Case lifecycle

`new complaint → assigned → trace run → analyst review/notes → recommendation draft (optional) → independent supervisor decision → case disposition → export/close`

Persist each state transition, actor, timestamp, reason, and evidence snapshot. Re-running a trace creates a new trace result/version; it does not mutate the prior trace or prior decision snapshot.

### 8.2 Draft and independent approval

- Analyst selects account(s), supported amount(s), evidence, and written justification.
- Amount may not exceed the freezable estimate when a balance is available. If balance is unknown, the UI/API must not silently treat upper-bound unmoved value as a confirmed freeze amount; require a clearly labelled recommendation basis and policy validation.
- Supervisor approval/rejection requires a written reason.
- Author and approver must be different users. Enforce `drafted_by_user_id <> decided_by_user_id` using a PostgreSQL check constraint and validate supervisor role server-side. Add a DB trigger/controlled stored procedure if needed to prevent direct writes bypassing service checks.
- Admin cannot approve a freeze recommendation on a case for which that admin ingested the relevant data, per role rules.
- Approval creates a signed/hashed exportable recommendation document only.
- The recommendation service must not have an HTTP client, network egress configuration, or integration secret.
- Record reported outcome afterward as user-entered information; it does not trigger any external action.

### 8.3 Evidence snapshots and exports

At draft, approval, rejection, and close, snapshot the exact trace result, parameters, rule, dataset version/checksum, evidence transaction references, score/model version where relevant, written reasons, actor IDs, and timestamp. Hash canonical JSON with a stable canonicalization scheme; include the hash and exporter identity in PDF and JSON export.

Export case pack:

- machine-readable JSON bundle with schema version and content hash;
- PDF with case summary, source data/trace version, money decomposition, boundary reasons, account evidence, score explanations if present, approvals, and full caveats;
- export audit event and actor/time;
- re-import/verification command that checks bundle hash and reproduces stored trace from embedded permitted evidence or stored result snapshot.

---

## 9. Authentication, authorization, audit, and privacy

### 9.1 Authentication

Support institution OIDC/SAML integration as deployment mode. For pilot/demo fallback, admin-created users use Argon2id password hashes and mandatory TOTP. Access JWTs are short-lived; refresh token rotation is single-use with server-side revocation. Store only refresh token hashes. Apply rate limits to login, refresh, complaint intake, and expensive trace submissions. Use TLS in all environments; Docker Compose local mode should use a local reverse proxy/certificate configuration rather than teaching plaintext defaults.

### 9.2 Roles and endpoint permissions

- Analyst: create/assign complaint as allowed, run/read trace, read pseudonymous accounts, note, draft recommendation, close benign.
- Supervisor: analyst permissions plus approve/reject and reassign.
- Admin: users, ingestion, score config publication, retention/health; constrained from approving on self-ingested case.
- Auditor: read-only case/trace/score/audit and export audit reports.

Every route declares an explicit permission. CI enumerates routes and fails if one has none. Authorization is server-side in FastAPI dependencies and rechecked in service functions for sensitive use cases.

### 9.3 Append-only hash-chained audit

Audit every account read, identity resolution, dataset ingest/delete, complaint match/assignment, trace run/replay, score publication, recommendation draft/decision, case action, export, retention job, and admin permission change. Each event includes actor, role snapshot, target, case/dataset context, UTC time, request ID, reason when required, and redacted metadata.

- Use a DB role that can insert/select but cannot update/delete `audit.audit_events`.
- Add DB triggers to reject mutation as defense in depth.
- Serialize chain append per institution with a transaction/advisory lock; calculate `event_hash = hash(previous_hash || canonical_event_payload)`.
- Provide a verification command and API report for chain integrity.
- Do not include passwords, tokens, raw PII, or full account identifiers in logs/audit metadata.

### 9.4 PII boundary

Analysis store uses pseudonymous IDs. If a PII vault is needed, put mapping in a separate `vault` schema with separate encryption key, repository, DB role, and permission (`pii:resolve`). Resolution requires a case and reason, is audited, and is never called implicitly from the trace engine. If no vault is implemented for the prototype, do not add identity fields to `core`/`app` tables.

---

## 10. Versioned API contract for the sample client

All paths are under `/api/v1`. Publish OpenAPI from FastAPI and use it as the only frontend/backend contract. Response bodies include `request_id`; error bodies use a stable code, safe message, and field errors without PII.

### 10.1 Authentication and current user

- `POST /api/v1/auth/login` (fallback auth mode only)
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- OIDC login/callback routes when configured

### 10.2 Datasets and ingestion

- `POST /api/v1/datasets/uploads` → create upload manifest and return bounded/multipart upload instructions.
- `POST /api/v1/datasets/uploads/{upload_id}/complete` → verify object checksum/size and enqueue parse.
- `GET /api/v1/datasets/uploads/{upload_id}` → status/progress/error report.
- `POST /api/v1/datasets/uploads/{upload_id}/validate` → finalize validation policy (`reject_batch` or `quarantine_bad_rows`).
- `GET /api/v1/datasets/{dataset_id}` and `GET /api/v1/datasets/{dataset_id}/report`.
- `POST /api/v1/datasets/synthetic` → generate deterministic dataset from scenario and seed.
- `DELETE /api/v1/datasets/{dataset_id}` → authorized async deletion with dry-run option; preserve snapshots/audit and stale dependent traces.

Use MinIO multipart or streamed upload; do not accept a 2 GB file into one in-memory FastAPI request body. Progress API exposes bytes received, rows read, valid/invalid/duplicate counts, and current phase.

### 10.3 Complaints, queue, and cases

- `POST /api/v1/complaints` → structured complaint creation and transaction resolution.
- `GET /api/v1/complaints/{id}`; `GET /api/v1/complaints?sort=elapsed`.
- `POST /api/v1/complaints/{id}/assign` with target analyst and reason.
- `POST /api/v1/complaints/{id}/link` to link related complaints.
- `POST /api/v1/cases` or create case from complaint; `GET /api/v1/cases/{id}`.
- `POST /api/v1/cases/{id}/notes`; disposition and close endpoints with permission checks.

### 10.4 Trace and account evidence

- `POST /api/v1/complaints/{id}/traces` with rule ID and bounded parameters; refuse unresolved/ambiguous complaint without explicit selection.
- `POST /api/v1/traces/{trace_id}/rerun` with parameter changes; creates a new immutable run.
- `POST /api/v1/traces/{trace_id}/from-account` for re-trace from an account in that result.
- `GET /api/v1/traces/{trace_id}` returns stored canonical result, status, provenance, amounts, confidence, bounds, and termination reasons.
- `GET /api/v1/traces/{trace_id}/progress` returns job stage/hop progress and cancelability.
- `GET /api/v1/accounts/{account_id}?case_id=...` and `GET /api/v1/accounts/{account_id}/transactions` return role-filtered evidence and score explanation.
- `GET /api/v1/transactions/{transaction_id}` returns authorized transaction details and attribution evidence.

The trace API returns enough data to construct graph, timeline, table, and optional geographic view from the same result. Include observed transaction edges only; include coordinates/jurisdiction only when explicitly sourced and authorized.

### 10.5 Scores and evaluation

- `GET /api/v1/accounts/{id}/score?case_id=...`
- `GET /api/v1/admin/score-configs` and candidate create/update/validate/publish endpoints.
- `POST /api/v1/admin/evaluations` → background job.
- `GET /api/v1/admin/evaluations/{id}` → metrics, dataset, split, model/config version, and report artifact.
- `POST /api/v1/scores/{score_id}/disagreement` → analyst feedback with reason; audited.

### 10.6 Recommendation and export

- `POST /api/v1/cases/{case_id}/recommendations` → analyst draft.
- `GET /api/v1/recommendations?status=pending` for authorized supervisor.
- `POST /api/v1/recommendations/{id}/decision` → approve/reject with required reason; enforce independent approver.
- `GET /api/v1/recommendations/{id}/document` → generated artifact only after approval.
- `POST /api/v1/recommendations/{id}/outcome` → record reported outcome.
- `POST /api/v1/cases/{id}/exports` and `GET /api/v1/exports/{id}`.
- `GET /api/v1/audit/events` and export endpoint, auditor/admin permission only.

No endpoint name, client, or response should imply that approval calls an external freeze API.

### 10.7 Job behavior and errors

Ingestion, evaluation, exports, retention, and traces that may exceed the request budget run as jobs. Return `202 Accepted` with `job_id`, `status_url`, and `request_id`. Polling is sufficient for the prototype; add SSE only if a real UI need exists and it does not expand critical path.

Stable error codes include `DATASET_INVALID`, `UPLOAD_CHECKSUM_MISMATCH`, `COMPLAINT_UNRESOLVED`, `COMPLAINT_AMBIGUOUS`, `TRACE_BOUND_REACHED`, `TRACE_STALE`, `PERMISSION_DENIED`, `SELF_APPROVAL_FORBIDDEN`, `VALIDATION_ERROR`, `DEPENDENCY_UNAVAILABLE`, and `RATE_LIMITED`.

---

## 11. Milestone implementation plan

Milestones have exit checks. The trace engine is the critical path. Do not start scoring or UI polish before the core trace invariants and canonical API shape are stable.

### M0 — Repository, Compose, CI, and contracts

**Work**

- Create backend project skeleton and pinned Python/toolchain configuration.
- Add Compose services: API, worker, PostgreSQL, Redis, MinIO.
- Add liveness/readiness endpoints, structured JSON logging, request IDs, environment settings, and secret handling.
- Add first Alembic migration with three schemas and a seed admin/demo configuration.
- Publish initial OpenAPI tags and error envelope.
- Add import-linter rule protecting `engine/`.

**Exit**

- One-command local bring-up on clean machine.
- Migration applies from empty database; API/worker report healthy; object upload smoke test succeeds.
- CI runs format/lint/type-check/unit tests/import boundary/security scan.

### M1 — Ledger model, synthetic generator, and ingestion staging

**Work**

- Implement account/transaction/dataset contracts and monthly partitions.
- Implement deterministic seeded generator with normal behavior, typology patterns, and separate ground-truth labels.
- Implement CSV/JSONL streaming parsers, row validation, timezone normalization, checksums, row errors, staging, reject/quarantine policy, dedup registry.
- Add import job state/progress and retry-safe commit.

**Exit**

- Same scenario seed produces byte-identical ledger and ground truth.
- Loading a file twice creates no duplicate transaction IDs.
- Invalid rows produce field-specific reports; reject mode leaves committed ledger unchanged; quarantine mode commits only valid rows.
- Dataset manifest carries uploader, source, checksum, counts, and range.

### M2 — Indexed bulk transaction repository

**Work**

- Add required partial source/time index, destination/time index, dataset/time index, and query-plan checks.
- Implement batched outgoing and inflow queries for a whole frontier.
- Add benchmark scripts at Tier 1; verify no per-account query loop.
- Record hardware/dataset/query plan in benchmark report.

**Exit**

- Indexed retrieval matches brute-force scan on fixtures.
- One frontier hop uses a fixed small number of SQL queries, independent of number of accounts in the frontier.
- Initial measurements are reported honestly; no unmeasured latency claim.

### M3 — Pure trace engine (**critical path**)

**Work**

- Implement proportional pooled-inflow strategy, shared sibling budget, causal timestamps, exact paise rounding/residue, branch lineage, confidence, boundary termination, and bounds.
- Add the golden worked-example fixture and pure engine contract.
- Add property-based graph generation and deterministic canonical serialization.
- Add result types for nodes, edges, boundary endpoints, stopping reason, trace parameters, values, and provenance.

**Exit**

- Golden fixture matches ₹40,000 to B, ₹12,000 to C, ₹48,000 unmoved at A.
- Property tests pass across 10,000 generated graphs for no amplification, conservation, causality, confidence, boundaries, and determinism.
- Engine imports none of API/DB/services and has no network-capable dependency.

### M4 — Trace orchestration and complaints

**Work**

- Implement complaint intake, exact transaction resolution, ambiguous/unresolved states, queue ordering, assignment, case creation, trace submission and persisted replay.
- Implement Celery job lifecycle/progress/cancel for long traces; enforce request-duration threshold.
- Persist trace parameters, dataset version/hash, rule/engine version, canonical result and status.
- Implement retrace-from-account and immutable rerun behavior.

**Exit**

- Unresolved complaint cannot start a trace; ambiguous match requires explicit selection.
- Rerunning saved parameters against the same dataset version is byte-identical.
- Trace graph/timeline/table consumers can use the same API result object.
- Bound reasons are surfaced distinctly from natural endpoint reasons.

### M5 — Auth, RBAC, sessions, and audit

**Work**

- Implement OIDC configuration and fallback Argon2id + mandatory TOTP.
- Implement short-lived access tokens, refresh rotation, revocation, user/role administration, endpoint permission registry, IP allowlist configuration, and rate limits.
- Implement append-only hash-chained audit writer, DB immutability protections, redaction, and verification command.
- Add route-permission enumeration and role matrix tests.

**Exit**

- Every route declares a permission; Analyst/Supervisor/Admin/Auditor behavior matches the role matrix.
- Audit chain verifies; direct UPDATE/DELETE is rejected.
- Logs and error responses do not expose seeded PII/account identifiers.
- TLS is configured for local deployment and on-prem production profile.

### M6 — Evidence, accounts, scores, and evaluation

**Work**

- Implement balance completeness rules, four separate money values, freezable estimate, account transactions, feature windows, feature registry, model config/version, score explanations, and evaluation jobs.
- Integrate AMLworld data only for detection benchmark and own generator only for trace/path metrics.
- Isolate label access and publish metrics with dataset/split/model version.
- Add candidate score config validate/publish flow.

**Exit**

- Feature builder cannot access labels and forbidden features are absent.
- Missing features remain unknown with coverage.
- Score response includes observed value/window/threshold/contribution/evidence/benign explanation/model version.
- No performance/model numbers appear until an actual benchmark artifact is generated.

### M7 — Cases, recommendations, approvals, and exports

**Work**

- Implement evidence snapshot lifecycle, notes/disposition, recommendation drafts, independent approval/rejection, outcomes, PDF/JSON export, hashes, export provenance, and re-import/verify.
- Add DB constraint and test for different author/approver; ensure supervisor role and admin self-ingest restriction.
- Add static/no-network test for recommendation/freeze service.

**Exit**

- Two-user workflow passes end to end; self-approval fails at database level.
- Approval creates document only; there is no outbound HTTP client or action.
- Export re-verifies hash and reproduces trace from saved version/evidence.

### M8 — Retention, health, operations, and benchmark baseline

**Work**

- Implement deletion dry run, dataset deletion job, retention/anonymization, stale trace invalidation, snapshot preservation, and audit retention boundary.
- Add Prometheus metrics, readiness/liveness, queue-depth, job failure, trace latency, ingestion metrics, and structured logs.
- Add nightly PostgreSQL backup and documented restore rehearsal.
- Run Tier 1 and Tier 2 benchmarks on available hardware and commit actual report/budgets.
- Load test 10 concurrent analysts.

**Exit**

- Failed ingest leaves ledger in pre-job state.
- Deletion dry run and execution match; evidence snapshots/audit survive per policy; dependent traces become stale.
- Restore is exercised end to end.
- NFR performance budgets are based on measured results, not initial working targets.

### M9 — API stabilization and handoff to frontend agent

**Work**

- Freeze `/api/v1` OpenAPI schemas for queue, complaints, trace result, account/transaction detail, recommendation, review, cases, exports, and health.
- Add contract fixtures for the deterministic demo scenario.
- Document auth for local demo, synthetic data reset, API errors, role setup, and endpoints.

**Exit**

- Sample UI can walk complaint → trace → selected account evidence → draft → separate supervisor approval → export using API only.
- No frontend implementation is included in this backend assignment.

---

## 12. Hackathon prioritization and cut line

The full v1 requirements exceed a safe 36-hour implementation window. Preserve a complete workflow and explicitly stage breadth. Do not call the hackathon slice a production bank deployment.

### Must complete for the stage demo

1. Compose/API/DB/worker startup and versioned schema.
2. Deterministic synthetic ledger and one transaction-file ingest path (or preloaded fixture plus working upload if time permits).
3. Complaint intake and exact transaction resolution.
4. Pure trace engine with shared budget and golden/property invariants.
5. Persisted trace output and API for graph/timeline/table data.
6. Trace boundaries, confidence, separate money values, balance-unknown behavior.
7. Case record and evidence snapshot.
8. Draft recommendation and independent approval workflow with DB self-approval guard.
9. JSON export with content hash; PDF if available without destabilizing core flow.
10. Honest sample dataset labels and no fabricated score/performance metrics.

### Defer until after core workflow is solid

- OIDC/SAML deployment integration and polished account administration; use seeded demo users with the same server-side RBAC rules for the prototype.
- Full 2 GB ingestion, watched folder scheduler, and object-storage-prefix polling.
- Trained logistic model and full AMLworld evaluation if dataset preparation consumes the trace-critical path. In that case return “score not evaluated,” never demo fake scores.
- PDF export if it threatens deterministic JSON export and approval integrity.
- PII vault; keep data pseudonymous.
- Voice complaint parser, screenshot OCR, analyst disagreement feedback loop, boundary-response resume, and cross-bank integration.
- Tier 2/3 performance claims until measured.

The cut line never removes conservation, shared sibling budget, causality, explicit boundary termination, no-autofreeze, second approver, or dataset/metric honesty.

---

## 13. Testing and verification plan

The plan includes tests because they are the evidence that the backend meets the required safety and correctness properties. Do not treat a green UI walkthrough as a substitute for engine/database tests.

### 13.1 Unit tests

- Money decimal normalization, paise rounding, and residual allocation.
- Attribution strategy with zero pool, zero remaining, full and partial fractions.
- Balance completeness and freezable estimate.
- Complaint exact/ambiguous/unresolved transaction matching.
- Feature missingness/coverage and forbidden feature registry.
- Canonical result serializer and stable sort order.
- Trace bound and terminal reason mapping.
- Permission policy and stable API error contracts.

### 13.2 Property tests

At least 10,000 generated graphs for trace invariants in §5.7. Add generators with simultaneous timestamps, late-arriving credits, multiple siblings, merged branches, cycles, self-transfers if accepted by schema, reversed/pending rows, partition boundary timestamps, boundary hops, and values near one paise.

### 13.3 Integration tests

- Ingest same file twice; assert zero duplicate rows on second import.
- Reject whole batch vs quarantine behavior.
- Failure injection mid-commit; assert rollback.
- Complaint creation and queue elapsed sorting.
- Trace save/replay and stale trace after dataset change/deletion.
- Two-user recommendation flow with self-approval rejection.
- Database-level audit immutability and hash-chain verification.
- PII permission boundary and audit event on resolution.
- Case export hash and JSON re-import verification.
- Retention preserves evidence/audit and invalidates dependent traces.
- Every endpoint role matrix and route permission declaration.

### 13.4 Performance and operations

- Benchmark scripts for Tier 1 and Tier 2, with hardware/model/dataset details and p50/p95 for trace, account detail, queue listing, ingest rate, graph-result size/serialization.
- Query count assertion: a hop query count does not grow with frontier account count.
- 10 concurrent analyst load script.
- API request >30s is converted to a job with progress endpoint.
- Backup/restore rehearsal, dependency-down readiness checks, worker restart recovery, retry idempotency.

### 13.5 CI gates

- Formatting/linting and Python type check; no type ignores in `engine/`.
- Import-linter architecture rules.
- Unit, property, integration, and API contract tests.
- Dependency vulnerability scan; fail on high severity per NFR.
- Requirement-to-test coverage report; no unaccounted critical safety requirement.
- No-autofreeze static check and route-permission completeness.

---

## 14. Operational and deployment requirements

- One-command local Compose bring-up with seeded synthetic data and documented demo users.
- Separate configuration profiles for local development and on-prem deployment; no secrets in source control.
- TLS enabled in all profiles, including local defaults through documented local certificates/reverse proxy.
- Database migration command and rollback policy; never hand-run schema SQL in deployment.
- Health endpoints: `/health/live` tests process liveness; `/health/ready` checks PostgreSQL, Redis/worker readiness, and MinIO when required.
- Structured JSON logs with request ID, job ID, case ID where permitted, and redacted account/PII values.
- Prometheus metrics for API latency/error, queue depth, ingest rows/sec, trace duration/edge count, worker retries/failures, and export failures.
- Nightly database backup; retention and restore runbook; test restore before claiming recovery readiness.
- Restart recovery: pending jobs are retried or marked recoverable; analysis service resumes serving within stated NFR after measurement.
- IP allowlist and institution identity provider configuration for on-prem deployment.

---

## 15. Open decisions and explicit defaults

The implementing agent should not pause for these unless a source file contradicts the defaults:

1. **Repository location:** no TRACE-X source-code repository was present in `D:\AmbiFlow` during inspection; create a backend repository/project skeleton where the team has designated the code workspace. Do not put generated source into the docs folder without checking with the team.
2. **Requirements4 precedence:** Requirements4 is the latest source. Keep its IDs and wording; use Requirements3 only where the two versions agree. Record any future delta before changing engine invariants.
3. **Prototype auth:** seed demo analyst/supervisor/admin/auditor accounts with Argon2id/TOTP-ready auth and real role checks; do not bypass authorization for demo convenience.
4. **Dataset upload:** implement MinIO multipart object upload; use a local watched directory as an optional adapter. Avoid large request-body buffering.
5. **Trace jobs:** use synchronous service execution for small demo traces only if it stays within request budget; otherwise same endpoint returns job resource. Persist canonical result either way.
6. **Unresolved complaint parser:** structured API intake is v1; natural-language parser remains a separate adapter and must ask for human confirmation of parsed fields.
7. **Boundary continuation:** not in v1. Persist endpoint reason and evidence needed; do not simulate an inter-bank response.
8. **PDF:** JSON bundle is the mandatory export; PDF is added after the workflow is stable.

---

## 16. Definition of backend handoff complete

The backend is ready for the frontend agent when:

- Compose services start from a clean machine and migrations apply.
- The synthetic fixture and ingest endpoint populate the ledger deterministically.
- The golden trace and property tests pass with the single shared sibling budget.
- Complaint resolution, tracing, accounts, boundaries, confidence, bounds, cases, and evidence snapshots are represented in the stable `/api/v1` contract.
- Recommendation draft and independent supervisor approval work through the API and database constraint; approval only creates an export document.
- The JSON case pack can be exported, hashed, and verified.
- Audit events are append-only and verifiable; role checks are server-side.
- OpenAPI and seed data are documented for the frontend agent.
- No fabricated model/performance metrics are present.
- Remaining unimplemented requirements are listed with IDs, reason, owner/phase, and test needed.

---

## 17. Source references

- `D:\Downloads\TRACE-X_HANDOFF.md` — locked attribution algorithm, architecture stack, evaluation split, boundary behavior, stage workflow, and open items.
- `D:\AmbiFlow\Requirements4.md` — latest requirements source; 54 FRs, NFRs, safety/privacy rules, schemas, and test map.
- `D:\AmbiFlow\Requirements3.md` — available on-disk requirements copy used to verify the detailed backend requirements when this plan was prepared.

The frontend/UI specification is intentionally not repeated here. This file gives the backend agent the service boundaries and API/data behavior needed to support that future UI without implementing it.
