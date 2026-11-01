# Changelog (master plan)

`date | IDs | flag / setting | seam touched | tests added (red → green) | baseline | rollback`

| Date | IDs | Setting | Seam | Tests (red → green) | Baseline | Rollback |
|---|---|---|---|---|---|---|
| 2026-11-01 | R21, RB-03 | — | `db.connect` (busy_timeout, migrations), `db.wipe` keeps `schema_migrations` | readyz | 29/36/24 green | revert `db.py`, delete `migrations.py`; new tables are unused by old code |
| 2026-11-01 | RB-14, WA-02 | `VOUCH_DEMO` | `config.validate`, `__main__`, `seed` | 13 red → green | green | revert `config.py`, `seed.py`, `__main__.py` |
| 2026-11-01 | HL-07 | `VOUCH_OUTBOUND_MODE` (default `sink`) | `gateway._deliver` → `delivery.deliver` | 3 red → green | green | `VOUCH_OUTBOUND_MODE=live` restores sending; or revert `_deliver` |
| 2026-11-01 | D11, HI-04, AG-02, OB-03 | — (enforced) | `gateway.create_proposal`, `edit_proposal`, `execute`; new `contacts.py`, 2 routes | 12 red → green | green after runner helper update | revert the 3 gateway seams + routes |
| 2026-11-01 | HI-03 | `VOUCH_REVIEW_TOP_N` | `cases.confirm_ranking`; dossier route records the review; legacy UI opens the dossier after upload | 3 red → green | green after runner helper update | delete the `reviews.enforce` line |
| 2026-11-01 | RB-05 | — | `cases.set_criteria` + `_reevaluate_case` | 2 red → green (FK crash reproduced) | green | revert `set_criteria` |
| 2026-11-01 | HL-01/HL-02 backstop, I1, I2 | — | migration 5 (trigger, unique index, immutable payload) | 2 red → green | green | drop the two triggers and the index |
| 2026-11-01 | RB-07 | `VOUCH_MAX_DELIVERY_ATTEMPTS` | new `delivery.retry`, route `POST /api/outbox/{id}/retry`, UI button | 2 red → green | green | remove route |
| 2026-11-01 | HL-04, R25 | — | `n8n/vouch-deliver.workflow.json` (attribution off, double HMAC) | 2 red → green, 3 guard tests | green | restore the JSON from `6d298e8` |
| 2026-11-01 | HI-07, TQ-03, TQ-06, TQ-04, DL-06 | `VOUCH_FUZZ_SEQUENCES` | new `tools/`, tests, CI | fuzzer, drill 9/9, 4 scanner tests | green | delete files; restore `checks.yml` |
