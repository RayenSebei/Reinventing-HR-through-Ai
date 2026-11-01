# Ground truth (Phase 0) — verified 2026-11-01 against commit `6d298e8`

Verdicts: **CONFIRMED** (as the master plan says) · **PARTIAL** (true with a correction) · **WRONG**. Evidence is file:line at `6d298e8`. "Status now" says what this branch changed.

| # | Verdict | Evidence | Note / status now |
|---|---|---|---|
| G1 | CONFIRMED | `vouch/app/main.py` (Starlette, not FastAPI), `db.py:106-110` WAL + FK; `interview-chat/interview_bot/*` own stack | Starlette, not FastAPI: plan wording corrected. |
| G2 | CONFIRMED | `documents.py:141` `%PDF` check, `:153` `MAX_PAGES`; `config.py` 5 MB | Unchanged (Phase 3). |
| G3 | CONFIRMED | `config.py` `MODEL_MODE` default `lexicon`; `sentinel_hr/runner.py` spawns with `VOUCH_MODEL=stub` | Unchanged (Phase 4/10). |
| G4 | PARTIAL | `evidence.py:145` `kind=="experience"` only adds a date-conflict note; no duration logic; no negation handling found | Repetition without context is already `NEEDS_REVIEW` (`evidence.py:87`). |
| G5 | CONFIRMED | `ranking.py` pure function of statuses; one template sentence | Unchanged (Phase 4). |
| G6 | CONFIRMED | `schemas.py` `ProposalCreate.kind` Literal of 2; `gateway._valid_start` now+3 days 10:00 UTC | Unchanged (Phase 5). |
| G7 | CONFIRMED | `cases.py:109` first regex email from CV text → `candidates.contact_email` → `gateway.create_proposal` payload `recipient` | **Fixed (D11):** recipient must be confirmed by a recruiter; CV address is only a suggestion. |
| G8 | PARTIAL | `gateway.execute`: approval/expiry/hash checked before the transaction; single use was already atomic (`UPDATE ... used_at IS NULL` + rowcount); the outbox stored the payload that was checked; no retry on failure | **Fixed:** payload re-read inside the transaction; DB trigger backstop; human retry with attempts recorded. |
| G9 | CONFIRMED | `set_criteria` deletes `criteria` rows referenced by `evidence_items` → `sqlite3.IntegrityError: FOREIGN KEY constraint failed` (reproduced, `evidence/red_run_phase1_2.txt`); review gate only in `static/app.js:274`; analysis inside the request | **Fixed:** FK crash and server-side review gate. Synchronous analysis unchanged (Phase 3). |
| G10 | CONFIRMED | `model.py:55` fixed `<cv_text>` tag, no boundary/canary | Unchanged (Phase 4). |
| G11 | CONFIRMED | Vouch: NFKC only (`documents.py:58`, `evidence.py:20`), Tag block not stripped; interview-chat `textutil.py:7` `ZERO_WIDTH` includes U+200C/U+200D and is deleted blanket (`ingestion.py:151`) | Unchanged (Phase 3). |
| G12 | CONFIRMED | `.github/workflows/checks.yml` ran only `vouch` pytest + frontend build | **Fixed:** CI runs `python -m tools.verify --all` (all suites + drill) and the secret scan. |
| G13 | CONFIRMED | No inbound mail, digest, reply handling, follow-up detection or employee Q&A code | Unchanged (Phases 5–7). |
| G14 | CONFIRMED | `vouch/frontend/src` Command Center only; other screens in `vouch/static/app.js` | Legacy UI updated for the new human steps. |
| G15 | CONFIRMED | `seed.py` hard-coded `demo1234`; `config.py` random JWT secret per process; no kill switch (`SANDBOX_ONLY` only when no n8n URL) | **Fixed:** `VOUCH_DEMO=1` required for the demo password; `VOUCH_OUTBOUND_MODE` kill switch (default `sink`). JWT secret behaviour unchanged. |
| G16 | CONFIRMED | `ledger.py` chain lives in the same SQLite file | Unchanged (Phase 10). |
| G17 | CONFIRMED | Demo PC: Windows x64 (`desktop-t9fdqni`), Node 24.22.0 in the desktop app. Its Linux VM has Python 3.10 and Tesseract, **no PyPI access** | Tests were run in a cloud workspace (see BASELINE.md). |
| G18 | CONFIRMED | Official n8n source `n8n-io/n8n@c44bd78` (n8n 2.46.0): Webhook auth only basic/header/jwt/none; Send Email cannot set `In-Reply-To`; **Send Email ≥ 2.1 appends an n8n attribution line by default** (`EmailSend/v2/send.operation.ts`) | **Fixed:** `appendAttribution: false`; double-HMAC comparison. See N8N_VERIFICATION.md. |

## Security-table rows touched in this pass (master Section 6)

| ID | Was | Now |
|---|---|---|
| AG-02 recipient from CV text | PARTIAL | DONE (D11 confirmation + execute re-check + fuzzer I5) |
| OB-03 header/CRLF/BCC | VERIFY | DONE for Vouch side (one-address validator on confirm and edit; workflow lint: no CC/BCC) |
| HL-01/HL-02 | DONE | DONE + DB trigger backstop + in-transaction re-read |
| HL-04 deceptive presentation | PARTIAL | PARTIAL: n8n no longer appends unapproved text; exact-bytes preview not built |
| HL-07 kill switch | PARTIAL | DONE |
| WA-02 default credentials | PARTIAL | DONE |
| DL-06 secrets | VERIFY | DONE (stdlib scanner, tree + history, in CI) |
