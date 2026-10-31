# RISK_ANALYSIS

Likelihood (L) and Impact (I) on a 1–5 scale are this review's judgment, not measurements. Score = L × I.

## Hackathon delivery risks

| # | Risk | L | I | Score | Mitigation | Trigger / owner |
|---|---|---:|---:|---:|---|---|
| R1 | Proof moments (gateway rejection, SENTINEL run) not working at demo time | 4→2 | 5 | 20→10 | Walking skeleton with M1 at h7; backup video; last real run report as fallback | M1 not green at h7 → stop features (A+B) |
| R2 | SENTINEL can't drive Vouch (simulator ≠ HTTP target) | 5→2 | 4 | 20→8 | New thin `sentinel_hr` runner from h1; contract-generated | Runner can't run 1 scenario by h4 (B) |
| R3 | Team size/model undecided → plan uncostable | 4→1 | 4 | 16→4 | T00/T02 before or at h0 | Not decided by h0:30 (all) |
| R4 | ~~Scenario library differs from the handover~~: **checked, matches** (24 / 10-9-4-1 / 9 PDFs). New risk: the scenarios are prose, and 3 need fixtures that don't exist | 4 | 4 | 16→6 | Sidecar machine steps; test-mode loader; build the 3 missing fixtures; SCENARIO_MAPPING.md | Any demo scenario not mapped by h4 (B) |
| R4b | French/Arabic claims untestable: the generator is ASCII-only | 5 | 3 | 15→6 | reportlab + TTF fixtures before the event; claim only languages actually tested | No FR/AR fixture at h0 (B) |
| R4c | Hidden-text detection misses render mode 3 with pdfplumber alone | 5→1 | 4 | 20→4 | **Fixed**: render + ink check, measured on the 9 fixtures | Regression test on `hidden_text.pdf` |
| R5 | LLM outage, rate limit or slow responses during the event or demo | 3 | 4 | 12→4 | 3-tier adapter; replay cache; demo offline | Hosted latency high in bake-off (A) |
| R6 | Poor FR/AR/mixed extraction → thin dossiers | 3 | 3 | 9 | Bake-off on multilingual CVs; lexicon fallback; NEEDS_REVIEW instead of invented claims | Verifier pass rate low on AR CV (A) |
| R7 | Forensic detector false positives on the clean CV | 3 | 3 | 9 | Golden test requires clean → 0; thresholds tuned; finding shows excerpt | Clean CV flagged (A) |
| R8 | Frontend squeezed → confusing demo | 3 | 3 | 9 | B starts UI at h1, not h11; one-product story | UI not clickable at h7 (B) |
| R9 | Python 3.11/3.12 mismatch breaks SENTINEL tooling | 2 | 2 | 4 | T01; runner avoids 3.12-only features | `uv sync` fails (all) |
| R10 | Scope creep (extra HR axes, chatbot) | 3 | 4 | 12 | Cut list; extra axes only after M2 and only in the 4-person variant | Anyone starts non-listed work before M2 |
| R11 | Judge asks "is it secure / independent?" | 4 | 3 | 12→3 | Scripted answer: "tested against N scenarios, X passed, Y unobservable; attacks are self-authored today; independence is on the roadmap" | — |
| R12 | Approval semantics challenged ("you recorded a draft") | 3 | 3 | 9→3 | D10 table in README; ask organizers at kickoff | — |

## Technical/security risks in the design itself

| # | Risk | Mitigation |
|---|---|---|
| S1 | Injection in **visible** text manipulates extraction | Containment: no LLM tools, schema output, verifier downgrades unsupported claims; finding is shown to the recruiter |
| S2 | Hidden-text detection evaded by an unanticipated technique (e.g. text-render mode, clipping paths, font tricks) | Hidden text is never trusted for scoring because only verified visible quotes count; the render-vs-OCR differential is a future upgrade; state the detection limits in the README |
| S3 | Canonicalization ambiguity (key order, unicode, floats) → hash mismatch or bypass | One canonicalization function shared by proposal and gateway; no floats in payloads (ISO datetimes, ints); unit tests |
| S4 | Race: double execution of one approval | Atomic conditional update on `used_at`; test with concurrent requests |
| S5 | Ledger rewritten by someone with DB write access | Described as tamper-evident only; head-hash anchoring as a future upgrade |
| S6 | IDOR on documents and dossiers | `require_case_scope` on every route that takes an ID; scenario AU-* covers it |
| S7 | Automation bias: recruiter rubber-stamps the ranking | "Open dossier before confirm"; borderline flag; wording on the confirm button; no reject endpoint |
| S8 | Ranking unfair to career changers / gaps | NEEDS_REVIEW scores 0.5 and is visibly provisional; borderline flag routes to human review; counterfactual tests |
| S9 | Candidate penalized for a planted injection they didn't write | Findings flag for review; they never reduce the score or hide the candidate |
| S10 | PII sent to a hosted model in the final product | Minimizer before every call; provider data agreement or self-hosted option (Lawyer juror's flip condition) |
| S11 | Baseline config accidentally disables auth | Only `AI_DEFENSES` is toggleable; auth/RBAC/gateway have no flag (rule 12); a test asserts it |

## Product/market risks (final product)

| # | Risk | Mitigation |
|---|---|---|
| M1 | Incumbents copy payload-bound approvals as a feature | The moat is vendor-neutral assurance plus the HR attack corpus and continuous testing, not the gate itself; pursue third-party scenarios early |
| M2 | No validated buyer or price | Customer-discovery interviews with SME HR teams and recruitment agencies before building F2+ |
| M3 | Regulatory burden of recruitment AI (high-risk classification in some jurisdictions, local data-protection law) | Legal review before any pilot with real data; DPIA template; human-oversight logs are already a design strength |
| M4 | "Independent" claim challenged | Use "self-tested" until outside parties run attacks |

## Residual risk after mitigation

The largest remaining risk is **R1/R2 execution**: whether the team actually holds the h7 gate. Everything else is either designed out (containment, determinism) or reduced to an honest disclosure.
