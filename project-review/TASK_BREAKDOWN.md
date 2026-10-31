# TASK_BREAKDOWN

Priority: **P0** = needed for M1 (h7) · **P1** = needed for M2 (MVP, h12.5) · **P2** = hardening/demo · **P3** = post-hackathon.
Owner: **A** backend, **B** frontend + assurance (2-person plan). Estimates are rough planning figures.

## Pre-event / h0

| ID | Task | Owner | Pri | Est | Depends | Done when |
|---|---|---|---|---|---|---|
| T00 | Commit headcount + person→module split in `DECISIONS.md` | All | P0 | 0.25h | — | Everyone named |
| T01 | Verify Python 3.12 + Node 20 + `uv` on every laptop | All | P0 | 0.25h | — | `python --version` = 3.12.x |
| T02 | Model bake-off (9 fixtures + 3 FR/AR/mixed CVs) | A | P0 | 1h | T01 | Model chosen, numbers recorded |
| T03 | ~~Inventory `sentinel/`~~: **done** in this review (SCENARIO_MAPPING.md). Agree the mapping as a team | B | P0 | 0.25h | — | Mapping accepted |
| T03b | Create the 3 missing fixtures (AI-001 paired CVs, AI-004 contact-canary CV, EI-004 canary docs) + off-page and metadata fixtures | B | P1 | 1h | — | Files + manifest entries |
| T03c | FR / AR / mixed CVs with reportlab + embedded TTF; check by rendering | B | P1 | 1h | — | Arabic renders correctly |
| T04 | Write approval-semantics table (D10) + organizer questions | A | P0 | 0.25h | — | In README draft |
| T05 | Create 3 multilingual synthetic CVs + 1 job offer | B | P1 | 0.5h | — | PDFs in `fixtures/` |

## H1 — contract

| ID | Task | Owner | Pri | Est | Depends | Done when |
|---|---|---|---|---|---|---|
| T10 | Repo layout, Makefile, ruff/mypy, pytest config | A | P0 | 0.25h | T01 | `make test` runs |
| T11 | Pydantic schemas + route stubs for all §6 routes; typed error enum | A | P0 | 0.5h | T10 | `openapi.json` exported |
| T12 | Generate TS client; Vite + React shell; router | B | P0 | 0.5h | T11 | Client compiles |
| T13 | Seed script: 4 users (one per role), 2 cases, memberships | A | P0 | 0.25h | T11 | `make seed` |

## H2 — walking skeleton (M1 at h7)

| ID | Task | Owner | Pri | Est | Depends | Done when |
|---|---|---|---|---|---|---|
| T20 | Login (argon2 + JWT cookie), `/auth/me`; base request model with `extra="forbid"` | A | P0 | 0.5h | T13 | Bad password → 401; unknown field → 422 |
| T21 | `require_case_scope()` dependency on every case route | A | P0 | 0.5h | T20 | AU-001 passes |
| T22 | Cases + criteria + confirm (weights sum to 100) | A | P0 | 0.5h | T21 | Ranking blocked until confirmed |
| T23 | Upload (multipart, size/magic check), SHA-256, read-only store, `jobs` table + worker thread | A | P0 | 0.75h | T22 | Job reaches DONE |
| T24 | Naive extraction (page text) + lexicon evidence | A | P0 | 0.5h | T23 | Dossier returns items |
| T25 | Deterministic ranking + breakdown | A | P0 | 0.5h | T24 | Same input → identical JSON |
| T26 | Proposals: canonical JSON + sha256; PATCH recomputes hash | A | P0 | 0.5h | T21 | Unit test on canonicalization |
| T27 | Approvals: role, scope, self-approval block, nonce, expiry | A | P0 | 0.5h | T26 | Unit tests per rule |
| T28 | Gateway: deny-by-default, hash check, atomic single-use, outbox write | A | P0 | 0.5h | T27 | AP-001, AP-003 pass |
| T29 | Ledger: chain + `/ledger/verify` + events from T22–T28 | A | P0 | 0.5h | T22 | Tamper test fails verify |
| T30 | UI: login, case list/detail, upload with progress | B | P0 | 1.5h | T12 | Click-through works |
| T31 | UI: shortlist table, proposal/approve/execute buttons, error toasts by code | B | P0 | 1.5h | T30 | Tamper shows "payload changed" |
| T31b | Test mode: `/_test/fixtures/{name}` loader (identities, cases, pre-built proposal states incl. executed and expired), A-AUDIT identity, prompt canary, model stub | A | P0 | 0.75h | T13 | Loader resets state |
| T32 | `sentinel_hr` runner: reads library YAML + **sidecar machine steps** (`mappings/<ID>.yaml`), HTTP executor, assertions on status/code/outbox/ledger, canary scan, JSONL trace, PASS/FAIL/BLOCKED/ERROR | B | P0 | 1.5h | T11, T31b | Runs one scenario |
| T33 | Implement PI-001, AU-001, AP-001, AP-003, EI-001 | B | P0 | 1h | T32 | 5 results recorded |
| T34 | **M1 gate**: E2E integration test + 5 scenarios run | A+B | P0 | 0.25h | all above | Green, or features stop |

## H3 — document security + verifier

| ID | Task | Owner | Pri | Est | Depends | Done when |
|---|---|---|---|---|---|---|
| T40 | Render (pypdfium2, 2×) + ink check per char, plus <4 pt and off-page, aggregated per word → visible/hidden text (prototype already validated in review) | A | P1 | 1h | T23 | 3/3 hidden fixtures flagged; 0 on the other 6 |
| T41 | Findings: instruction phrases (EN/FR/AR), keyword density, date contradictions, metadata oddities | A | P1 | 1h | T40 | 9/9 fixtures → expected finding; clean → 0 |
| T42 | Evidence verifier (normalize, exact, fuzzy) on visible text; UNSUPPORTED_CLAIM finding | A | P1 | 1h | T40 | EI-001 passes |
| T43 | pdf.js dossier view; quote → page highlight; hidden-text overlay; findings badges | B | P1 | 3h | T31 | Demo beat 2 works |

## H4 — AI + full ranking

| ID | Task | Owner | Pri | Est | Depends | Done when |
|---|---|---|---|---|---|---|
| T50 | `ModelAdapter` hosted → Ollama → replay; schema validate + 1 retry | A | P1 | 1h | T02, T42 | Kill network → replay used |
| T51 | PII minimizer (email, phone, URL, address, DOB, name header) | A | P1 | 0.5h | T50 | Redaction test |
| T52 | Ranking flags (borderline, finding badge); shortlist confirm | A | P1 | 0.5h | T25 | Confirm required before proposals |
| T53 | AI-drafted invite from candidate's own dossier | A | P1 | 0.5h | T50 | No cross-candidate data in prompt |
| T54 | Map remaining scenarios; mark BLOCKED/UNOBSERVABLE with reason | B | P1 | 1.5h | T33 | 24 rows in report |
| T55 | Assurance panel (results table, trace drill-down, timestamp) | B | P1 | 0.75h | T54 | Demo beat 4 works |
| T56 | "Open each top-N dossier before confirm" UX | B | P1 | 0.25h | T43 | Button disabled until viewed |

## H5–H6 — hardening and demo

| ID | Task | Owner | Pri | Est | Done when |
|---|---|---|---|---|---|
| T60 | Counterfactual fairness pairs test | A | P2 | 0.5h | Identical scores |
| T61 | Batch of N synthetic CVs: time it, write the measured number | A | P2 | 0.5h | Number in README |
| T62 | Error-path tests: expired, replay, self-approval, cross-case, schema-invalid | A | P2 | 0.5h | Green |
| T63 | CORS/CSRF/upload-limit/login-rate-limit check | A | P2 | 0.5h | Checklist ticked |
| T64 | README: run, architecture, approval semantics, what's tested / not tested, limits | B | P2 | 0.75h | Reviewed by A |
| T65 | Code freeze; fill replay cache; record backup video of both climaxes | A+B | P2 | 0.75h | Video file saved locally |
| T66 | Deck (problem, demo, architecture, honest limits, roadmap) | B | P2 | 0.75h | ≤ 8 slides |
| T67 | Two timed rehearsals, Wi-Fi off | A+B | P2 | 0.5h | < 5:00 twice |

## Cut list (in this order, if behind)

1. T56 → 2. T61 (state as "not measured") → 3. T54 beyond the 5 demo scenarios (report the rest as unmapped) → 4. T41 metadata/date checks → 5. T51 name redaction (keep contact redaction) → 6. Ollama tier (keep hosted + replay).
**Never cut:** T21, T26–T29, T33, T42, T65.

## P3 backlog (post-hackathon)

Postgres + Alembic · OIDC · object storage · CI assurance gate · email/calendar adapters with idempotency · DOCX + OCR · render-vs-OCR differential · inbox digest · draft replies · cited policy Q&A · tenant isolation · retention jobs · DPIA template · third-party scenario intake · signed assurance reports · customer interviews.
