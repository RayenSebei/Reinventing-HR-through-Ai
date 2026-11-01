# Decisions

D1–D11 are the master plan's defaults (Section 3), applied as written unless a row says otherwise. They need a human confirmation; silence = proceed with the defaults.

| # | Decision | Status |
|---|---|---|
| D1 | Vouch is the base; interview-chat stays separate | applied |
| D2 | Queue = SQLite table + worker processes | not started (Phase 3) |
| D3 | Search = SQLite FTS5 (available on both machines) | not started (Phase 7) |
| D5 | Sandbox drivers `docker` / `lite` | not started (Phase 3) |
| D10 | Decline messages only after a recorded human decision | not started (Phase 5); no decline kind exists today |
| D11 | Recipient of any candidate email confirmed by a human; CV address is a suggestion | **applied and enforced** |

## Decisions taken in this pass (please confirm)
| Date | Decision | Why |
|---|---|---|
| 2026-11-01 | Default `VOUCH_OUTBOUND_MODE=sink`. Live sending now needs `VOUCH_OUTBOUND_MODE=live` in addition to the n8n URL and secret. | Kill switch must fail safe (HL-07). Changes the n8n README's start command. |
| 2026-11-01 | `VOUCH_DEMO=1` is required for the `demo1234` password; without it `--seed` prints a one-time random password. Demo mode is refused with live outbound. | WA-02. **Changes the demo start command.** |
| 2026-11-01 | Changing criteria after CVs were analysed archives the old evidence, re-evaluates every CV against the new criteria, and supersedes the current draft/confirmed shortlist. | Fixes the FK crash (G9); a shortlist judged on old criteria must be confirmed again. |
| 2026-11-01 | The review gate needs the top `VOUCH_REVIEW_TOP_N` (default 3) plus every flagged candidate, opened by the confirming user through the dossier route, for the current document SHA. | HI-03; matches the existing UI rule, now enforced by the server. |
| 2026-11-01 | No new columns on existing tables: new data goes into new tables. | Existing code inserts with positional `VALUES (?,...)`; a new column would break it. |
| 2026-11-01 | n8n Remove Duplicates not added; Vouch's "never re-send a DELIVERED row" is the guarantee. | Its webhook answer on a dropped duplicate is not defined in the source read (R25). |
| 2026-11-01 | SENTINEL runner helpers (`sentinel_hr/scenarios_hr.py`: `shortlist`, `proposal`) perform the two new human steps. The scenario library (`sentinel/scenarios`) is untouched. | Setup must follow the new rules; no check was weakened. |
