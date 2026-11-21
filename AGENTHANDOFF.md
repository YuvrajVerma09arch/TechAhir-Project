# AGENT HANDOFF — Ahir Company Project Assessment

> **Living document.** Every agent that picks up this project MUST read this file first,
> then update it at every meaningful change before handing off. Never delete prior history —
> append to the logs below so context is never lost between agents.

---

## 1. Project Overview

| Field | Value |
| --- | --- |
| Project name | Ahir Company Project Assessment |
| Repository root | `/Users/yuvraj/ahir-project-assessment` |
| Purpose | Build & ship the project defined by the user's assessment **statement** (not yet provided). |
| Current phase | **PHASE 0 — Scaffolding complete, awaiting the requirements statement.** |
| Owner / requester | User (`Telos`) |

### What the project is
To be defined once the user provides the **statement**. Do NOT guess the product, domain,
features, or tech stack. Wait for the statement, then confirm understanding before building.

---

## 2. Confirmed Requirements & Constraints (from the user)

These are the operating rules the user explicitly set. Treat them as binding until changed:

1. **Statement pending** — The user will provide the project statement next. All actual
   development waits for it.
2. **Full development + shipping** — Work covers both implementation and shipping/deployment.
3. **Deployment targets**
   - **Vercel** — intended for the frontend / web app.
   - **Render** — intended for the backend / API / services.
   - (Exact split depends on the statement; confirm before locking architecture.)
4. **Git**
   - `git init` has been done on `main`.
   - **NO remote is to be added yet.** The user will add the remote after the project is complete.
   - Commit **all updates in meaningful parts** — i.e. atomic, logical commits at each
     meaningful milestone. Do not leave work uncommitted and do not make one giant final commit.
5. **Multi-subagent workflow** — The whole task must be executed using multiple subagents
   (exploration, planning, implementation, testing, docs, review, etc.). Coordinate work so
   agents do not overlap; brief each with the context in this file.
6. **Handoff discipline** — Keep `AGENTHANDOFF.md` updated at **every meaningful update** so
   any new agent has full context. See §7 for the update procedure.
7. **More instructions coming** — The user said remaining instructions will be provided when
   they get the details. Expect additional constraints after the statement.

---

## 3. Environment Notes

- Machine: macOS (darwin), working dir `/Users/yuvraj`.
- Git identity configured: `Telos <telos2909@gmail.com>`, Git 2.54.0.
- Default branch: `main`.
- Temp files (when needed): `/private/var/folders/4q/sb7ljglx3yq8mwlv51flc1pc0000gn/T/opencode`
  — prefer this over generic `/tmp`.
- No remote configured (intentional — see §2.4).

---

## 4. Architecture Intent (provisional — confirm after statement)

```
[ User / Browser ]
        |
        v
   Frontend  ----------> deployed on Vercel
        |  (HTTP/API calls)
        v
   Backend / API ------> deployed on Render
        |
        v
   Database / external services (TBD from statement)
```

Stack, framework, database, auth, and repo layout are **TBD** — decide with the user after
the statement is received. Do not scaffold framework code before that decision.

---

## 5. Current Repository State

```
ahir-project-assessment/
├── .git/                 # initialized, branch: main, no remote
├── .gitignore           # default ignores (node, python, env, OS, etc.)
├── AGENTHANDOFF.md      # this file
└── README.md            # short project stub
```

Latest commit: `chore: initialize project repository and handoff scaffold` (Phase 0).

---

## 6. Worklog / Decision Log (append-only, newest last)

| Date | Agent | Change | Commit |
| --- | --- | --- | --- |
| 2026-11-21 | Main | Created project dir, `git init` (main), added `.gitignore`, `README.md`, `AGENTHANDOFF.md`, initial commit | Phase 0 |

---

## 7. Procedure for Every Agent (MANDATORY)

1. **Read** this entire `AGENTHANDOFF.md` before doing anything.
2. **Check** §1/§2 for any new statement or instruction the user may have added.
3. **Coordinate** — only touch files assigned to your subagent role; avoid overlapping edits.
4. **Work** in thin, verifiable slices; test as you go.
5. **Commit** meaningful parts with conventional messages
   (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`, `build:`, `ci:`).
6. **Update this file** at every meaningful update:
   - bump §1 phase,
   - add rows to §6 worklog,
   - update §5 repo state if structure changed,
   - record new decisions/constraints in §2.
7. **Commit the handoff update** alongside or immediately after the change it documents.
8. **Do NOT** add a git remote. The user will do that when the project is complete.

### Multi-subagent orchestration map (to activate after the statement)

| Role | Responsibility | Status |
| --- | --- | --- |
| Orchestrator (main) | Read statement, confirm scope, split work, integrate, commit | Active |
| Explore/Research | Analyze statement, research stack & deployment needs | On demand |
| Planning | Produce implementation plan & task breakdown | On demand |
| Backend agent | API / services (Render target) | On demand |
| Frontend agent | Web app (Vercel target) | On demand |
| Testing agent | Tests & validation | On demand |
| Docs/Handoff agent | Keep this file & README current | On demand |
| Review agent | Code review before final ship | On demand |

---

## 8. Next Steps (for the next agent)

- [ ] **Wait for / capture the user's project statement** (no development before this).
- [ ] Confirm understanding, scope, and any new instructions the user supplied.
- [ ] Decide architecture & stack with the user (Vercel frontend / Render backend intent).
- [ ] Spin up the multi-subagent workflow per §7 and begin implementation in slices.
- [ ] Commit each meaningful part; keep this handoff file current throughout.
- [ ] Deploy to Vercel + Render at the end; do NOT add a remote.
