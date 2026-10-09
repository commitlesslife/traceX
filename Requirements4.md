# TRACE-X — Requirements

Oct 8, 2026 · @Victor Isaac

TRACE-X traces a reported fraud forward through a transaction graph and tells an investigator which accounts still hold the victim's money, with evidence for every claim. This tab is the requirement spec; Architecture and Implementation Plan are the other two tabs.

## Scope and release boundary

TRACE-X v1 is a deployable single-institution system: a bank fraud-operations team or a police cyber cell runs it on their own data. It is not a demo harness with a scripted path.

The product boundary is this: an investigator receives a fraud report, traces where the money went, decides which accounts to recommend for freezing, and leaves behind a case file another person can audit.

### What makes this a product rather than a prototype

1. Real accounts and sessions. Named users, roles, password or OIDC login, session expiry.
2. Durable state. Every trace, case, note and decision is persisted and survives a restart.
3. Idempotent ingestion. The same file loaded twice produces no duplicate transactions.
4. Schema migrations. Database changes ship as versioned migrations, never hand-run SQL.
5. Audit trail. Every read of an account, every score change, every freeze recommendation is logged with actor and time.
6. Operability. Health checks, structured logs, metrics, backup and restore, one-command deploy.
7. Tests that gate merges. Unit, property and integration tests run in CI.
8. Performance budgets that are measured, not claimed.

### In and out of v1.0

| Area | In v1.0 | Out of v1.0 |
| --- | --- | --- |
| Data in | Batch CSV and JSON upload, scheduled directory pickup, generated datasets | Live bank core-banking integration, card networks |
| Analysis | Temporal graph, feature engine, forward tracing, account and network scoring | Graph neural networks, cross-institution federated analysis |
| Output | Ranked holdings, freeze recommendation drafts, case packs as PDF and JSON | Automatic freezing, automatic reporting to any authority |
| Identity | Pseudonymous account keys, optional separate PII vault | Customer identity resolution, beneficial-ownership graphs |
| Users | Analyst, supervisor, admin, auditor roles with RBAC | Multi-tenant SaaS with per-tenant isolation |
| Deploy | Docker Compose on one host, Postgres, Redis, object storage | Kubernetes, multi-region, high availability |

### Release ladder

| Release | Adds | Gate before starting |
| --- | --- | --- |
| v1.0 | Batch ingestion, tracing, scoring, cases, RBAC, audit | None, this is the build |
| v1.1 | Streaming ingestion, incremental graph updates, alert queue with SLA timers | v1.0 passing its performance budgets |
| v1.2 | Model retraining pipeline, score-config approval workflow, analyst feedback loop | 200 or more real cases closed in v1.1 |
| v2.0 | Cross-institution tracing with privacy-preserving joins | A signed data-sharing agreement and a legal review |

Anything not listed above is out of scope. A request to add scope mid-build goes to the backlog, not into the current milestone.

## Users, roles and permissions

Four roles, enforced server-side on every endpoint. A role is attached to a user account; permissions are never decided in the frontend.

| Role | Does | May not |
| --- | --- | --- |
| Analyst | Opens complaints, runs traces, reads accounts, drafts freeze recommendations, writes notes, closes cases as benign | Approve a freeze recommendation, change score config, delete a case, read the PII vault |
| Supervisor | Everything an analyst does, plus approves or rejects freeze recommendations and reassigns cases | Change score config, delete audit records |
| Admin | Manages users, ingests datasets, publishes a score configuration version, manages retention jobs | Approve a freeze recommendation on a case they ingested data for, delete audit records |
| Auditor | Reads every case, trace, score explanation and audit record, exports audit reports | Write anything at all |

### Separation-of-duty rules

1. The analyst who drafts a freeze recommendation cannot approve it. Approval requires a second user with the supervisor role.
2. No role can delete or edit an audit record. The audit table is append-only at the database level.
3. An admin can publish a score configuration but cannot alter a case outcome that used an earlier version.
4. Account identifiers shown to analysts are pseudonymous. Resolving a pseudonym to a customer identity is a separate, separately permissioned action that is always logged.

### Primary workflows by role

| Workflow | Owner | Trigger | Ends when |
| --- | --- | --- | --- |
| Triage a new complaint | Analyst | Complaint arrives or is entered | Trace run and holdings reviewed |
| Draft freeze recommendation | Analyst | Holdings show recoverable funds | Draft submitted for approval |
| Approve or reject | Supervisor | Draft submitted | Decision recorded with a written reason |
| Close a case | Analyst or supervisor | Investigation finished | Disposition and evidence snapshot saved |
| Ingest a dataset | Admin | New file or scheduled pickup | Validation report accepted, analysis run queued |
| Publish score config | Admin | Model or thresholds changed | New version active, old version retained |
| Audit review | Auditor | On demand or periodic | Export generated |

## Functional requirements

Every requirement below is testable. The implementation plan maps each one to a milestone and an automated test.

### Ingestion and data management

| ID | Requirement |
| --- | --- |
| FR-01 | Upload a transaction file as CSV or JSON Lines, up to 2 GB, with a progress indicator |
| FR-02 | Validate every row against the schema and return a per-row error report naming the field and reason |
| FR-03 | Reject the whole batch or quarantine bad rows, chosen by the admin at upload time |
| FR-04 | Deduplicate by transaction identifier; re-uploading the same file adds nothing |
| FR-05 | Normalise all timestamps to UTC and store the original offset |
| FR-06 | Record a dataset record with source, row counts, time range, checksum and uploader |
| FR-07 | Pick up files automatically from a watched directory or object-storage prefix |
| FR-08 | Generate a synthetic dataset from a named seed and a scenario configuration |
| FR-09 | Delete a dataset and everything derived from it, logged, in one operation |

### Complaints and case intake

| ID | Requirement |
| --- | --- |
| FR-10 | Record a complaint with victim account, disputed transaction, amount, reported time and channel |
| FR-11 | Accept complaints through the API so an upstream reporting system can push them |
| FR-12 | Show a queue ordered by time elapsed since the fraud, with the elapsed clock visible per row |
| FR-13 | Assign a complaint to an analyst, and reassign with a reason |
| FR-14 | Link several complaints that share accounts into one investigation |

### Tracing

| ID | Requirement |
| --- | --- |
| FR-15 | Trace forward from a seed transaction, following only transfers that occur after funds arrive |
| FR-16 | Apply a chosen attribution rule and show which rule produced the result |
| FR-17 | Implement one attribution rule completely, with its assumptions and amount limits shown beside every result; further rules are optional and must be labelled |
| FR-18 | Never attribute more money out of an account than the traced amount that entered it |
| FR-19 | Report four separate quantities per account, never collapsed into one number: traced in, traced out, unmoved traced value, and available balance |
| FR-20 | Bound every trace by maximum hops, time horizon and work budget, and report when a bound stopped the search |
| FR-21 | Let the analyst re-run a trace from any account in the result |
| FR-22 | Persist every trace with its parameters so the same result can be reproduced later |
| FR-23 | Show the trace as a graph, as a timeline and as a table, from the same stored result |

### Unmoved value and the institutional boundary

A transaction ledger alone cannot state what remains in an account. These requirements keep the distinction visible rather than hiding it behind one confident figure.

| ID | Requirement |
| --- | --- |
| FR-47 | Define unmoved traced value as traced in minus traced out, and label it everywhere as an upper bound on what could remain |
| FR-48 | Show available balance only when the data supports it: an opening balance plus a complete transaction history for that account |
| FR-49 | When balance data is absent, display "balance unknown" rather than any rupee figure implying a known balance |
| FR-50 | Compute the freezable estimate as the lower of unmoved traced value and available balance, and show it only when both exist |
| FR-51 | Mark any hop whose destination is outside the operating institution as a terminal node labelled as requiring an inter-bank request, and never imply visibility past it |
| FR-52 | Report, per trace, how much of the seed amount left the institution and is therefore untraceable with this data |
| FR-53 | Carry a confidence per hop equal to the attributed fraction compounded along the path, and display it beside every amount |
| FR-54 | Resolve a reported transaction against the dataset at intake, returning a match confidence, and refuse to trace an unresolved reference |

### Scoring and explanation

| ID | Requirement |
| --- | --- |
| FR-24 | Compute account features over configurable rolling windows |
| FR-25 | Produce an account risk score from a versioned, published model configuration |
| FR-26 | Show every score component with its observed value, window, threshold and contribution |
| FR-27 | Link every component to the transaction identifiers that produced it |
| FR-28 | Mark missing features as unknown and show score coverage rather than treating missing as low risk |
| FR-29 | Show at least one benign explanation for each high-scoring pattern |
| FR-30 | Never display a score as a determination of guilt; scores rank review order only |

### Freeze recommendations

| ID | Requirement |
| --- | --- |
| FR-31 | Produce a list of accounts ranked by unmoved traced value, each row showing the freezable estimate and the confidence behind it |
| FR-32 | Let an analyst draft a freeze recommendation selecting accounts and amounts, with a written justification |
| FR-33 | Require approval by a different user with the supervisor role before a recommendation leaves draft |
| FR-34 | Generate a freeze request document containing the evidence, the amounts and the trace parameters |
| FR-35 | Record the outcome reported back for each recommendation |
| FR-36 | Never execute a freeze automatically or call any external system that would |

**The approval boundary, stated once and enforced in code.** Approving a recommendation authorises the generation of an exportable document and nothing else. It sends no instruction to any bank, triggers no external call, and changes no account. The freeze service has no outbound HTTP client, and a test asserts that it never acquires one.

### Cases, audit and export

| ID | Requirement |
| --- | --- |
| FR-37 | Create a case from a complaint, holding traces, accounts, notes, recommendations and disposition |
| FR-38 | Snapshot the evidence at the moment of each decision so later data changes cannot rewrite history |
| FR-39 | Export a case pack as PDF and as a JSON bundle with a content hash |
| FR-40 | Log every data access, analysis run, score publication and case action with actor, time and target |
| FR-41 | Let an auditor search and export the audit log by actor, case or time range |
| FR-42 | Apply a retention policy that deletes or anonymises data past its configured age |

### Administration

| ID | Requirement |
| --- | --- |
| FR-43 | Manage users, roles and session policy from an admin screen |
| FR-44 | Edit, test and publish a score configuration as a new version without editing code |
| FR-45 | Show system health: queue depth, last ingestion, graph build time, model version in use |
| FR-46 | Run and view an evaluation report of the current model against a labelled dataset |

## Non-functional requirements

These are budgets, not aspirations. Each one has a benchmark script in the repo and fails the build when breached.

### Performance, measured before it is promised

No latency or throughput figure is committed until it has been measured on the dataset and the machine the team actually has. Milestone MB produces the first benchmark report, and its numbers then become the budgets CI enforces.

| ID | Requirement |
| --- | --- |
| NFR-01 | Publish a benchmark report naming dataset size, hardware, and measured p50 and p95 for trace, account detail, queue listing, ingestion rate and graph load |
| NFR-02 | Once measured, each figure becomes a committed budget; CI fails a change that regresses it by more than 20 percent |
| NFR-03 | Re-run and re-publish the benchmark whenever the dataset tier or the engine changes |
| NFR-04 | No HTTP request runs longer than 30 seconds; anything slower becomes a background job with a progress endpoint |

Working targets for v1, held until the first benchmark replaces them with real numbers:

| Operation | Working target | Tier |
| --- | --- | --- |
| Trace, 6 hops, 72-hour horizon | under 2 seconds at p95 | Tier 2 |
| Account detail with score explanation | under 800 ms at p95 | Tier 2 |
| Complaint queue, 50 rows | under 500 ms at p95 | Tier 2 |
| Bulk ingestion | at least 5,000 transactions per second | Tier 2 |
| Graph view | interactive to 300 nodes, clustered beyond | Tier 2 |

### Scale, staged rather than promised

| ID | Requirement |
| --- | --- |
| NFR-05 | Tier 1, 500,000 transactions and 50,000 accounts, is the development and demo tier |
| NFR-06 | Tier 2, 5 million transactions and 500,000 accounts, is the benchmark tier where the working targets apply |
| NFR-07 | Tier 3, 50 million transactions and 5 million accounts, is v1.1 only, and only once the Tier 2 bottleneck is identified by measurement |
| NFR-08 | 10 concurrent analysts in v1, measured with a load script rather than estimated; 50 is a v1.1 goal |

High availability, multi-region deployment, streaming ingestion and sharding stay out of v1. They are added when a measured bottleneck justifies them, not before.

### Reliability and operations

| ID | Requirement |
| --- | --- |
| NFR-09 | The analysis service restarts and resumes serving within 10 minutes |
| NFR-10 | A failed ingestion job leaves the database in its pre-job state |
| NFR-11 | Liveness and readiness endpoints that reflect real dependency health |
| NFR-12 | Nightly database backup with a documented, tested restore procedure |
| NFR-13 | Structured JSON logs with a request identifier carried end to end |
| NFR-14 | Prometheus metrics for request latency, queue depth, trace duration and job failures |

### Security

| ID | Requirement |
| --- | --- |
| NFR-15 | All traffic over TLS; no plaintext transport in any environment including local defaults |
| NFR-16 | Passwords hashed with Argon2id; OIDC supported as an alternative |
| NFR-17 | Short-lived access tokens with refresh rotation and server-side revocation |
| NFR-18 | Authorisation checked server-side on every endpoint, tested per role |
| NFR-19 | Database encrypted at rest; any PII vault separately encrypted with its own key |
| NFR-20 | No secret in source control; configuration through environment or a secret store |
| NFR-21 | Rate limiting on authentication and on expensive trace endpoints |
| NFR-22 | Dependency vulnerability scan in CI, build fails on high severity |

### Quality and maintainability

| ID | Requirement |
| --- | --- |
| NFR-23 | Test coverage at least 80 percent on the analysis engine, including property-based tests of trace invariants |
| NFR-24 | Type checking passes with no ignores in the engine package |
| NFR-25 | All schema changes through migrations, reversible where possible |
| NFR-26 | API versioned under a path prefix; breaking changes require a new version |
| NFR-27 | One-command local bring-up with seeded data |

### Usability

| ID | Requirement |
| --- | --- |
| NFR-28 | A new analyst completes a first trace and case within 10 minutes using only in-app guidance |
| NFR-29 | Every screen that shows a score or a traced amount offers the explanation within one click |
| NFR-30 | Keyboard navigation and visible focus states across the investigation flow |
| NFR-31 | All times shown in the user's timezone with the UTC value available on hover |

## Data contract and evaluation datasets

One input contract serves every data source. A bank export, a generated dataset and a public benchmark all arrive as the same rows, so nothing downstream knows or cares which it is.

### Transaction schema

| Field | Type | Required | Rule |
| --- | --- | --- | --- |
| transaction\_id | string | Yes | Unique within the dataset, stable across reloads |
| source\_account | string | Yes | Pseudonymous key, never a customer name |
| destination\_account | string | Yes | Pseudonymous key |
| amount | decimal(18,2) | Yes | Greater than zero |
| currency | string | Yes | ISO 4217; v1.0 accepts INR only and rejects the rest |
| timestamp | ISO 8601 with offset | Yes | Stored as UTC plus the original offset |
| status | enum | Yes | completed, reversed or pending; only completed is analysed |
| channel | string | No | upi, imps, neft, rtgs, card, atm, internal |
| source\_bank | string | No | Institution code, used for cross-bank display |
| destination\_bank | string | No | Institution code |
| balance\_after\_source | decimal | No | Enables the lowest-intermediate-balance rule when present |
| dataset\_label | string | No | Evaluation only; excluded from every feature by a hard check |

### Account schema

| Field | Type | Required | Rule |
| --- | --- | --- | --- |
| account\_id | string | Yes | Matches the transaction keys |
| opening\_balance | decimal | No | With a complete transaction history, this is what makes available balance computable; without it, only unmoved traced value can be shown |
| opening\_balance\_at | timestamp | No | Required whenever opening\_balance is present |
| history\_complete | boolean | No | Asserts that every transaction for this account is in the dataset; available balance is computed only when true |
| opened\_at | date | No | Absent means unknown, never new |
| account\_type | enum | No | individual, merchant, corporate, government |
| institution | string | No | Institution code; an account whose institution differs from the operating one is a boundary account |
| kyc\_level | enum | No | full, minimum, unknown |

### Complaint schema

| Field | Type | Required |
| --- | --- | --- |
| complaint\_id | string | Yes |
| victim\_account | string | Yes |
| disputed\_transaction\_id | string | Yes |
| disputed\_amount | decimal | Yes |
| fraud\_time | timestamp | Yes |
| reported\_time | timestamp | Yes |
| fraud\_type | enum | No |

### The three datasets, and what each is for

| Dataset | Purpose | What it can honestly measure |
| --- | --- | --- |
| IBM AMLworld, the LI-Small or HI-Small variant | Independent detection benchmark | Precision, recall and PR-AUC for suspicious-account ranking |
| Own generator | Development, demos, load testing, and tracing correctness | Path recovery and traced-value accuracy, because ground truth exists by construction |
| Authorised institution data | Pilot deployment only | Nothing is published from it without written permission |

**Why the benchmark is still synthetic, and why that is fine.** Real transaction data is almost never shareable at scale, and prior work notes there are no real public datasets for comparing anti-money-laundering methods in banks. Every usable public benchmark is therefore generated too. IBM's AMLworld datasets are the chosen one because they are independent of this team and carry complete labels for which transactions are laundering, in sizes from roughly 700,000 accounts and 7 million transactions upward. The point is not realism; it is that we did not design the patterns we claim to detect. SAML-D, with its 28 typologies, is the fallback if AMLworld proves hard to load.

**The evaluation splits in two, and each half is labelled.** Detection metrics come from AMLworld. Tracing metrics, meaning path recovery and how closely unmoved traced value matches the truth, can only come from the generator, because no public dataset labels where a victim's money ended up. Saying this plainly is stronger than blurring it: it shows you know what each number is worth.

The generator must produce normal behaviour that is genuinely varied: salaried accounts, merchants with high fan-in, payroll accounts with high fan-out, remittance patterns, dormant accounts and bursty small businesses. It then injects collection, pass-through, fan-out, cyclical, split-and-merge and behaviour-shift patterns, each with a scenario identifier kept in a separate ground-truth file.

### Hard rules on labels

1. Labels live in a separate table, never in the feature table.
2. A unit test asserts that no feature column name appears in the label table and that the feature builder cannot read it.
3. Accuracy figures quoted anywhere in the product or the pitch come from the public benchmark, never from the generator.
4. Train and test split by scenario or by network, never by random transaction rows, because rows from one network leak into both halves otherwise.

## Compliance, safety and acceptance criteria

### Regulatory context

India's framework shapes several requirements. None of this is legal advice, and a real deployment needs counsel.

| Context | What it means for the build |
| --- | --- |
| Digital Personal Data Protection Act, 2023 | Purpose limitation, data minimisation, retention limits, security safeguards, breach reporting |
| Prevention of Money Laundering Act | Mule accounts and the proceeds of fraud sit in a regulated reporting regime; the product supports reporting, never replaces it |
| RBI expectations on fraud risk management | Fraud decisions affecting a customer require governance and a documented human process |
| National cybercrime reporting and the 1930 helpline | The complaint intake schema is designed so an upstream reporting system can push complaints in |

### Safety requirements

| ID | Requirement |
| --- | --- |
| SR-01 | The system never freezes, blocks, reports or restricts an account by itself |
| SR-02 | Every output that names an account is labelled as a lead for review |
| SR-03 | Attributes with discrimination risk, including location, account age alone and demographic proxies, are never scoring features |
| SR-04 | Every freeze recommendation requires a written justification and a second approver |
| SR-05 | Traced amounts are shown as an upper bound under a named attribution rule, never as proven ownership of funds |
| SR-06 | The interface shows at least one benign explanation alongside each flagged pattern |
| SR-07 | A false-positive rate is published in the product's own evaluation screen |
| SR-08 | Analysts can record disagreement with a score, and those records feed the evaluation report |

### Privacy requirements

| ID | Requirement |
| --- | --- |
| PR-01 | Account identifiers in the analysis store are pseudonymous |
| PR-02 | Any identity mapping lives in a separate schema with its own key and its own permission |
| PR-03 | Resolving a pseudonym is logged with actor, time, case and reason |
| PR-04 | Retention policy configurable per dataset, with automatic deletion or anonymisation |
| PR-05 | Export bundles carry a content hash and the identity of the exporter |
| PR-06 | No personal data in logs or error messages, enforced by a redaction filter |

### Deletion, retention and the audit boundary

Dataset deletion, retention limits, immutable audit records and frozen case evidence pull against each other. One rule settles it: **what was decided is kept, what it was decided from can go.**

| Object | On dataset deletion | On retention expiry | Ever deleted |
| --- | --- | --- | --- |
| Ledger rows | Deleted | Deleted or anonymised | Yes |
| Features and scores | Deleted | Deleted | Yes |
| Traces | Marked stale, parameters kept, edges deleted | Deleted with their case | With the case |
| Case evidence snapshots | Kept; the case is the record of a decision | Deleted when the case's own clock expires | With the case |
| Cases and freeze recommendations | Kept | Deleted at case retention age | With the case |
| Audit events | Kept | Kept for the audit retention period, which is longer | Only by a separate, logged purge |

1. Audit events store identifiers and actions, never payloads, so keeping them longer does not keep personal data longer.
2. Deleting a dataset marks every dependent trace stale rather than silently recomputing it. A stale trace renders with a banner and cannot back a new recommendation.
3. A legal hold blocks deletion for named cases. Placing and lifting a hold are themselves audited actions.
4. Deletion is a job with a dry-run mode that reports what would go, because an irreversible cascade needs a preview.

### Acceptance criteria for v1.0

The release is done when all of the following are true.

1. A fresh machine runs one command and reaches a working system with seeded data.
2. An analyst can log in, pick a complaint, trace it, view holdings, draft a freeze recommendation, and have a supervisor approve it, using only the UI.
3. All forty-six functional requirements have a passing automated test.
4. The benchmark has been run at Tier 2 and its measured figures, not the working targets, are recorded as the committed budgets in NFR-01 to NFR-08.
5. A role-permission test suite proves every endpoint rejects every role that should not reach it.
6. Property tests prove the trace conservation invariant on ten thousand generated cases.
7. An evaluation report against the public benchmark is generated, with precision, recall and the recovery-time curve.
8. A case pack exports as PDF and JSON, and the JSON re-imports to reproduce the same trace.
9. Backup and restore has been performed end to end and documented.
10. The audit log contains an entry for every action taken during a scripted acceptance walkthrough.

### Success metrics after deployment

| Metric | Target |
| --- | --- |
| Median time from complaint to freeze recommendation | Under 15 minutes |
| Share of traced funds still unmoved when the recommendation is raised | Reported weekly, trend upward |
| Analyst agreement with the top-ranked holdings | Above 70 percent |
| Cases closed benign after investigation | Tracked as the false-positive cost, trend downward |

## Interface and visualisation requirements

The interface is where this system's honesty becomes visible or gets lost. These requirements are as binding as the engine ones: a correct trace presented as a single confident number is a worse product than no trace at all.

### Screens

| Screen | Purpose | Must contain |
| --- | --- | --- |
| Queue | Where a shift starts | Complaints sorted by elapsed time, not amount; a live elapsed clock per row; a reachable-percentage bar per row; open count, value at risk, still reachable, median time to first trace |
| Investigation | Where the work happens | Trace controls, the money-flow canvas, a timeline, and the value panel |
| Account | Why this surfaced | Priority score, feature coverage, every component as a contribution bar with its benign explanation, counterparties, ledger |
| Case | The record | Action timeline, evidence snapshots, notes, disposition, export |
| Review | Supervisor approval | Pending recommendations with amounts and confidence, justification, approve and reject with a required reason |
| Admin | Operations and proof | Datasets with balance availability, model version, the evaluation report, system health |

### The money-flow canvas

This is the centrepiece and the thing judges and investigators will both touch first.

| ID | Requirement |
| --- | --- |
| UI-01 | Render the trace as a branching left-to-right flow, not a chain; a seed that splits three ways must read as three branches |
| UI-02 | Arrow thickness encodes the attributed amount, so the largest loss is legible before any number is read |
| UI-03 | Node fill encodes unmoved traced value, never risk score, because that is the actionable quantity |
| UI-04 | Accounts outside the operating institution render with a dashed outline, are labelled as leaving the institution, and cannot be expanded |
| UI-05 | Every node and every edge is clickable and opens a detail panel without navigating away |
| UI-06 | The detail panel shows transaction reference, channel, timestamp, attributed amount and confidence |
| UI-07 | Hovering an edge shows amount and time before any click, because users hover first |
| UI-08 | A replay control redraws the branches in timestamp order in roughly three seconds |
| UI-09 | Re-trace from any node is available directly on the node |
| UI-10 | Above 300 nodes the view collapses into clusters with counts, expandable on demand |
| UI-11 | Animated flow indicators show direction of movement without requiring a legend |
| UI-12 | A timeline beneath the canvas is bidirectionally linked: selecting a node highlights its hops and the reverse |

### Colour semantics

Colour carries one meaning only, and it is recoverability, not suspicion. A mule account holding reachable money is good news and must not be coloured as a threat.

| Colour | Meaning | Used for |
| --- | --- | --- |
| Green | Holds funds still reachable | Nodes with unmoved value, the reachable share, confident confidence values |
| Amber | Partly moved on, or an estimate under strain | Partial holdings, elapsed-time warnings, low coverage |
| Red | Beyond reach | Boundary nodes, cash withdrawals, the restored-to-victims figure |
| Grey | Pass-through, holds nothing | Accounts that retained nothing |
| Accent blue | The victim and the seed | Origin node, seed transaction |

Colour never carries meaning alone. Every coloured state also carries a text label, for accessibility and for printing.

### Charts the product must contain

| Chart | Where | Source |
| --- | --- | --- |
| Recovery by reporting delay | Admin evaluation screen and the pitch | Computed from traced complaints; measured points marked, interpolation marked as modelled |
| Reachable versus beyond reach | Investigation screen, as a split bar above the canvas | Current trace result |
| Score components | Account screen, one horizontal bar per component with points contributed | Score breakdown |
| Reachable percentage per complaint | Queue rows, inline mini bars | Latest trace per complaint |
| Detection metrics | Admin screen | Evaluation run against the benchmark |

### Display rules for money and uncertainty

| ID | Requirement |
| --- | --- |
| UI-13 | Unmoved traced value always carries a qualifier such as "up to"; it is never shown as a bare figure |
| UI-14 | An unknown balance renders as the words "balance unknown", never as zero, a dash, or an empty cell |
| UI-15 | The four quantities appear as four separate rows and are never summed into one headline figure |
| UI-16 | Confidence appears beside every attributed amount; rows below 0.2 render faded |
| UI-17 | A stale trace, whose underlying data changed, renders behind a banner and cannot back a new recommendation |
| UI-18 | When a bound stopped the search, a banner names which bound and offers to relax it |
| UI-19 | All amounts use tabular figures so columns of rupees align, with a consistent currency format |
| UI-20 | Every account-naming view carries a visible label that it is a lead for review |

### States, accessibility and feel

| ID | Requirement |
| --- | --- |
| UI-21 | Loading states are skeletons matching the final layout, never a full-page spinner |
| UI-22 | A long trace streams results with a hop counter and a cancel control |
| UI-23 | Empty states say what to do next rather than "no data" |
| UI-24 | Errors state what failed, what to try, and the request identifier to quote |
| UI-25 | Keyboard navigation and visible focus across the whole investigation flow |
| UI-26 | The canvas has a text-equivalent sortable table of hops, serving both accessibility and dense graphs |
| UI-27 | Dark interface by default, compact density, one type family, three sizes |
| UI-28 | Times display in the user's timezone with the UTC value on hover |

### Simulate mode, kept separate

| ID | Requirement |
| --- | --- |
| UI-29 | Simulate is a tab inside Investigation, never a separate product area, and is always labelled as a model |
| UI-30 | The variable the user controls is reporting delay, not the path the money took; letting a user draw the path and then tracing it proves nothing |
| UI-31 | The recovery curve redraws from measured behaviour in the loaded dataset, and the screen states which dataset |

### Design references produced so far

These were designed during planning and should be carried into the build rather than re-invented.

1. The six-screen walkthrough: queue with elapsed clocks, investigation workbench, account explanation with benign matches, supervisor review with the self-approval block, case record with action timeline, admin with datasets and metrics.
2. The interactive flow canvas: a three-way split across HDFC, a Paytm wallet and ICICI, terminating at an Axis mule account holding ₹1,80,000, an offshore exchange and an ATM withdrawal.
3. The stakes panel: taken versus still reachable as a split bar, hop arcs thinning with each transfer, and the recovery decay curve.
4. The pitch deck illustrations: the four-stage fraud story, and the list-versus-network contrast showing the same six transactions read two ways.

## Requirement-to-test map

Every critical workflow and every safety rule names the test that proves it. This map covers the workflows and safety rules, not all 54 functional requirements; the remainder are listed in the backlog table below and each must gain a test before its milestone closes.

### Workflow coverage

| Requirement | Verified by | Test location |
| --- | --- | --- |
| FR-01 to FR-04 ingestion and idempotency | Load a file twice, assert row counts unchanged; load a corrupt file, assert the per-row report | tests/integration/test\_ingestion.py |
| FR-10 to FR-14 complaint intake and queue | Create through the API, assert queue ordering by elapsed time, assert reassignment is audited | tests/integration/test\_complaints.py |
| FR-15 to FR-19 tracing correctness | Property tests for conservation, no amplification and causality over generated graphs | tests/property/test\_trace\_invariants.py |
| FR-20 bound reporting | Run with each bound deliberately tight, assert the correct bound name is returned and relaxing it adds edges | tests/unit/test\_trace\_bounds.py |
| FR-22 reproducibility | Re-run a stored trace from its saved parameters, assert byte-identical results | tests/integration/test\_trace\_replay.py |
| FR-24 to FR-30 scoring and explanation | Assert every score response carries all five explainability fields and that coverage is reported | tests/integration/test\_score\_contract.py |
| FR-31 to FR-35 freeze workflow | Walk draft, approve, reject and outcome through the API as two different users | tests/integration/test\_freeze\_workflow.py |
| FR-37 to FR-39 cases and export | Export a case pack, re-import the JSON, assert the trace reproduces | tests/integration/test\_case\_export.py |
| FR-40 to FR-41 audit | Perform a scripted walkthrough, assert one audit row per action with the right actor | tests/integration/test\_audit\_trail.py |
| Full workflow | Playwright script: complaint to approved recommendation entirely through the UI | frontend/e2e/investigation.spec.ts |

### Safety rule coverage

| Rule | Verified by | Test location |
| --- | --- | --- |
| SR-01 no automatic freezing | Static check: no code path calls an external system to restrict an account; a test asserts the freeze service has no outbound client | tests/unit/test\_no\_autonomous\_action.py |
| SR-03 no discriminatory features | Assert the feature registry contains no field from the forbidden list, including account age alone and location | tests/unit/test\_feature\_registry.py |
| SR-04 second approver required | Database constraint test: approving your own draft is rejected at the database level, not only in the service | tests/integration/test\_separation\_of\_duty.py |
| SR-05 traced amounts are bounded claims | Assert every trace response carries the rule name, its assumptions and the approximation flag | tests/unit/test\_trace\_response\_contract.py |
| SR-06 benign explanation shown | Assert every score component resolves to at least one benign explanation string | tests/unit/test\_benign\_explanations.py |
| PR-01 and PR-03 pseudonymity | Assert no analyst-facing response contains a vault field, and that any resolution writes an audit row | tests/integration/test\_pii\_boundary.py |
| Label hygiene | Assert the feature builder cannot import or query the label table | tests/unit/test\_label\_isolation.py |
| RBAC completeness | Enumerate every route, fail on any without a declared permission, then exercise the full role matrix | tests/integration/test\_permissions.py |

### Remaining requirements and their tests

These were uncovered when the map was first written. Each gains its test before its milestone closes.

| Requirement | Verified by | Test location |
| --- | --- | --- |
| FR-05 to FR-08 normalisation, dataset records, pickup, generation | Assert UTC conversion keeps the original offset; assert checksum uniqueness; assert two seeded generations match | tests/integration/test\_dataset\_lifecycle.py |
| FR-09 and FR-42 deletion and retention | Dry run reports the correct cascade; after deletion, case evidence and audit survive and dependent traces are stale | tests/integration/test\_deletion\_retention.py |
| FR-21 and FR-23 re-trace and multiple views | Re-trace from a mid-path account; assert graph, timeline and table render from one stored result | tests/integration/test\_trace\_views.py |
| FR-43 to FR-45 administration and health | Create a user and assert role takes effect; publish a config and assert old scores still resolve; assert health reflects a stopped dependency | tests/integration/test\_admin.py |
| FR-46 evaluation report | Run the report on a fixture and assert the metrics structure and the recovery curve are present | tests/integration/test\_evaluation\_report.py |
| FR-47 to FR-50 unmoved value and balance | Assert the four quantities are separate fields; assert "balance unknown" appears when balance data is missing; assert freezable estimate is the lower of the two | tests/unit/test\_value\_decomposition.py |
| FR-51 and FR-52 institutional boundary | Assert a hop to another institution terminates and is labelled; assert the trace reports value that left the institution | tests/unit/test\_boundary\_termination.py |
| FR-53 confidence | Assert confidence compounds along the path and never rises with depth | tests/property/test\_confidence.py |
| FR-54 complaint resolution | Assert an unresolved reference is refused with a clear message, not traced | tests/integration/test\_complaint\_resolution.py |
| SR-02, SR-07, SR-08 lead framing, published false positives, disagreement | Assert the lead label on every account-naming response; assert the evaluation screen publishes the false-positive rate; assert disagreement writes a record | tests/integration/test\_safety\_surface.py |
| PR-02, PR-04 to PR-06 vault, retention, export hash, log redaction | Assert vault access needs its own permission; assert export carries a hash and exporter; assert a log line containing a seeded identifier is redacted | tests/integration/test\_privacy\_controls.py |

### Reporting

The test suite emits a coverage report mapping requirement identifiers to test outcomes. That report is committed, and the demo can show it: a judge asking "how do you know the trace is correct" gets an answer with a file name attached.
