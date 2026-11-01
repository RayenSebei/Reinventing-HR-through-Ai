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
| 2026-11-01 | `VOUCH_DEMO_MODE=1` is required for the `demo1234` password; without it `--seed` prints a one-time random password. Demo mode is refused with live outbound. | WA-02. **Changes the demo start command.** |
| 2026-11-01 | ~~Changing criteria after analysis re-evaluates every CV (RB-05).~~ **Superseded by main:** criteria are locked once evidence exists (`CRITERIA_LOCKED`). Migration 3 (`evidence_archive`) stays reserved so numbering is stable. | The team chose Rayen's dashboard as the final product; its lock also removes the FK crash (G9). |
| 2026-11-01 | The review gate needs the top `VOUCH_REVIEW_TOP_N` (default 3) plus every flagged candidate, opened by the confirming user through the dossier route, for the current document SHA. | HI-03; matches the existing UI rule, now enforced by the server. |
| 2026-11-01 | No new columns on existing tables: new data goes into new tables. | Existing code inserts with positional `VALUES (?,...)`; a new column would break it. |
| 2026-11-01 | n8n Remove Duplicates not added; Vouch's "never re-send a DELIVERED row" is the guarantee. | Its webhook answer on a dropped duplicate is not defined in the source read (R25). |
| 2026-11-01 | SENTINEL runner helpers (`sentinel_hr/scenarios_hr.py`: `shortlist`, `proposal`) perform the two new human steps. The scenario library (`sentinel/scenarios`) is untouched. | Setup must follow the new rules; no check was weakened. |
| 2026-11-01 | Secret scan: one reviewed history exception (`tools/secret_scan_allow.txt`): test-only Playwright keys in `da86ad92` on `feature/hr-workspace-p0-p3`. Exceptions name one commit and one file. | CI flagged it; the value is a labelled test placeholder, not a leaked credential. |
| 2026-11-01 | Merged onto main (dashboard = final product). One demo flag: `VOUCH_DEMO_MODE=1` (main's name) both shows the sign-in shortcuts and allows the `demo1234` password; `VOUCH_DEMO` is gone. | Two flags for one idea would confuse the demo. |
| 2026-11-01 | Review gate (HI-03) also guards main's explicit shortlist route: every selected candidate must have been opened by the confirming recruiter. Demo seeding calls the service directly and is not gated. | Main replaced "confirm whole ranking" with an explicit selection. |
| 2026-11-01 | Dashboard Actions tab: recruiter confirms the recipient (prefilled with the CV suggestion) before "Create draft" is enabled (D11). | Without it the new gateway check would block the dashboard flow. |
| 2026-11-01 | Secret scan: a `tree <path>` exception for `vouch/frontend/playwright.config.ts` (now on main). It only exempts lines containing `not-for-production`; any other key in that file is still reported (tested). | Same reviewed test-only keys as the history exception. |
| 2026-11-01 | Approving needs `payload_sha256` (the version the manager was shown). Rejecting does not. A recruiter still gets 403 before any body check. | External review P0: an edit between "view" and "approve" was approved silently. |
| 2026-11-01 | Login throttle keyed by (account, client address), plus a per-client cap for password spraying. | External review P1: anyone could lock the manager out. Behind a reverse proxy this needs the real client address. |
| 2026-11-01 | interview-chat refuses a placeholder or short `IB_SECRET_KEY` (exit at start). | External review P0: copied `.env.example` made staff tokens forgeable. **Changes start-up: an old `.env` with `change-me` must be fixed.** |
| 2026-11-01 | HR assistants (F1–F5) are rules/search based, no AI model, each behind `FEAT_<NAME>_MODE=off|on` (default on). No `shadow` mode: they only read data or create drafts that still need the manager's approval. | Works offline for the demo; honest about "no AI model". |
| 2026-11-01 | Reply drafts are a new proposal kind `reply`, built server-side only (`gateway.create_proposal(..., composed=...)`, never from a request body) and approved like every other action. The candidate's text, links and the original subject are never copied into a reply. | No second send path; Vouch cannot be used to relay attacker content. |
| 2026-11-01 | An inbound message is linked to a candidate only through a recruiter-confirmed address (D11), never through the CV address or the display name. | A stranger can claim any name. |
| 2026-11-01 | Demo seed sends two invitations through the real gateway (sink mode only; skipped with live outbound) and moves their send times back (4 days, 1 day) so "waiting for a reply" has data. The ledger keeps the true times. | Demo needs an overdue case; seeding never e-mails anyone. |
| 2026-11-01 | HR handbook = fictional company (`vouch/policies/*.md`). Answers are the quoted section; abstain below a score and coverage threshold or on personal questions. | An abstention sends the employee to HR; a wrong answer misleads them. |
