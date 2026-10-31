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

## Phase 2 — approved direction implemented

New case/scorecard editor, paginated candidate table with search/filter/sort,
source overlays, honest X-ray extraction view, ranking breakdown, comparison
drawer and top-dossier review gate. Role switches clear the review gate.
Criteria editing is disabled after CV analysis to avoid the existing foreign-key
failure while preserving evidence. No security backend modules changed.

Validation: 29 Python tests; TypeScript, lint and production build passed.
Browser inspected real clean and adversarial dossiers, X-ray, source overlays,
keyboard dismissal and generated ranking; no console or CSP errors.
Screenshots: docs/screenshots/phase2-*.jpg.
Windows required GOMAXPROCS=2 and GOMEMLIMIT=256MiB for the bundler.
Approvals, ledger, assurance and the complete walkthrough follow in Phases 3–4.
