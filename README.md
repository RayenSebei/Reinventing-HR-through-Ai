# Vouch

Vouch is an AI-assisted recruitment workspace for evidence-led CV review, approval-controlled candidate communication, and timed first-round chat interviews.

> AI collects, organizes, and explains evidence. People retain hiring authority.

This repository is a hackathon prototype built with synthetic data. It demonstrates governance controls; it is not production-ready hiring software or a security certification.

## The problem

Recruiting teams need faster screening and follow-up without turning opaque model output into an automated employment decision. They also need evidence provenance, consistent candidate treatment, privacy boundaries, and a record of who approved consequential actions.

## What Vouch implements

- A role-aware React workspace for recruiters, hiring managers, HR administrators, and auditors.
- Case criteria, PDF CV ingestion, visible-text analysis, suspicious-content findings, sourced quotes, and human-confirmed shortlists.
- A suggested evidence ranking that never automatically rejects candidates.
- Exact-payload invitation drafts, four-eyes approval, expiry, single-use execution, and a sandbox outbox.
- One-time candidate interview links, English/French/Arabic consent flow, a server-enforced timer, consistent core questions, CV-gap questions, short-answer follow-ups, and persisted response times.
- Combined CV/interview evidence reports, audit-recorded report opening, and human `advance` / `hold` / `reject` decisions with written reasons.
- Interview scheduling, follow-up tasks, role-scoped audit views, a hash/HMAC-linked ledger, and synthetic SENTINEL security scenarios.

The AI Inbox remains an explicitly labelled synthetic UI preview. External email and calendar delivery are not enabled by default. The default `lexicon` evidence provider is deterministic and does not call an LLM.

## Architecture

```text
React HR workspace                     Candidate interview page
        |                                         |
        +---------------- Vouch API ---------------+
                          |
              role/case and token boundaries
                          |
  cases - candidates - documents/evidence - chat sessions/messages/reports
                          |
             proposals - approvals - gateway - sandbox outbox
                          |
                 tamper-evident Trust Ledger
                          |
                       SQLite
```

`vouch/` is the canonical integrated application and source of truth. The original `interview-chat/` implementation is retained for provenance and its independent tests/SENTINEL scenarios; do not run it beside Vouch as a second production data store.

| Path | Responsibility |
|---|---|
| `vouch/app/main.py` | Starlette routes, auth boundaries, security headers, static application |
| `vouch/app/cases.py` | Cases, candidates, documents, evidence, rankings, erasure |
| `vouch/app/chat_interview.py` | Candidate tokens, consent, timer, guarded chat, transcript, combined report, human decisions |
| `vouch/app/gateway.py` | Exact-payload proposal/approval checks and single-use execution |
| `vouch/app/ledger.py` | Hash and HMAC-linked audit events and integrity verification |
| `vouch/frontend/` | React HR workspace; production assets are built into `vouch/static/app/` |
| `sentinel_hr/` | 27 canonical-app adversarial scenarios |
| `interview-chat/sentinel/` | 13 original live interview-module scenarios |

See [the integration audit](docs/integration-audit.md) for branch contributions, conflicts, decisions, and remaining risks.

## Recruitment workflow

1. A recruiter creates a case, defines criteria, and ingests candidate CVs.
2. Vouch extracts candidate-provided evidence and flags suspicious or hidden document content.
3. A person reviews dossiers and confirms an explicit shortlist.
4. A recruiter drafts a candidate invitation containing a one-time chat link.
5. A different authorized hiring manager reviews and approves the exact payload hash.
6. The gateway rechecks the approval and activates the candidate link only on successful single-use execution.
7. The candidate consents and completes the timed multilingual interview.
8. HR opens the combined CV/interview evidence report from the candidate evidence view.
9. A recruiter or hiring manager records a human decision and written reason.
10. Scheduling, follow-up, approvals, and relevant security actions remain visible in the audit trail.

## AI and human oversight

Vouch treats model output as untrusted draft material:

- The default `VOUCH_MODEL=lexicon` makes no external model call.
- Optional compatible model providers extract candidate claims; application code checks quotes against visible CV text.
- Candidate chat follows a deterministic case question plan. Manipulation-like answers are retained for review but do not advance or become report evidence.
- Suggested ordering and reports are decision support, not authorization. Vouch never auto-rejects a candidate.
- Approval and hiring-decision authority comes from authenticated human roles, never from model text.

## Security and SENTINEL

Implemented prototype controls include:

- password hashing and signed staff sessions;
- case-scoped staff authorization and separate candidate token authentication;
- random interview tokens referenced by hash in the session table, expiry, disabled-until-approved state, and restart prevention;
- strict request schemas, upload/answer limits, candidate endpoint rate limiting, CSP, clickjacking and MIME-sniffing headers;
- hidden/tiny/off-page CV text detection and prompt-injection heuristics;
- exact canonical payload digests, self-approval prevention, expiring approvals, nonce verification, and replay prevention;
- append-only SQLite triggers plus hash/HMAC chain verification.

The ledger is tamper-evident, not tamper-proof: a database/key administrator could rebuild or replace it. Rate limiting is in-process, token links are bearer credentials, and the prototype uses SQLite and a single application process.

Some security-testing and SENTINEL attack-scenario inspiration was drawn from [Indaba](https://github.com/rayen-mansouri/Indaba). Vouch's implementation and tests in this repository are project-specific.

## Technology

- Python 3.11+, Starlette, Uvicorn, Pydantic, SQLite
- React 19, TypeScript, Vite, TanStack Query, Radix UI
- PDFPlumber/PDFium for document analysis
- Pytest and Playwright for automated checks
- Optional OpenAI-compatible or local Ollama evidence provider

## Install and run

```powershell
cd vouch
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m app --seed --yes
```

Open `http://127.0.0.1:8000`. Node is not required to run the committed production build.

For frontend development:

```powershell
cd vouch\frontend
npm ci --ignore-scripts
npm run dev
```

### Demo identities

All demo accounts use `demo1234`. Account shortcuts appear only when `VOUCH_DEMO_MODE=1`.

| Account | Role |
|---|---|
| `recruiter@vouch.demo` | Recruiter |
| `manager@vouch.demo` | Hiring manager |
| `admin@vouch.demo` | HR administrator |
| `auditor@vouch.demo` | Auditor |

Never reuse these credentials outside the synthetic demo.

## Configuration

Copy `.env.example` and set values in your process environment. Important settings include:

- `VOUCH_JWT_SECRET` and `VOUCH_LEDGER_KEY` (required stable secrets outside a throwaway demo);
- `VOUCH_PUBLIC_BASE_URL` for generated candidate links;
- interview duration, invite lifetime, answer limit, and rate limit;
- `VOUCH_MODEL` plus provider-specific model settings;
- `VOUCH_DATA_DIR` / `VOUCH_DB` and retention days;
- optional signed n8n delivery settings.

No API keys or real candidate data belong in Git.

## Testing

```powershell
cd vouch
$env:OPENBLAS_NUM_THREADS="1"
.\.venv\Scripts\python.exe -m pytest -q

cd frontend
npm run typecheck
npm run lint
npm run build
npx playwright install chromium
npm run test:e2e
```

Current validated results on the integration branch:

- Canonical backend/integration suite: **60 passed**, including 27 `sentinel_hr` cases.
- Original interview module suite: **36 passed**.
- Original interview live SENTINEL runner: **13/13 passed**.
- Frontend typecheck, safe-rendering lint, and production build: **passed**.
- Playwright: attempted, but the available Windows host crashed bundled Chromium under memory pressure and stalled system Chrome before assertions; browser results are therefore not claimed for this integration commit.

## Repository layout

```text
vouch/             canonical integrated application
interview-chat/    original standalone feature module and tests (reference)
sentinel_hr/       canonical app attack runner and fixtures
sentinel/          shared attack scenario library and synthetic CVs
n8n/               optional signed delivery workflow
docs/              architecture, integration, and dashboard documentation
project-review/    earlier project audit and planning artifacts
```

## Known limitations

- Prototype persistence and rate limiting are single-process; there are no production migrations or distributed locks.
- Interview links are bearer links; the prototype does not separately verify candidate identity.
- The integrated CV upload path supports PDF. DOCX/TXT ingestion remains in the retained standalone module and is not advertised as integrated.
- The chat uses deterministic questions and guard rules; it does not use the optional CV model provider for generative interviewing.
- Email and calendar integrations are simulated/sandboxed unless separately configured and authorized.
- Detection heuristics and self-authored synthetic tests do not establish real-world fairness, security, or regulatory compliance.
- Browser end-to-end checks must be rerun on a host with sufficient Chromium memory before a live demo.

## Credits

Built by the Vouch hackathon team. Security-scenario inspiration is attributed above; third-party package licenses remain with their respective authors. No repository-wide license has been added because the owners have not established a licensing choice.
