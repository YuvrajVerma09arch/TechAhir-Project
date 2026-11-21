# Support Ticket Triage System

An end-to-end, production-minded triage service for the Ahir company technical assessment.
It reads customer support tickets, assigns a **category** and a **priority**, estimates
confidence, automatically accepts only the tickets it is confident about, and routes everything
uncertain to a **human review queue**. It finishes with a truthful report accounting for every
ticket.

> **Safety principle:** a wrong priority on an urgent ticket is costly. Escalation and reliable
> human review are deliberately prioritised over automation coverage.

---

## 1. Problem statement

Support teams receive hundreds of tickets a day. Each must be read, categorised and prioritised
before anyone can act. We want an AI model to do the first pass — but the model will sometimes be
wrong, slow or unavailable, and anything it is not sure about must go to a person.

For this assessment the system processes the provided 300 tickets, writes `results.csv`, exposes
an API, provides a human review workflow and a dashboard, and reports exactly how all 300 tickets
were handled. The original statement is in [`docs/problem-statement.pdf`](docs/problem-statement.pdf).

---

## 2. Dataset and taxonomy

The provided [`data/tickets.csv`](data/tickets.csv) contains **300 tickets**
(`T-0001` … `T-0300`) with columns `id, received_at, customer, subject, body`.

**There are no ground-truth labels.** No supervised model can be trained and no accuracy figure
can be honestly reported. We therefore implement a transparent, conservative deterministic
baseline and treat its confidence scores as *routing signals*, not calibrated probabilities.

Taxonomy is taken from the dataset's own README (not from generic defaults):

| Field | Allowed values |
| --- | --- |
| Category | `Billing`, `Technical`, `Account`, `Shipping`, `Other` |
| Priority | `Low`, `Medium`, `High`, `Urgent` |

Ticket text is treated strictly as **untrusted data**. The dataset contains exactly two planted
instruction-like strings (`T-0072`, `T-0245`) attempting to change the classifier's rules; these
are detected and escalated to human review, never obeyed. The audit also found 58 core safety /
escalation candidates, one empty body (`T-0093`), several near-empty and non-English tickets, and
heavily templated duplicate text — all of which inform the conservative routing rules. See
[`docs/dataset-notes.md`](docs/dataset-notes.md) for the full evidence-backed audit.

---

## 3. Quickstart

Requires Python 3.11+ and Node.js 18+.

```bash
# 1. Python environment
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Start the backend API  (http://localhost:8000)
uvicorn app.main:app --reload --port 8000

# 3. Process the 300 provided tickets (idempotent; safe to repeat)
curl -X POST http://localhost:8000/api/triage/seed

# 4. Start the dashboard  (http://localhost:5173)
cd web && npm install && npm run dev

# 5. Verify
curl http://localhost:8000/health
curl http://localhost:8000/api/report
python3 -m pytest -q
```

`results.csv` and `report.json` are written to `artifacts/`. Interactive API docs are at
`/docs`.

---

## 4. Architecture

```
React + JavaScript (Vite)  ---> Vercel     dashboard: overview / analytics / review / reports
        |  REST (fetch)
        v
FastAPI + Pydantic        ---> Render      /api/*, /health, consistent error envelopes
        |
        v
TriageService
   |-- classifier.py        deterministic category rules (+ optional TF-IDF exemplar signal)
   |-- priority_engine.py   safety/urgency rules; never auto-downgrade a critical ticket
   |-- confidence.py        thresholds, asymmetric routing, injection detection
   |-- reporting.py         report, accounting invariant, CSV exports
   `-- SQLite               tickets, original predictions, review corrections, audit trail
        |
        v
artifacts/results.csv  +  artifacts/report.json  +  review queue  +  CSV exports
```

The four lifecycle states are mutually exclusive, so a ticket is counted exactly once:
`auto_classified`, `pending_review`, `human_reviewed`, `failed`.

```
total input = auto_classified + pending_review + human_reviewed + failed
```

Shared taxonomy and interfaces live in [`app/triage/types.py`](app/triage/types.py).

---

## 5. Technology choices

| Layer | Choice | Reason |
| --- | --- | --- |
| API | FastAPI + Pydantic | Typed boundaries, automatic validation and OpenAPI docs |
| Service / rules | Python stdlib (+ optional scikit-learn TF-IDF) | Offline, deterministic, auditable, no API keys or paid services |
| Storage | SQLite (`sqlite3`) | Zero infrastructure, persistent review queue, easy local demo |
| Dashboard | React + JavaScript + Vite | Fast, deployable as a static site on Vercel |
| Charts | Custom CSS/SVG bar components | Clear analytics without a chart-library dependency |
| Tests | pytest (+ FastAPI TestClient) | Unit, service and API coverage |

No external model service, API key or paid dependency is required. The application runs fully
offline.

---

## 6. Classification approach

Because the dataset is unlabelled, we do **not** claim to have trained a supervised model.
The engine is deliberately transparent:

- **Category** — weighted keyword/phrase scoring over subject and body, with separate evidence
  strength and top-two margin. A weak or ambiguous match yields low confidence.
- **Priority** — a dedicated safety layer checks for account compromise, security incidents,
  financial loss, service-wide outages, hard deadlines and severe impact. Safety signals can
  raise urgency but never let a low classifier score silently downgrade a risky ticket.
- **Injection defence** — instruction-like text inside a ticket (`[assistant:`, `IMPORTANT
  SYSTEM NOTE`, `ignore all previous instructions`, `Output priority=`, role directives) is
  detected, ignored as content and forced into review.
- **Uncertainty** — confidence is a heuristic strength/margin signal, not a calibrated
  probability. When it cannot be established, the ticket is escalated.

An engine injectable into `TriageService` also lets tests simulate failures, timeouts and invalid
responses.

---

## 7. Confidence and escalation strategy

| Condition | Outcome |
| --- | --- |
| Category **and** priority confidence both above threshold, no safety/injection flags | `auto_classified` |
| Either confidence below threshold, or the two disagree | `pending_review` |
| Urgent predicted with low margin, or safety rules disagree with the model | `pending_review` |
| Injection markers, empty text, missing fields, malformed model output | `pending_review` or `failed` |
| Engine raises / times out / returns invalid data | `failed` (never dropped) |

Thresholds are asymmetric: an `Urgent` prediction needs stronger evidence than a `Low` one.
Every escalation carries a human-readable `review_reason`. The original prediction is never
overwritten — human corrections are stored separately for auditability.

---

## 8. Human review workflow

1. `GET /api/review-queue` lists pending tickets with confidence values and escalation reasons.
2. A reviewer opens a ticket, reads the original text and the model's prediction.
3. `POST /api/review/{ticket_id}` submits corrected category/priority.
4. The record becomes `human_reviewed`; the original prediction remains intact in the audit trail.
5. Corrections can later seed a labelled evaluation set (see design note).

---

## 9. API reference

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Liveness/health |
| `POST` | `/api/triage/batch` | Triage tickets from JSON or CSV upload |
| `POST` | `/api/triage/seed` | Process the bundled 300 tickets (idempotent) |
| `GET` | `/api/tickets` | List/filter (`category`, `priority`, `status`, `page`, `page_size`) |
| `GET` | `/api/tickets/{id}` | Ticket detail |
| `GET` | `/api/review-queue` | Pending human reviews (paginated) |
| `POST` | `/api/review/{id}` | Submit corrections and mark reviewed |
| `GET` | `/api/report` | Full processing report |

CSV downloads are generated client-side in the dashboard's Reports section; there is no
server-side export route.
All responses use a consistent error envelope:
`{"error": {"code": "...", "message": "...", "details": ...}}`.

---

## 10. Processing results

<!-- RUN_STATS_START -->
Generated from the real 300-ticket dataset by `POST /api/triage/seed`. Full machine-readable
output: [`artifacts/report.json`](artifacts/report.json),
[`artifacts/results.csv`](artifacts/results.csv),
[`artifacts/review_queue.csv`](artifacts/review_queue.csv).

| Metric | Result |
| --- | --- |
| Total input / processed | **300 / 300** |
| Automatically classified | **234 (78.0% automation coverage)** |
| Pending human review | **66 (22.0% review rate)** |
| Human reviewed / failed | **0 / 0** |
| Accounting invariant | **holds** — 234 + 66 + 0 + 0 = 300 |
| Average engine latency | ~0.8 ms/ticket |

**Category distribution:** Technical 68 · Billing 65 · Account 62 · Other 61 · Shipping 44
**Priority distribution:** Low 244 · Urgent 24 · High 20 · Medium 12

**Escalations:** classifier/safety conflicts 41; safety reasons — financial loss 17, severe
impact 15, service outage 14, explicit urgency 12, security breach 12, hard deadline 11,
account takeover 3; prompt-injection markers 2. The two planted injections (`T-0072`, `T-0245`)
were escalated and their embedded instructions ignored; the disguised account-compromise ticket
`T-0259` was escalated to Urgent.

These are operational counts from the deterministic rules engine, **not** accuracy figures —
the dataset has no ground-truth labels.
<!-- RUN_STATS_END -->

---

## 11. Design note — scaling to 50,000 tickets/day and staying healthy for a month

- **Implemented today — deterministic, bounded core.** Triage is a synchronous, idempotent
  `TriageService` over SQLite, with conservative rules and explicit abstention. At 300 tickets
  this is instant and fully reproducible; the same code path is the unit of work a worker would
  call at scale.
- **Future — asynchronous, queue-based batch processing.** Put ticket arrivals on a durable
  queue (SQS/Redis/RabbitMQ); workers claim one ticket at a time, use the unique ticket id as an
  idempotency key, and write results transactionally. At ~50,000/day (~0.6/s average, with peaks)
  a modest worker pool absorbs load; autoscale on queue depth, and dead-letter anything that
  repeatedly fails instead of dropping it.
- **Future — horizontal scaling and model serving.** Workers are stateless and scale out
  independently of the API. The classifier becomes a versioned model artefact behind a local
  inference service with timeouts, circuit breakers and a deterministic fallback; a slow or
  unavailable model degrades to rules + mandatory review rather than blocking the queue.
- **Future — monitoring accuracy, confidence and escalation.** Today's `/api/report` already
  exposes coverage, review rate, escalation reasons and failure counts; the following extends it.
  Track automation coverage, review rate,
  confidence distributions, escalation-reason mix, `failed` count, p95 latency and queue depth.
  Human corrections are the ground truth: compare reviewer decisions with model decisions to get
  live precision/recall by category and priority — with special attention to recall on `Urgent`.
- **Future — drift detection and periodic evaluation.** Weekly shadow evaluation on a labelled sample,
  PSI/KS drift checks on feature and confidence distributions, and alerts when review rate or
  `Urgent` disagreement moves beyond control limits. Retrain/recalibrate only on reviewed,
  labelled data, behind an A/B gate.
- **Future — verifying reliability one month later.** Replay a frozen golden set (including the injection
  and urgency edge cases) against the current pipeline; assert the accounting invariant, stable
  `Urgent` recall, bounded latency and no silent failures. Compare today's report with the
  month-old baseline and require an explicit sign-off for any regression before promotion.

---

## 12. Testing

```bash
python3 -m pytest -q
```

Coverage includes valid classification, priority assignment, low-confidence escalation,
confidence disagreement, critical escalation, empty/missing fields, model failure, invalid model
response, human review/correction, duplicate processing and batch accounting invariants. API
tests use an isolated temporary database. No test is skipped and no metric is fabricated.

---

## 13. Deployment

- **Backend (Render):** `render.yaml` defines a Python web service; start command
  `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, health check `/health`.
- **Frontend (Vercel):** `vercel.json` builds the Vite app from `web/`; set
  `VITE_API_BASE_URL` to the Render service URL.

---

## 14. Limitations and assumptions

- The dataset is unlabelled, so there is no supervised model, no training/evaluation split and no
  accuracy claim. Confidence is heuristic, not calibrated probability.
- Keyword rules are interpretable but narrow; unseen phrasing is intentionally escalated rather
  than guessed. This lowers automation coverage on purpose.
- The 300 tickets are the supplied assessment sample with fictitious customer names; no real
  customer data is committed.
- Injection detection is pattern-based and defence-in-depth; ticket text must never be executed
  or inserted into a privileged instruction context.

---

## 15. Publishing

```bash
git add -A
git commit -m "feat: complete support ticket triage system"
git push -u origin main
# Then make the repository public in GitHub settings.
```

No API keys, secrets, virtual environments or model binaries are committed.
