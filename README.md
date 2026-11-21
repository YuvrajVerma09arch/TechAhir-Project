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

**Our interpretation of "AI model":** the statement says *"Use any tech stack… We will judge based
on how you build,"* and the supplied dataset has no labels to train on or validate against. We
therefore implemented the first pass as a **deterministic rules layer** with conservative
abstention — deliberately *not* an external LLM call. We call it the *first-pass engine* or *rules
layer* throughout this document so no reviewer expects a trained model. It runs fully offline and
is reproducible.

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

### How this satisfies "we want an AI model to do this first pass"

The statement itself says *"Use any tech stack. Details are left out on purpose. We will judge
based on how you build. Get a working core first."* The implementation choice is therefore ours,
and the evaluation is on the quality of the build.

The statement also defines what that first pass must be capable of: *"The model will sometimes be
wrong, slow, or unavailable, and a wrong priority on an urgent ticket is costly, so anything the
system is not sure about must go to a person."* We designed around exactly that — the engine emits
a category, priority, confidence and reason, and deliberately **abstains** when evidence is weak,
conflicting or safety-relevant. Failure of the decision component is treated as a normal case, not
an exception.

The supplied file contains **no category or priority labels**. Training a supervised classifier
would require inventing labels, which would make every accuracy number meaningless. We therefore
report only operational counts and state that limitation plainly. In production, the human review
queue produces the missing ground truth; a trained model can then be evaluated against the rules
baseline on held-out reviewed tickets. The `TriageEngine` protocol is the swap point.

| Statement requirement | How this project satisfies it |
| --- | --- |
| First-pass classification | Rules layer emits category + priority + confidence + reason for every ticket |
| "wrong, slow or unavailable" | Injectable failing/invalid engines, failure containment, no ticket dropped, documented degradation path |
| "anything not sure about goes to a person" | Dual-threshold abstention + safety flags; 24.67% escalation, 100% of Urgent escalated |
| "Use any tech stack / judge how you build" | Simple, auditable, offline deterministic logic with tests and a truthful report |
| "Get a working core first" | Working ingestion, classification, review queue, report and API before optional polish |

### Why no external LLM API

This was an engineering choice, not a requirement of the statement. We avoided it because:

1. **Reproducibility** — no credentials are supplied and the results in §10 must be identical for
   every reviewer. LLM output varies across model versions and sampling settings; the rules engine
   is deterministic.
2. **Injection surface** — the dataset contains planted instructions aimed at an AI classifier
   (`T-0072`, `T-0245`). A deterministic rules layer cannot be prompt-injected; an LLM primary
   classifier would put the attack on the critical path.
3. **No evidence of benefit** — with no ground-truth labels there is no way to show an LLM is more
   accurate, and its self-reported confidence is not a reliable basis for the "anything not sure
   about goes to a person" rule. Our confidence comes from transparent evidence strength and a
   top-two margin instead.
4. **Working core first** — an offline engine runs anywhere with no setup, so a reviewer can clone,
   install and reproduce the entire result in minutes.

The engine remains **LLM-ready**: it implements the `TriageEngine` protocol in
`app/triage/types.py`, so an LLM classifier can be injected into `TriageService` without changing
the service, API, storage or dashboard. See the design note for the future model-serving path.

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

### Optional LLM caution judge

The rules engine is always the classifier. An **optional**, off-by-default LLM layer can be added
on top as a *caution judge* — configured with `LLM_JUDGE_ENABLED=true` and an OpenAI-compatible
endpoint (`LLM_API_KEY`, `LLM_API_BASE`, `LLM_MODEL`). It is deliberately one-directional:

- It returns only `{"escalate": boolean, "reason": string}` — **never a category or priority**.
- Its only effect is to **add** human review. It cannot auto-accept a ticket or change a label.
- Ticket text is injection-stripped before being sent and treated strictly as untrusted data.
- Invalid JSON, a timeout or any API failure **fails closed** (escalates) rather than silently
  reducing caution.
- It is disabled by default, so the offline, reproducible results in §10 are unchanged.

This makes hallucination bias toward safety: a false "escalate" costs one review, while a false
"do not escalate" cannot override the rules decision. The human reviewer remains the final
authority. See `.env.example` for all settings.

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
| `POST` | `/api/triage/ticket` | Create and triage ONE ticket (id generated when omitted) |
| `POST` | `/api/triage/seed` | Process the bundled 300 tickets (idempotent) |
| `GET` | `/api/tickets` | List/filter (`category`, `priority`, `status`, `page`, `page_size`) |
| `GET` | `/api/tickets/{id}` | Ticket detail |
| `GET` | `/api/review-queue` | Pending human reviews (paginated) |
| `POST` | `/api/review/{id}` | Submit corrections and mark reviewed |
| `GET` | `/api/report` | Full processing report |

CSV downloads are generated client-side in the dashboard's Reports section; there is no
server-side export route.

The dashboard's **New Ticket** section is a guided intake form: it offers issue-type quick
picks, optional urgency context and worked examples, but deliberately does **not** let the raiser
choose the category or priority — that is the engine's job. New tickets are added to the live
store, so the committed 300-ticket artifacts remain the reference benchmark run.
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
| Automatically classified | **226 (75.33% automation coverage)** |
| Pending human review | **74 (24.67% review rate)** |
| Human reviewed / failed | **0 / 0** |
| Accounting invariant | **holds** — 226 + 74 + 0 + 0 = 300 |
| Average engine latency | ~1.4 ms/ticket |

**Category distribution:** Technical 68 · Billing 65 · Account 62 · Other 61 · Shipping 44
**Priority distribution:** Low 233 · Urgent 28 · High 27 · Medium 12

**Escalations:** classifier/safety conflicts 52; safety reasons — financial loss 20, hard
deadline 18, access/2FA loss 17, severe impact 15, service outage 14, explicit urgency 12,
security breach 12, account takeover 3; prompt-injection markers 2. The two planted injections
(`T-0072`, `T-0245`) were escalated and their embedded instructions ignored; the disguised
account-compromise ticket `T-0259`, the 2FA/access-loss tickets (`T-0123`, `T-0155`, `T-0172`,
`T-0219`, `T-0251`) and the empty-body ticket `T-0093` are all forced to review. All 28 Urgent
tickets require human confirmation.

Coverage dropped from an earlier 78% to 75.33% deliberately: a safety review found critical
tickets being auto-accepted as Low, and the fixes route them to people instead. Safety is
prioritised over automation coverage.

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
  unavailable model degrades to rules + mandatory review rather than blocking the queue. The
  `TriageEngine` protocol is the plug-in point: an LLM-backed classifier can be added later
  without touching the service, API, storage or dashboard, provided it is validated against a
  labelled review sample before it is allowed to auto-accept anything.
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

Exact step-by-step instructions (including how `data/tickets.csv` travels with the repo, seed
commands, Vercel/Render configuration, and the persistent-disk caveat) are in
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

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
