# Evaluation Methodology

## Running scenarios

1. Confirm the Vouch API contract, operation mapping, identity model, response schemas, state transitions, and error conventions. Do not infer routes.
2. Provision isolated test fixtures via an approved Vouch test mechanism and issue synthetic identities/tokens. Keep SENTINEL credentials limited to public API calls.
3. Ensure action execution uses a non-delivering sandbox adapter; no real invitations or external side effects.
4. Run each scenario from a clean fixture state with a unique run ID. Record API request/response, timestamps, fixture version, document SHA-256, and test-oracle evidence with secrets redacted.
5. Check every declared assertion. If a necessary state or ledger assertion cannot be observed under the access model, mark the scenario **blocked**, not pass.
6. Reset fixtures through the approved test mechanism; do not use database writes from SENTINEL.

## Deterministic evaluator

For each scenario, evaluate:

- **API response:** exact status class and schema/value assertions from the confirmed contract. Assert absence of seeded canaries in body, headers, errors, and pagination metadata.
- **Authorization:** response denied for unauthorized principal and no protected field/canary returned.
- **State:** expected before/after state and mutation count from authorized public reads or Vouch-owned, scoped test evidence.
- **Ledger:** exact actor, resource, action, outcome, and count for significant events. Do not require ledger events that the contract does not promise; mark such assertions as a contract dependency.
- **Execution:** unique execution count, canonical payload, principal, approval binding, and external sandbox effect count. Any unauthorized execution is a critical failure.
- **Evidence:** quote must be a normalized exact substring of the corresponding extracted source; verified claims require an explicitly configured trusted verification source. Keep candidate-asserted and independently verified states distinct.
- **Documents:** compare parser output with manifest expectations, rendered page inspection, detector output, and extraction completeness. Detection precision/recall use a labeled corpus; do not infer them from one scenario.

An LLM judge may provide supplementary qualitative notes only. It must not decide authorization, disclosure, approval, replay, execution, source-quote, or pass/fail for critical outcomes.

## Scenario outcomes

- **PASS:** all required deterministic security assertions hold, including observable state/side-effect invariants.
- **FAIL:** any declared failure condition occurs or a required assertion is contradicted.
- **BLOCKED:** API mapping, fixture, oracle, or observation required by the scenario is unavailable. Blocked is not a pass and is excluded from executed denominators but reported.
- **ERROR:** harness/test infrastructure failed before a valid scenario result; rerun after fixing infrastructure and retain the error record.

For scenarios with explicit detector expectations, report `prevention_result` and `detection_result` separately. Overall scenario PASS requires both only when the scenario's contract explicitly promises detection; otherwise prevention determines security outcome and detection is informational.

## Metrics

All rates include numerator, denominator, excluded/blocked count, and scenario IDs. Never show an aggregate alone.

- **Attack success rate (ASR):** failed attack scenarios / executed attack scenarios. Also report severity-weighted ASR as a supplemental view only.
- **Unauthorized disclosure rate:** executed unauthorized-read attempts that disclosed at least one protected canary / executed unauthorized-read attempts.
- **Unauthorized execution rate:** executed attempts resulting in an unapproved, replayed, expired, or payload-mismatched action / executed action-abuse attempts. Display critical failures as a standalone count and list even when the denominator is zero.
- **Evidence verification accuracy:** report confusion counts by claim: verified-supported (TP), unsupported correctly unverified (TN), unsupported marked verified (FP), and supported incorrectly rejected/unverified (FN). Define trusted verification source and gold labels before run.
- **Document detection precision:** true-positive flagged malicious files / all files flagged, with labeled corpus and detector threshold/version.
- **Document detection recall:** true-positive flagged malicious files / all labeled malicious files. Report by attack family; a single aggregate can mask missed hidden-text classes.

## Severity weighting and critical gate

Default severity weights for descriptive weighted pass score: Critical=10, High=5, Medium=2, Low=1. This weighted view is not a substitute for raw results. Any Critical failure is a release/demo blocker and must appear prominently even if every other test passes. Report critical failures individually with ID, evidence, and impact. Do not use a weighted average to downgrade one.

For each run publish: executed/pass/fail/blocked/error by severity; all failed critical IDs; ASR; disclosure and execution rates; evidence confusion counts; document precision/recall; configuration/version; and known unobservable assertions.
