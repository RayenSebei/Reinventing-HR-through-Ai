# Dashboard v2 implementation plan

## Checkpoint and scope

Work is on `feature/dashboard-v2`. Phase 1 ends at a visual approval checkpoint,
as requested. The existing workflow remains available at `/legacy` until its
replacement passes the later phases. Do not reset the user's existing database.
Use a separate data directory for browser walkthroughs.

Phase 0: inspect tooling, API, schema, ledger producers, and constraints.
Phase 1: React/TypeScript shell, live Command Center, read-only scoped overview,
test coverage, both themes, committed build and screenshots.
Phase 2: evidence workspace and ranking/compare.
Phase 3: approvals and linked ledger.
Phase 4: assurance, presenter mode, final accessibility and workflow pass.
Phase 5: volume generator and missing modules require separate approval.

## API map

| Surface | Existing APIs | Access / behavior |
| --- | --- | --- |
| Session | POST auth/login; GET auth/me, users, meta | Identity from bearer token; meta is public |
| Cases | GET/POST cases; GET cases/:id | Members; auditors/admins can read all |
| Scorecard | PUT cases/:id/criteria; POST criteria/confirm | Recruiter membership required |
| CVs | GET/POST cases/:id/candidates; GET candidates/:id/dossier | Multipart PDFs; confirm criteria first |
| Evidence | GET documents/:id/extraction, findings, pages/:n.png | Same case scope; text must be rendered as text |
| Ranking | GET/POST cases/:id/ranking; POST ranking/:version/confirm | Human confirmation; frontend top-three review gate |
| Actions | GET/POST cases/:id/proposals; GET/PATCH proposals/:id | Draft is not execution |
| Approval | POST proposals/:id/approve, reject, execute | Exact payload hash, expiry, single use; no optimistic updates |
| Outbox | GET cases/:id/outbox | Sandbox acceptance and actual external delivery are distinct |
| Ledger | GET ledger?case_id=; GET ledger/verify | Global verification only auditor/admin |
| Assurance | GET assurance/latest, status; POST assurance/run | Global synthetic report; status exposes running boolean only |
| New overview | GET dashboard/overview[?case_id=] | Token-derived scope, strict query validation, no writes |

## Data definitions

- Counts aggregate all accessible rows, not a paginated first page.
- Security findings exclude MODEL_FALLBACK (a model availability notice).
- Gateway refusals count EXECUTION_DENIED ledger events, not candidates.
- Sent means accepted into the outbox through the gateway. External delivery is
  reported separately; SANDBOX_ONLY is never presented as a real delivered email.
- Approved means the latest approval matches, is unexpired, unused, and approved.
  Stored status alone is insufficient after an edit. Rejected, expired and changed
  approvals remain visible as distinct states.
- Pipeline stages declare their units. Confirmed shortlist counts distinct
  candidates in the current confirmed rankings, not historical versions.
- Pending drafts have no expiry timer. The expiry clock starts at approval.
- Assurance numbers and model mode come from the report, never from runtime meta.
- Recent activity excludes unrelated cases and global events for ordinary members.

## Security decisions

Try the committed build with the existing CSP first. Do not enable inline script,
eval, remote fonts, or remote assets. Prefer SVG presentation attributes and CSS
for charts. If component style attributes require it, add only the explicitly
authorized `style-src-attr 'unsafe-inline'`, with tests and documentation.
The shadcn chart style injector must be replaced by static CSS, never raw HTML.
All CV-derived content must have `dir="auto"` and use React text interpolation.
Queries must be scoped by the authenticated user, including cache keys and retries.

## Tooling inspection

Playwright and shadcn MCP registrations were added. This active chat does not yet
expose their newly registered tools; use the available browser integration and
the official pinned shadcn CLI for the current checkpoint. A new Codex session
loads the registrations. Node dependencies use exact versions and a lockfile.

Impeccable commit `4f956490f0056ae1ff5ea80372cf56e83c001d3c` was inspected.
Its current launcher downloads and executes a binary at runtime; do not enable
that launcher or its hooks under this brief. Apply the inspected static design
and critique guidance manually. The specified fallback GitHub repository returned
repository-not-found. No third-party runtime design hooks are enabled.

## Validation

Run original tests at every phase; new tests cover scope, totals beyond page size,
effective approvals, empty data, malformed query parameters, script CSP, no writes,
and frontend text-only rendering. Use an isolated demo database for UI checks.
Run typecheck, lint, production build; verify the production build's CSP and browser
console, all four roles, keyboard navigation, and dark/light at 1920×1080 and
1280×720. Commit images and build. Audit notes live in architecture-review.md.

## Risks and boundaries

SQLite and synchronous PDF/model work suit a single-process demo, not a proven
high-volume deployment. Never claim otherwise. A request to improve the whole
project does not silently override the supplied non-negotiable restrictions on
backend changes. Document protected-path fixes for explicit follow-up approval.
