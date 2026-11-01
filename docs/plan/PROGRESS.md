# Progress

Branch `vouch-hardening` on top of `6d298e8`. Updated 2026-11-01.

## Gate 0 — PASS
Baseline green (29 / 36 / 24), every G row has a verdict (GROUND_TRUTH.md), no application file changed before the red test run was recorded.

## Phase 1 — partly done
| ID | Status | Proof |
|---|---|---|
| R21 migrations (`schema_migrations`, additive, new tables only) | DONE | `app/migrations.py`; readyz shows `schema_version` |
| RB-03 `busy_timeout`, in-transaction re-read in execute | DONE | `db.py`, `gateway.execute`; fuzzer |
| RB-09 / RB-06 `/api/healthz`, `/api/readyz` (integrity, ledger, schema, writable) | DONE | `test_healthz_and_readyz` |
| RB-14 config validation, fail-fast start, `.env.example` | DONE | `test_config_and_n8n.py` (9 cases) |
| HL-07 kill switch `VOUCH_OUTBOUND_MODE=disabled|sink|live` (default sink) | DONE | 3 tests, drill row, fuzzer I4 |
| WA-02 demo password only with `VOUCH_DEMO=1` | DONE | 2 tests |
| DL-06 secret scan (tree + history), in CI | DONE | `tools/secret_scan.py`, 4 tests |
| TQ-04 CI runs all suites + drill + secret scan | DONE (not yet run on GitHub) | `.github/workflows/checks.yml` |
| TQ-06 `python -m tools.verify --fast/--all` | DONE | `reports/verify_*.md` |
| RB-09 structured JSON logs with request IDs; injectable clock for new code | TODO | |
| SC-01 dependency hashes (`--require-hashes`) | TODO (needs PyPI access) | |
| AX-10 synthetic data generator skeleton | TODO | |

## Phase 2 — partly done
| ID | Status | Proof |
|---|---|---|
| D11 / HI-04 recipient confirmed by a human; CV address only a suggestion; one-address validation (OB-03, AG-02) | DONE | 12 tests, 3 drill rows, fuzzer I5 |
| HI-03 server-side review gate | DONE | 3 tests, drill row; legacy UI records the review when it opens a dossier |
| HL-01/HL-02 DB trigger: outbox needs a used, matching, non-self approval; one outbox row per proposal; outbox payload immutable | DONE | 2 tests, drill row, fuzzer I1/I2 |
| RB-05 criteria change after analysis (FK crash fixed, evidence archived, re-evaluated, shortlist superseded) | DONE | 2 tests, drill row |
| RB-07 human retry, same approved bytes, never twice once delivered, attempts recorded | DONE | 2 tests, drill row, fuzzer I9 |
| HL-04 n8n no longer appends unapproved text; double-HMAC check | DONE | 5 workflow lint tests, drill row; **import on a real n8n still to do** |
| HI-07 invariant fuzzer (I1, I2, I4, I5, I6, I9) | DONE | `test_invariants.py`; 300 sequences in CI; **10,000 sequences / 80,000 steps / 2,224 sends: 0 violations** |
| TQ-03 protection-removal drill | DONE (9 rows) | `python -m tools.drill` |
| HI-01 register enforced by a static test + decision-table triggers | PARTIAL (register written, not enforced by a test) | RECORD_REGISTER.md |
| HI-02 proposal kind registry | TODO | |
| HI-04 risk tiers, batch approval for low risk only, step-up for high risk | TODO | |
| HI-05 delegation / absence; HI-06 decision table; HL-03 rubber-stamping metrics | TODO | |
| OB-01/OB-02/OB-04 cross-candidate canary, commitment lexicon, link checks | TODO | |

## Next step
Finish the TODO rows of Phases 1–2, then Gate 2. Exact commands to resume:
```
python -m tools.verify --all
python -m tools.secret_scan --history
```

## Blockers
- PyPI is blocked in both environments available to the agent: dependency hashes (SC-01) and an exact-pin run need a machine with PyPI. Run `python -m tools.verify --all` on the Windows demo PC.
- n8n cannot be run here: import the workflow once (N8N_VERIFICATION.md).
- The companion `docs/security/HARDENING_PROMPT.md` is not in the repo; security IDs were applied from the master plan's wording.
