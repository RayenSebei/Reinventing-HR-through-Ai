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
| RB-14 / WA-02 | Unsafe settings refuse to start; no known password without `VOUCH_DEMO=1`; secrets never printed | red run: `config.validate` missing | 13 tests | — | — |
| DL-06 | Planted keys are found in tree and history; this repo is clean | — (tool is new) | 4 tests; `secret scan: 0 finding(s)` | — | history here was shallow; CI uses full history |
| HI-07 | Random sequences of real API actions never break I1, I2, I4, I5, I6, I9 | the fuzzer catches the removed recipient re-check with a replayable seed (drill) | `test_invariants.py` | see below | other invariants need later phases |
| TQ-03 | Each listed protection, when removed, turns its tests red | — | `evidence/drill_run.txt` | **9/9 red** | — |
| UI | Legacy UI completes login → upload → shortlist → recipient prompt → propose → approve → send | — | headless Chromium run, 0 console errors | — | not yet a committed Playwright test (Phase 8) |

## Fuzzer runs
| Sequences | Steps | Successful executions | Live transport calls | Violations | Time |
|---|---|---|---|---|---|
| 300 (CI default) | 2,400 | 60 | 30 | 0 | 11 s |
| 1,000 | 8,000 | 210 | 115 | 0 | 19 s |
| 3,000 | 24,000 | 686 | 435 | 0 | 89 s |
| **10,000** (Gate 2 target) | 80,000 | 2,224 | 1,259 | **0** | 16 min 21 s (`evidence/fuzz_10000.txt`) |

Labels: all results here use the `stub` model (SENTINEL) or `lexicon` (Vouch tests). No real-model result is claimed.
