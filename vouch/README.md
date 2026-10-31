# Vouch

**An AI helper that screens CVs for a recruiter, can't be tricked by a CV, and can't send anything a manager didn't approve.**

All data is synthetic. Nothing here contacts real people.

## Run it (5 minutes)

You need **Python 3.11 or newer**.

```bash
cd vouch
pip install -r requirements.txt
python -m app --seed            # creates 4 demo users + a demo job, then starts the server
```

Open **http://127.0.0.1:8000** and use the quick sign-in buttons. Every demo password is `demo1234`.

| Demo user | Role | What they can do |
|---|---|---|
| recruiter@vouch.demo | Recruiter | criteria, upload CVs, rank, draft emails, send approved emails |
| manager@vouch.demo | Hiring manager | approve or reject drafted emails |
| auditor@vouch.demo | Auditor | read everything, check the ledger |
| admin@vouch.demo | HR admin | read everything, check the ledger |

Run the tests: `python -m pytest -q` (from `vouch/`). This includes all 24 SENTINEL attacks.

## The 5-minute demo

1. **Recruiter, tab 2:** upload `sentinel/datasets/clean_cvs/clean_cv.pdf` and `adversarial_cvs/white_on_white.pdf` (plus `hidden_text.pdf`).
   The trick CV shows a **red box** where the invisible text is, and the alert explains it. The hidden words never count as evidence.
2. Click each candidate. Every criterion shows an **exact quote** from the CV (green box on the page), or "not found".
3. **Tab 3:** "Rank candidates on evidence". Each score comes with its reasons. Confirm only after opening the top dossiers.
4. **Tab 4:** draft an interview invitation. Nothing is sent yet.
5. Switch to **manager** and press "Approve this exact content".
6. Switch back to **recruiter**, press "Change time (+2 h)", then "Send through the gateway".
   **The gateway refuses it:** the content changed after approval. (Draft again, approve, send, and it goes to the outbox.)
7. **Assurance tab:** run the SENTINEL scenarios. SENTINEL attacks a separate copy of Vouch and shows the results live.

Backup plan: record steps 1–7 once as a video before the pitch.

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

The v2 Command Center is available at `/`; the operational workflow remains at
`/legacy` during the phased migration. All metrics come from the authenticated,
case-scoped overview API. The current checkpoint is Phase 1; candidate evidence,
ranking, approvals and other screen migrations follow visual approval.

The committed `static/app/` build runs with Python alone. To develop the frontend:

```sh
cd frontend
npm ci --ignore-scripts
npm run typecheck
npm run lint
npm run build
```

Use Node 24. `npm run dev` proxies `/api` to port 8000. The production build is the
CSP verification target. Vite 7.3.7 is pinned because Vite 8's native bundler failed
memory allocation on the demo laptop. Tests may need `OPENBLAS_NUM_THREADS=1` on
memory-constrained Windows systems.

## Security decisions

The original CSP is retained: script and style sources remain self only, without
unsafe-inline or unsafe-eval. The shadcn chart's generated style injector was
removed; chart colours come from the local stylesheet. Sonner's pinned runtime
CSS injection call is removed at build time and its official stylesheet is bundled
as a local asset. The build fails if that known injector format changes. No CSP
exception was needed in the browser checks performed for this checkpoint.

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
