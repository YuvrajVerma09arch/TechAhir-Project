# Deployment Guide — Support Ticket Triage

Backend: **FastAPI on Render**. Frontend: **React + Vite on Vercel**. No API keys, no paid model
services, no secrets. Everything is offline and deterministic.

## How the data is handled

| Path | In repo? | Purpose |
| --- | --- | --- |
| `data/tickets.csv` | **Yes — committed** | The 300 supplied tickets. Travels with the clone, so the backend can seed itself. |
| `artifacts/results.csv`, `report.json`, `review_queue.csv`, `all_predictions.csv` | **Yes — committed** | Verified deliverables from the real 300-ticket run. |
| `artifacts/triage.db` | **No — gitignored** | SQLite database created at runtime by `TriageService`. |

`POST /api/triage/seed` reads `data/tickets.csv`, triages all 300 tickets and (re)writes the
artifacts. It is **idempotent** — re-running never double-counts. You can also upload any other
CSV with `POST /api/triage/batch` (multipart field `file`, or JSON `{"tickets": [...]}`).

---

## 1. Render — backend API

### Option A: Blueprint (recommended)
1. Render Dashboard → **New** → **Blueprint**.
2. Connect the GitHub repo, branch `main`.
3. Render reads `render.yaml` and creates `support-ticket-triage-api`:
   - build: `pip install -r requirements.txt`
   - start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - health check: `/health`
4. Deploy, then copy the service URL (e.g. `https://support-ticket-triage-api.onrender.com`).

### Option B: Manual web service
New → Web Service → Python; set build/start/health exactly as above.

### Environment variables (all optional — defaults are correct)
```
DB_PATH=artifacts/triage.db
DATA_PATH=data/tickets.csv
CATEGORY_CONFIDENCE_THRESHOLD=0.65
PRIORITY_CONFIDENCE_THRESHOLD=0.55
DEFAULT_PAGE_SIZE=50
MAX_PAGE_SIZE=200
```
Relative `DATA_PATH` resolves from the repository root; relative `DB_PATH` resolves from the
process working directory (repo root on Render).

### Populate and verify
```bash
curl https://<your-render-url>/health
curl -X POST https://<your-render-url>/api/triage/seed
curl https://<your-render-url>/api/report
```

### IMPORTANT — persistence on the free plan
Render's free plan has an **ephemeral filesystem**. The SQLite DB and any human review
corrections are **lost on every restart/redeploy**. For a genuinely shippable deployment:

- Upgrade to a paid plan with a **persistent disk** mounted at e.g. `/data`, and set
  **`DB_PATH=/data/triage.db`**. Review corrections then survive restarts.
- Run **exactly one instance**. SQLite is a local file; multiple instances would split state.
  (Multi-instance scaling requires migrating storage to Postgres — a code change, not a config.)
- After any redeploy on a fresh disk, call `POST /api/triage/seed` again.

---

## 2. Vercel — frontend dashboard

1. Vercel → **Add New** → **Project** → import the same repo.
2. Keep the **Root Directory as the repository root** — `vercel.json` runs
   `cd web && npm install && npm run build` and serves `web/dist`.
3. Add an environment variable **before building**:
   ```
   VITE_API_BASE_URL=https://<your-render-url>
   ```
   No trailing slash. This is baked in at **build time** — after changing it, trigger a new deploy.
4. Deploy. `vercel.json` includes the SPA rewrite `/(.*) → /index.html`.
5. Open the dashboard → click **Process sample dataset (300 tickets)** → Overview/Analytics/
   Review Queue/Reports fill from the real API.

CORS is already open (`allow_origins=["*"]`, no credentials), so the Vercel origin can call Render.

---

## 3. Local development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
curl -X POST http://localhost:8000/api/triage/seed
cd web && npm install && npm run dev
python3 -m pytest -q     # 87 tests
```

For the React app to point at Render locally:
```bash
VITE_API_BASE_URL=https://<your-render-url> npm run dev
```

---

## 4. Deployment checklist

- [ ] Backend `/health` returns `{"status":"ok"}`
- [ ] `POST /api/triage/seed` returns 200 with `total_input: 300`
- [ ] `GET /api/report` shows `invariant_holds: true`
- [ ] `VITE_API_BASE_URL` set and frontend rebuilt after setting it
- [ ] Dashboard Overview shows 300 total / 226 auto / 74 review
- [ ] Reviewing a ticket updates the on-disk artifacts (requires persistent disk to survive restart)
- [ ] One Render instance only; persistent disk configured if reviews must survive

## 5. Known deployment limitation

With SQLite + ephemeral disk, the service is fully functional for evaluation and demos, but
**human review state is not durable across redeploys** on the free plan. The fix is a persistent
disk (or a Postgres migration for multi-instance scale). This is called out in the README design
note under future scaling work.
