# Phase 1 checkpoint

The new Command Center runs at `/`. Existing operational screens remain at
`/legacy` with context-preserving navigation until Phases 2–4 are approved.

Implemented: token-scoped aggregate API, real metrics, pipeline, security findings,
role-specific attention queue, ledger activity, report-labelled SENTINEL gauge,
case filter, demo role switch, command palette, local fonts and dark/light themes.

Validation: 29 Python tests passed (19 existing, including 24 synthetic attack
scenarios; 10 dashboard tests). Frontend typecheck, lint and production build passed.
The production browser showed no CSP errors during login or command-palette use.
Screenshots use an isolated preview database with two real fixture uploads through
the API. They are not the user's working database. No volume-proof claim is made.

Review limitation: two independent reviewers were launched with user consent. They
identified small text and missing legacy deep links, both corrected. Their runs
then ended with a usage-limit error; the final pass was performed by the primary
agent. The Impeccable executable/detector was deliberately not enabled because its
runtime binary download conflicts with the brief. No automated detector pass is claimed.

Remaining: full replacement of candidate/ranking, approval, ledger and assurance
screens; presenter mode; complete browser walkthrough on those new screens. The
Phase 1 visual approval checkpoint precedes that work. The existing backend and
classic screens remain usable. See architecture-review.md for deferred backend fixes.
