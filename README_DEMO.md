# TRACE-X Hackathon V1 MVP — Runbook & Verification Guide

## 1. Overview
TRACE-X is a deployable fraud tracing system for bank fraud operations teams and police cyber cells.
It follows victim funds through a transaction ledger, enforces exact paise-level money conservation, respects institutional boundaries, ensures separation of duties between analyst and supervisor, and generates auditable evidence-backed case files.

---

## 2. Quickstart: One-Command Launch

### Start the Server
Run from the repository root:
```powershell
$env:PYTHONPATH="d:\TrackX\backend\src"
python -m uvicorn tracex.main:app --host 127.0.0.1 --port 8000 --reload
```

Once running:
- **Interactive Prototype UI Template:** [http://127.0.0.1:8000/](http://127.0.0.1:8000/) or [http://127.0.0.1:8000/template](http://127.0.0.1:8000/template)
- **Interactive OpenAPI Documentation:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Service Readiness:** [http://127.0.0.1:8000/health/ready](http://127.0.0.1:8000/health/ready)

---

## 3. Seeded Demo Identities

| Username | Password | Role | Display Name | Permissions |
|---|---|---|---|---|
| `analyst_priya` | `analyst123` | **Analyst** | Priya Sharma | Intake complaints, execute traces, draft recommendations |
| `supervisor_rajesh` | `supervisor123` | **Supervisor** | Rajesh Verma | Review & approve/reject drafts (cannot self-approve) |
| `admin_user` | `admin123` | **Admin** | Admin Ops | System config, dataset reset, all analyst tasks |
| `auditor_user` | `auditor123` | **Auditor** | Audit Cell Lead | Read-only inspection of cases, traces, and audit trail |

---

## 4. Resetting Demo State
To restore the clean golden fixture state at any time:
```powershell
$env:PYTHONPATH="d:\TrackX\backend\src"
python backend/src/tracex/seed_demo.py
```
*(Or click the **Reset** button in the prototype UI top navigation bar)*

---

## 5. End-to-End Walkthrough Script (for Judges & Demo)

1. **Intake & Exact Ledger Resolution (20 sec):**
   - Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) logged in as `analyst_priya`.
   - Inspect active complaint `CMP-2026-0891` (Victim ₹1,00,000, seed `TX-SEED-100K`).
   - Note match verification status: `matched` in ledger.

2. **Deterministic Proportional Trace (40 sec):**
   - Click **Run Proportional Trace**.
   - Show the money decomposition summary:
     - `Seed Inflow = Total Unmoved + Crossed Boundary` (Exact paise conservation).
   - Point out the 4 quantities per account:
     - `Traced In`, `Traced Out`, `Unmoved (Upper Bound)`, `Available Balance`.
   - Point out account `ACC-B-202` shows **`balance unknown`** because ledger history is incomplete.
   - Point out the external boundary transfer to `HDFC_EXT` flagged with cutoff reason: `Crossed operating institution into External Partner Bank`.

   - For a larger graph and multi-hop view, open stress case `CASE-2026-0888` (`CMP-2026-0888`, seed `TX-DEEP-SEED-100K`). This synthetic branching trail reaches six hops across 19 accounts and includes an external-institution boundary. Its raw transfer amounts are not the attributed amounts: the pooled-funds rule recalculates each edge, while the trace still conserves the ₹1,00,000 seed across in-ledger value and boundary value.

3. **Recommendation Draft (20 sec):**
   - Under Analyst Recommendation Draft, select `ACC-A-101`, amount `₹44,800.00`, enter justification, and submit draft.
   - Show draft status: `DRAFT`.

4. **Separation of Duties & Supervisor Independent Review (30 sec):**
   - Switch role to `supervisor_rajesh` via the top navigation switcher.
   - Attempting to self-approve as an analyst is rejected with HTTP 403.
   - As supervisor, enter decision reason and click **Approve Recommendation Document**.
   - Show the generated cryptographic document hash. Note the explicit safety disclaimer: *Approval generates a case document only; zero external HTTP/freeze calls.*

5. **Verifiable Export (10 sec):**
   - Click **Export JSON Pack**.
   - Inspect the downloaded JSON bundle featuring evidence snapshots, trace parameters, stopping reasons, and top-level canonical `content_hash`.

---

## 6. Running Tests
To run the automated test suite verifying golden fixture invariants and API RBAC:
```powershell
$env:PYTHONPATH="d:\TrackX\backend\src"
python -m pytest backend/tests/ -v
```
