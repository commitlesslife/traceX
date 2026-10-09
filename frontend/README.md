# TRACE-X Frontend

Standalone React and TypeScript investigation workspace. The interface is built from scratch and consumes the FastAPI application in `../backend`.

## Local development

1. Start the API from the repository root:

   ```powershell
   $env:PYTHONPATH = "D:\TrackX\backend\src"
   python -m uvicorn tracex.main:app --host 127.0.0.1 --port 8000 --reload
   ```

2. In another terminal, install frontend dependencies and start Vite:

   ```powershell
   cd D:\TrackX\frontend
   npm install
   npm run dev
   ```

   Open `http://localhost:5173`. Vite proxies `/api` and `/health` to the local FastAPI service.

## Single-origin demo build

Build the frontend, then start the API and open `http://127.0.0.1:8000`:

```powershell
cd D:\TrackX\frontend
npm install
npm run build
```

FastAPI serves `frontend/dist` from `/`. The old standalone HTML remains available at `/template` for reference only.

## Screens

- Overview and complaints queue with search and complaint intake
- Case investigation with API-backed trace controls, animated selectable transaction graph, ledger evidence details, and expanded hop timeline
- Account and balance record inspection
- Analyst recommendation drafting and separate supervisor approval or rejection
- Case export download, audit records, operations status, and demo fixture reset
- Globe view clearly reports that geographic data is unavailable when ledger evidence does not include sourced coordinates

The seeded fixture is synthetic. Trace amounts are attribution upper bounds, and external-institution boundaries indicate the end of available ledger visibility.
