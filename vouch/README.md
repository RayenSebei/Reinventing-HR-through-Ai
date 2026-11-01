# Vouch

**An AI helper that screens CVs for a recruiter, can't be tricked by a CV, and can't send anything a manager didn't approve.**

All data is synthetic. Nothing here contacts real people.

## Run it (5 minutes)

You need **Python 3.11 or newer**.

```bash
cd vouch
pip install -r requirements.txt
python -m app --seed --yes      # confirms the wipe; creates users, a case and 10 synthetic CVs
```

Open **http://127.0.0.1:8000** and sign in with a demo account. Every demo password is
`demo1234`. Set `VOUCH_DEMO_MODE=1` to show the account shortcuts on the sign-in page;
the shortcuts are hidden by default.

| Demo user | Role | What they can do |
|---|---|---|
| recruiter@vouch.demo | Recruiter | criteria, upload CVs, rank, draft emails, send approved emails |
| manager@vouch.demo | Hiring manager | approve or reject drafted emails |
| auditor@vouch.demo | Auditor | read everything, check the ledger |
| admin@vouch.demo | HR admin | read everything, check the ledger |

Run backend tests: `python -m pytest -q` (from `vouch/`). This includes all 27
SENTINEL scenarios: the original 24 plus three route-privacy regressions.

## The 5-minute demo

1. Start at the **Command Center** for the hiring funnel, pending actions, ledger activity,
   and SENTINEL status.
2. Open **Cases** and introduce the scorecard, candidate list, and explicit shortlist.
3. Use **Evidence** to show sourced quotes, page overlays, hidden text, and review findings.
4. Open **Approvals** as a hiring manager and review the exact message and SHA-256 hash.
   Editing the draft makes the earlier approval invalid for execution.
5. Return as a recruiter, execute only an unchanged approved action through the Action
   Gateway, and show its delivery state in the **Outbox**.
6. Finish in **Trust Ledger** and **Assurance** to verify the chain and show scenario
   outcomes. Presenter mode provides this five-minute sequence in the app.

## How it works

```
CV (PDF) ─► upload + SHA-256 ─► hidden-text check (compare page renders with and without text objects)
        ─► visible text only ─► remove personal data ─► AI model or word list (extracts quotes, has no tools)
        ─► quote checker (is the quote really in the CV?) ─► SOURCED / NEEDS_REVIEW / NOT_FOUND
        ─► deterministic ranking (weights × evidence, no auto-reject) ─► recruiter confirms shortlist
        ─► draft email (proposal + SHA-256 of canonical payload) ─► manager approves THAT hash
        ─► Action Gateway re-checks everything ─► sandbox outbox ─► (optional) n8n delivers it
every step ─► Trust Ledger (hash chain)
```

| File | Job |
|---|---|
| `app/documents.py` | PDF reading, hidden/tiny/off-page text, injection phrases, keyword stuffing, date conflicts, Arabic order |
| `app/evidence.py` | criterion → quote → page → status; checks every AI quote against the visible text |
| `app/model.py` | AI connection: `lexicon` (no AI), `openai` (any compatible API), `ollama` (local), `replay`, `stub` |
| `app/pii.py` | removes emails, phones, names, addresses, birth dates before the AI or a dossier sees text |
| `app/ranking.py` | deterministic score, reasons, review flags; nobody is rejected |
| `app/gateway.py` | proposals, approvals (bound to the hash, expire, single use), the Action Gateway, n8n delivery |
| `app/ledger.py` | hash-chained event log + verification |
| `app/security.py`, `schemas.py` | login tokens, per-case access, request models that reject unknown fields |
| `static/app/` | locally built React dashboard assets |

## Workspace API

The dashboard uses `/api/candidates` for scoped filtering and pagination,
`/api/candidates/compare`, `/api/cases/{id}/analytics`, and `/api/workspace/outbox`.
`/api/audit/ledger` includes event hashes, previous hashes, MACs, and the ledger head;
`/api/audit/export` returns the caller's role-scoped JSON export with an HMAC-SHA256
signature. HR administrators manage users and the persisted approval TTL and review
threshold through `/api/admin/users` and `/api/admin/policy`.

## Choosing the AI model

Set `VOUCH_MODEL` before starting:

| Value | What happens | Extra settings |
|---|---|---|
| `lexicon` (default) | No AI. A multilingual word list finds quotes. Fully offline. | – |
| `openai` | Any OpenAI-compatible chat API | `VOUCH_OPENAI_BASE_URL`, `VOUCH_OPENAI_API_KEY`, `VOUCH_OPENAI_MODEL` |
| `ollama` | Local model through Ollama | `VOUCH_OLLAMA_URL`, `VOUCH_OLLAMA_MODEL` (default `qwen3:8b`) |
| `replay` | Re-uses answers recorded from earlier `openai`/`ollama` runs. Use this on stage. | – |

Whatever the model says, **code checks every quote** against the visible CV text. Unsupported quotes are not stored as evidence and trigger an alert; this reduces hallucination risk but cannot guarantee zero hallucinations. An answer with any extra field (like an "action") is thrown away.

The approval digest is `SHA-256(UTF-8(canonical(payload)))`; canonical JSON uses sorted keys and compact separators, and disallows floating-point values. The approval nonce is checked against the matching approval event in the append-only ledger before execution.

## Rules this code enforces

1. CV and job text are data, never instructions. Hidden text is never shown to the AI or used as evidence.
2. The AI has no tools and no identity. It can't create, approve or send anything.
3. Nothing is sent without a hiring manager approving the exact content. Any change invalidates the approval.
4. Approvals expire (`VOUCH_APPROVAL_MINUTES`, default 15) and work once.
5. Users only see cases they belong to. Identity and role come from the login token, never from the request.
6. Every request rejects unknown fields (`role`, `approved_by`, `document_id`, ...).
7. Ranking uses only the criteria the recruiter set, never protected traits, and never rejects anyone.
8. "SOURCED" means "quoted from the CV", a candidate claim. Vouch never marks anything "verified".

## What "nothing is recorded without approval" means here

| Data | Recorded automatically? |
|---|---|
| Security alerts, ledger events | Yes (audit, not decisions about people) |
| Uploaded CVs and their analysis | Yes (the recruiter's own upload) |
| AI drafts (dossier, ranking, emails) | Yes, but only as drafts |
| Confirmed shortlist | Only when the recruiter confirms it |
| Any email sent / status change | Only through an approved proposal and the gateway |

## Data handling

Original CVs stay on the Vouch server (`data/originals`, read-only). Only visible text with personal data removed is sent to an AI model. The ledger stores IDs and hashes, never CV text or contact details. `VOUCH_RETENTION_DAYS` (default 180) controls automatic purge at startup and via `python -m app.retention`; candidate erasure also removes the original document, extraction, and dossier while retaining the ledger.

## Honest limits

- Tested on synthetic CVs only. Detection was measured on the repository's fixtures, not on real CVs.
- The word-list mode is lenient: it finds a word, not real proficiency. The recruiter still decides.
- Arabic is handled for simple right-to-left lines. Complex mixed-direction lines may still read out of order.
- Scanned (image-only) CVs and DOCX are not supported yet.
- The ledger is tamper-*evident*: someone with database access could rebuild the whole chain.
- SENTINEL's attacks are written by the same team. "Independent" testing would need outside contributors.
- SQLite and one server process: fine for a demo, not for many users.

## Dashboard

The React workspace is available at `/`: Command Center, cases and evidence,
rankings and shortlist, compare, actions and outbox, approvals, ledger, assurance,
and HR administration. The legacy route falls through to the same client-side app.
All workspace APIs are authenticated and role-scoped.

The committed `static/app/` build runs with Python alone. To develop the frontend:

```sh
cd frontend
npm ci --ignore-scripts
npm run typecheck
npm run lint
npm run build
npx playwright install chromium
npm run test:e2e
```

Use Node 24. `npm run dev` proxies `/api` to port 8000. The production build is the
CSP verification target. Playwright starts an isolated temporary database, seeds
synthetic fixtures, checks all four roles, and writes screenshots for both target
resolutions and themes under `frontend/test-results/screenshots/`. Vite 7.3.7 is
pinned because Vite 8's native bundler failed memory allocation on the demo laptop.
Tests may need `OPENBLAS_NUM_THREADS=1` on memory-constrained Windows systems.

## Security decisions

The original CSP is retained: script and style sources remain self only, without
unsafe-inline or unsafe-eval. Charts and progress indicators use local CSS/native
elements rather than runtime style injection. Zod runs with JIT disabled to avoid
its dynamic-code path under `script-src 'self'`. Sonner's pinned runtime CSS injection
call is removed at build time and its official stylesheet is bundled as a local
asset. The build fails if that known injector format changes.

The new overview performs no writes, rejects unknown/duplicate query parameters,
uses token identity and existing membership rules, and excludes unrelated ledger
records. Totals include all permitted records instead of just the first API page.
An approved-but-edited or expired draft is not counted as currently approved.
Outbox acceptance is distinct from actual external delivery. SENTINEL's model mode
is read from its report; synthetic stub results do not prove live-model security.

All new rendering uses text nodes, with a lint gate against raw HTML injection.
Security-critical modules were not changed. Known architecture limitations and
proposed follow-ups are in [the architecture review](../docs/architecture-review.md).

Dependency versions are pinned in `frontend/package.json` and `package-lock.json`.
A minimatch 11.0.1 override addresses the lint tool's glob amplification advisory.
Direct dependency versions and licences are in [frontend dependencies](../docs/frontend-dependencies.md).

Latest validation: 52 backend tests passed (including all 27 SENTINEL scenarios),
frontend typecheck/lint/build passed, and 21 Playwright tests passed with no CSP
violations. Playwright captures 16 role/resolution/theme screenshots under
`frontend/test-results/screenshots/`.
