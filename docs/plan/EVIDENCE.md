# Evidence

`ID | claim | red run | green run | metric vs threshold | residual risk`
Every green claim below is reproduced by `python -m tools.verify --all` (latest table: `reports/verify_2026-11-01.md`).

| ID | Claim | Red run | Green run | Metric | Residual |
|---|---|---|---|---|---|
| G9 / RB-05 | Editing criteria after CVs were analysed no longer crashes and keeps the old evidence | `evidence/red_run_phase1_2.txt`: `sqlite3.IntegrityError: FOREIGN KEY constraint failed` | `test_criteria_change_after_analysis_keeps_working`, `..._supersedes_confirmed_shortlist` | drill row red when removed | — |
| D11 / HI-04 / AG-02 | No proposal until a recruiter confirms the address; CV address is a suggestion; execute refuses a recipient that differs | red run: 409 never returned | 5 tests + `RECIPIENT_NOT_CONFIRMED` | fuzzer I5: 0 violations; 2 drill rows red | — |
| OB-03 | Only one clean address is accepted (no CR/LF, commas, semicolons, names, NUL) on confirm and on edit | red run: accepted | 8 parametrised cases + edit test | drill row red | n8n still receives a string; Vouch guarantees its shape |
| HI-03 | Shortlist confirmation needs the confirming user to have opened the top N and flagged dossiers via the API | red run: 200 without any review | 3 tests | drill row red | — |
| HL-01/HL-02 backstop | The database refuses an outbox row without a used, matching, non-self approval, and a second row per proposal | red run: inserts accepted | 2 tests | drill row red; fuzzer I1/I2 | — |
| HL-07 | `disabled` holds, `sink` never calls n8n, `live` calls once | red run: no such setting | 3 tests | drill row red; fuzzer I4 | — |
| RB-07 | Retry re-sends the same approved bytes, never after DELIVERED, attempts recorded | red run: no retry route | 2 tests | drill row red; fuzzer I9 | lost-answer duplicate (RESIDUAL_RISK.md) |
| HL-04 / R25 | n8n sends exactly the approved text (no attribution) and never compares raw signatures | red run: `appendAttribution` absent, raw compare | 5 workflow lint tests | drill row red | not yet run on a real n8n |
| RB-14 / WA-02 | Unsafe settings refuse to start; no known password without `VOUCH_DEMO_MODE=1`; secrets never printed | red run: `config.validate` missing | 13 tests | — | — |
| DL-06 | Planted keys are found in tree and history; this repo is clean | — (tool is new) | 4 tests; `secret scan: 0 finding(s)` | — | history here was shallow; CI uses full history |
| HI-07 | Random sequences of real API actions never break I1, I2, I4, I5, I6, I9 | the fuzzer catches the removed recipient re-check with a replayable seed (drill) | `test_invariants.py` | see below | other invariants need later phases |
| TQ-03 | Each listed protection, when removed, turns its tests red | — | `python -m tools.drill` | **15/15 red** | — |
| UI | Legacy UI completes login → upload → shortlist → recipient prompt → propose → approve → send | — | headless Chromium run, 0 console errors | — | not yet a committed Playwright test (Phase 8) |

## Fuzzer runs
| Sequences | Steps | Successful executions | Live transport calls | Violations | Time |
|---|---|---|---|---|---|
| 300 (CI default) | 2,400 | 60 | 30 | 0 | 11 s |
| 1,000 | 8,000 | 210 | 115 | 0 | 19 s |
| 3,000 | 24,000 | 686 | 435 | 0 | 89 s |
| **10,000** (Gate 2 target) | 80,000 | 2,224 | 1,259 | **0** | 16 min 21 s (`evidence/fuzz_10000.txt`) |

Labels: all results here use the `stub` model (SENTINEL) or `lexicon` (Vouch tests). No real-model result is claimed.

## External review findings (2026-11-01), branch `fix/review-findings`
Red run for all of them: `evidence/red_run_review_findings.txt` (23 failed, 2 passed before the fixes). Tests: `vouch/tests/test_review_findings.py`, `interview-chat/tests/test_secret_key.py`.

| Finding | Claim now | Red run | Green run | Drill | Residual |
|---|---|---|---|---|---|
| P0 approval not tied to viewed content | Approve needs `payload_sha256` of what the manager saw; re-checked inside the transaction | approve without hash → 200 | 4 tests | 2 rows red | — |
| P0 interview-chat placeholder key | `change-me`, other placeholders or < 32 chars stop the app; `.env.example` ships an empty key (random per start) | no check | 9 tests | — (other app) | — |
| P0 criteria edit → 500 | Already fixed on main: `CRITERIA_LOCKED` 409 | — | `test_dashboard.py` | — | re-scoring after a change needs a new case |
| P0 newline / Bcc in recipient or subject | Recipient: one clean confirmed address (D11). Subject: no C0/C1 control or U+2028/2029, ≤ 200 chars | `\u2028`, NEL, VT, TAB, NUL accepted | 6 cases | 1 row red | — |
| P1 oversized PDF page | Preview checks pdfium's own page size and pixel budget; analysis also checks pdfium's size | 14400 pt page rendered (~1.4 GB RGB) | 2 tests | 1 row red | — |
| P1 lockout of any account | Failures count per (account, client address) plus 30 per client for spraying | manager locked from every machine | 2 tests | 1 row red | behind a proxy all clients share one address |
| P1 non-manager raw text via extraction | Every role except recruiter gets PII-redacted text (auditor and admin were raw) | auditor/admin saw the e-mail | 3 cases | 1 row red | — |
| P1 negated mentions | English and French negations ("not familiar with", "haven't used", "aucune expérience", "jamais utilisé"…) are never evidence | 9 phrases counted | 10 tests | — | whole line skipped (conservative) |
| P1 PII filter `2019-2023` | Already fixed on main | — | `test_core.py` | — | — |
| P1 stub results | Reports, dashboard and README say `stub` | — | — | — | no real-model run yet |
| P1 `--seed` wipes / logs out | By design (`--yes` required); README now says start without `--seed`, set `VOUCH_JWT_SECRET` to keep sessions | — | — | — | — |

## HR assistants F1–F5 (2026-11-01), branch `feature/hr-assistants`
Red run: `evidence/red_run_assistants.txt` covers F4 and F3 (written before the code). F1/F2/F5 tests were written together with the code, not red first; the drill rows below are the proof that each of their protections is tested.

| Feature | Claim | Tests | Drill | Residual |
|---|---|---|---|---|
| F4 free slots | Suggested slots are in the future, on weekdays, inside working hours, never across lunch and never overlapping the interviewer's interviews/meetings or the candidate's interviews; a suggested slot can be booked | 12 | 1 row red | candidate's own availability outside Vouch is unknown |
| F3 replies waiting | Latest sent message per candidate is listed until a reply is recorded (manually or by an inbound message from the confirmed address); follow-up = approval-bound draft + task, idempotent, refused after a reply | 8 | 1 row red | no real mailbox |
| F1 inbox | Hidden HTML, instruction text, phishing language, look-alike senders, disguised/short/IP links, attachments and Reply-To mismatch are flagged; quoted chains, zero-width and bidi characters removed; ledger holds no text or address; links never fetched | 16 | 1 row red | rules, not a model; synthetic corpus only |
| F2 replies | Draft = facts only (role, next interview, free slots), no candidate text or links, neutral on sensitive topics, refused for flagged/unconfirmed senders, grounding check on every number/date/address/link, kind `reply` through approval | 7 | 2 rows red | fixed wording |
| F5 HR Q&A | Answer = quoted handbook section with its name; tuning set 18/18, held-out 15/16 (1 wrong), out-of-scope 6/6 refused, personal questions refused; ledger keeps only a hash | 30 | 1 row red | small synthetic question sets |
| UI | Headless-browser walk-through: inbox (digest, reply draft, phishing flags, .eml upload), follow-ups (overdue + draft), interviews (suggested slot booked), HR assistant (answer, abstain, French), approvals (reply + follow-up visible), light/dark, 390 px width without horizontal scroll | — | — | one CSP console message when the Schedule dialog opens; it also happens on `main` (existing dialog component) |
