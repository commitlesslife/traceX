# TRACE-X demo runbook

## Launch

Build the frontend, then start the API from the repository root:

```powershell
cd D:\TrackX\frontend
npm install
npm run build
cd D:\TrackX
$env:PYTHONPATH='D:\TrackX\backend\src'
py -3 -m uvicorn tracex.main:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000/>. API docs: <http://127.0.0.1:8000/docs>.

The synthetic demo accounts are `analyst_priya` / `analyst123`, `supervisor_rajesh` / `supervisor123`, `admin_user` / `admin123`, and `auditor_user` / `auditor123`.

## Cases for the stage

| Case | Reported | Trail | Demonstrates |
| --- | ---: | --- | --- |
| `CASE-2026-0891` | ₹1,00,000 | Compact | Pooled funds and an external ledger boundary |
| `CASE-2026-0888` | ₹1,00,000 | Six hops, 18 transfers | Branching with partial attribution |
| `CASE-2026-0877` | ₹1,80,000 | Eight hops, 20 transfers | Long ladder and a synthetic international boundary |
| `CASE-2026-0866` | ₹1,25,000 | Seven hops, 15 transfers | Domestic and international boundaries |

For a long trail, open `CASE-2026-0877`, run the ledger trace, and switch from **Network** to **Globe**. India faces forward. Drag to rotate, scroll or pinch to zoom, and use **Home** to return to the India view. Hop chips focus the sequence. Selecting a transfer highlights its route and opens its ledger evidence. The focused strip distinguishes the full transfer from the amount attributed to the reported payment. Pause and resume the moving money marker during discussion.

For two separate boundaries, open `CASE-2026-0866`. One boundary is a separate domestic institution; the other is a synthetic international processor. Map positions are **presentation anchors**: the ledger has no verified account coordinates. Never present the displayed city or country as a real transaction location.

The graph, hop timeline, evidence drawer, and globe use the same trace result. The network graph remains horizontally scrollable for longer fixtures.

## Reset demo data

The seed command replaces local demo records, including stored traces and drafts. Back up `D:\TrackX\tracex_mvp.db` first if the current session matters:

```powershell
$env:PYTHONPATH='D:\TrackX\backend\src'
py -3 backend/src/tracex/seed_demo.py
```

The reset creates all four cases. It does not call a bank or freeze an account.

## Checks

```powershell
cd D:\TrackX\frontend
npm run build
cd D:\TrackX\backend
$env:PYTHONPATH='D:\TrackX\backend\src'
$env:DATABASE_URL='sqlite:///./tracex_validation.db'
py -3 -m pytest tests/unit/test_api_workflow.py -q
```

The extended fixture checks assert hop depth, transfer count, boundary count, unique transaction IDs, and exact money conservation.
