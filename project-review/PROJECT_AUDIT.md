# PROJECT_AUDIT — Vouch + SENTINEL (Secure AI HR System hackathon)

_Review date: 31 Oct 2026. Author: Claude. No implementation code was changed._

## 0. What this audit was based on

| Source | Status | Notes |
|---|---|---|
| Official hackathon specification (2 pages) | Read in full | The fixed constraints. |
| Project source inventory PDF (365 pp.) | Read: §3–8 (evolution, conflicts, constraints, open questions), U04 handover in full, notes N01–N06 in full, research PDF P01 headings and key sections | The handover (U04) is the latest statement of intent and is treated as the baseline. |
| `sentinel-defense-main.zip` | Inspected: README, `docs/architecture.md`, `pyproject.toml`, source tree (~21.4k lines Python), scenario format | Reported results were not re-run. |
| GitHub `RayenSebei/Reinventing-HR-through-Ai` (`sentinel/` scenario library) | **Read in full** at commit `84bf25f` (made public 31 Oct 2026) | 33 files; the handover's counts are confirmed; per-scenario analysis in SCENARIO_MAPPING.md; the 9 PDFs were parsed and render-tested |

**Not inspected because it does not exist yet:** Vouch application code. The handover says the workspace "was initially empty". No routes, schemas or DB models are confirmed.

## 1. Reconstructed project vision

**One sentence (from the handover):** Vouch is a secure AI recruitment platform. It screens and ranks candidates using traceable job-related evidence, prepares recruitment actions, and requires explicit human approval before any consequential action runs. SENTINEL independently tests whether the platform resists adversarial documents, unauthorized access, approval manipulation and AI-policy violations.

**Primary objective (hackathon):** win a 17-hour event judged on Intelligent / Reliable / Human-in-the-loop / Secure, with a 5-minute demo, a README and a pitch "as a startup".
**Primary objective (final product):** a vendor-neutral control layer between untrusted HR inputs (CVs, emails) and consequential HR actions, with continuous adversarial assurance.

**Intended users:** recruiter (operator), hiring manager (approver), HR admin (configuration), auditor/DPO (read-only oversight). Buyer hypothesis: SME HR teams, recruitment agencies, and organisations with mixed HR stacks. This hypothesis is **unvalidated** (§6 of the source report).

### Subsystems in the intended final product

| # | Subsystem | Purpose | Origin |
|---|---|---|---|
| 1 | Auth & RBAC | Identity, 4 roles, per-case resource authorization | U04 §9 |
| 2 | Recruitment cases | Job, criteria, recruiter-confirmed weights | U04 §4 step 1 |
| 3 | Document intake | Preserve the original, SHA-256, extraction, metadata | step 2 |
| 4 | Document security analysis | Hidden text, white-on-white, tiny font, metadata, injection, keyword stuffing, contradictions | step 2 |
| 5 | Evidence engine | Requirement → exact quote + page + status, checked deterministically | step 3 |
| 6 | Ranking engine | Deterministic weighted rubric, missing evidence shown, no auto-reject | step 4 |
| 7 | AI orchestration | LLM extracts and interprets, proposes actions; never executes | steps 3–5 |
| 8 | Proposals & approvals | Payload-hash-bound, expiring, single-use human approvals | step 6 |
| 9 | Action Gateway | Deny-by-default sole executor | step 7 |
| 10 | Trust Ledger | Hash-chained event log (tamper-evident) | step 7 |
| 11 | Frontend | Recruiter / manager / auditor screens + assurance panel | U04 §7 |
| 12 | SENTINEL assurance | Black-box adversarial tests via the public API; metrics; report | U04 §5–6 |

### Confirmed vs assumed vs optional

| Class | Items |
|---|---|
| **Confirmed requirement (official spec)** | Ranked shortlist with job-related justification (if the screening axis is chosen); human approval before anything is "sent or recorded"; AI + system + web security; fictional data only; README, code, 5-min demo, presentation; 17 h |
| **Team decision (handover)** | One end-to-end recruitment workflow; deterministic transparent ranking; no auto-rejection; payload-bound approvals; Action Gateway; Trust Ledger; SENTINEL as examiner, not gatekeeper; modular monolith; FastAPI/React/SQLite; the 14 security rules; the explicit "won't build" list |
| **Assumption (unverified)** | That the 24 scenarios + 9 PDFs exist at HEAD; that a hosted LLM is allowed and available; that the model handles FR/AR/EN; that team size is 2 or 4; that SENTINEL code can be reused for HTTP black-box testing |
| **Optional / idea** | Email digest, auto-replies, scheduling against a real calendar, employee Q&A, interview assistant / interview chatbot, onboarding, document generator, turnover analysis, Presidio, Docling, LangGraph, ESCO |

## 2. How the components are meant to fit together

CV upload → intake (hash, extract) → security analysis (findings) → evidence engine (LLM extracts candidate claims, deterministic quote check) → ranking (deterministic) → recruiter reviews and confirms shortlist → AI drafts an action (invite / follow-up / reply) → proposal stored with canonical payload hash → hiring manager approves (approval bound to hash, expiry, nonce) → Action Gateway checks everything and executes into an adapter (sandboxed outbox for the hackathon) → every step writes a ledger event. SENTINEL, outside the trust boundary, drives the same public API with attack inputs and checks responses plus observable state.

## 3. Findings: what is strong

1. **The core security idea is correct and demonstrable.** Binding approval to a canonical payload hash and making a single gateway the only executor turns the spec's "nothing sent without approval" into an enforced, testable invariant. Every court juror who discussed it, including 11 who voted guilty, called it sound.
2. **The safety design avoids the known traps in recruitment AI.** It has no auto-rejection, excludes protected attributes, keeps scoring deterministic, shows missing evidence separately, and uses fictional data. It answers the team's own notes (N01) on bias, instability, hallucination and explainability.
3. **The scope discipline is explicit.** There is a written "won't build" list (HRIS, payroll, emotion analysis, flight risk, swarms, fine-tuning, K8s).
4. **Positioning is honest.** The team says "tested against N scenarios", not "secure", and calls the ledger "tamper-evident, not immutable".
5. **SENTINEL is real, non-trivial prior work.** It has a typed package, scenario schema, mutation validation, metrics (ASR/BTU/FBR), JSONL traces and a dashboard. Its reported live-model numbers were produced on a different domain.

## 4. Findings: what is weak (ordered by impact)

| # | Weakness | Evidence | Impact |
|---|---|---|---|
| W1 | **The two demo payoff moments come last in the schedule.** Approvals and the gateway are at h9–11 and SENTINEL integration at h13–14.5, with no fallback. | U04 §13 | Highest. If either slips, the pitch has no proof. (Court charge 3) |
| W2 | **SENTINEL cannot test Vouch as-is.** Its runner simulates its own world in-process with a reference agent, simulated human and synthetic ToolGateway. Its existing HTTP seam (`HttpDefense`) is the reverse direction: SENTINEL calling a *defense*, not driving a *target app*. Black-box HTTP target execution has to be written. | `docs/architecture.md`, source tree | The "reuse" is the schema, metrics, reporting and dashboard patterns, not the runner. 1.5 h is not enough. |
| W3 | **The 24 HR scenarios were written before any API existed.** None has run, and every one needs mapping. Verified in the repo: they are prose, with no machine steps. | U04 §6, repo | Each scenario is a contract you haven't signed yet. See SCENARIO_MAPPING.md |
| W4 | **Team size and model are undecided.** | §4 of report | Nobody can cost the work. (Court charge 2) |
| W5 | **Multilingual extraction is unproven.** CVs are FR/AR/EN or mixed (N01). The "deterministic fallback" has no defined way to extract evidence. | N01, U04 §7 | The "Intelligent" criterion is at risk exactly when the fallback is needed. |
| W6 | **Document forensics is broad and untested.** Seven attack classes are planned, but only the team's own fixtures are tested. Some classes (hidden layers, render-vs-extract differential) are costly to do well. | U04 §4 | Time sink with false-positive risk. |
| W7 | **"Independent" assurance is not yet independent.** The same team writes the attacks and the defenses. | Court: Competitor and Lawyer jurors | Credibility risk if a judge asks. |
| W8 | **Two-product pitch.** Judges must learn "Vouch" and "SENTINEL" in 5 minutes. The frontend is built last (h11–13). | Court: Designer juror | Clarity and UX. |
| W9 | **Approval semantics are unresolved.** It is unclear whether "recorded" covers AI drafts, uploads and rankings. | §4, §6 of report | Judges may probe it. Needs a written, enforced definition. |
| W10 | **The fairness concern (career changers, gaps) has no mechanism.** | N01 item 5 | Partly addressed by not auto-rejecting. There is no positive mechanism. |
| W11 | **Market is unvalidated.** Incumbents ship HR agents. | P01 §8, §6 | Matters for the "startup" framing, not the build. |
| W12 | **Python 3.12 requirement vs 3.11.9 locally.** | U04 §5 | Small, but it blocks SENTINEL tests if ignored. |

## 4b. Findings from the repo (verified, not in the handover)

| # | Finding | Impact |
|---|---|---|
| G1 | The repo holds **only** `sentinel/`; no Vouch code at all | Confirms the plan starts from an empty workspace |
| G2 | The 24 scenarios are **prose specifications** (16 of 24 explicitly wait on the API contract), and no runner exists | The live SENTINEL demo needs a runner plus per-scenario machine steps. This is the retrial's main charge |
| G3 | AI-001, AI-004 and EI-004 reference **fixtures that don't exist** | 3 scenarios can't run until the fixtures are made |
| G4 | The PDF generator is ASCII-only (`?` replaces non-ASCII) with Type1 Helvetica | French, Arabic and mixed-language CVs can't be produced, so a core claim about Tunisian CVs (N01) is untestable today |
| G5 | `hidden_text.pdf` uses text render mode 3, which **pdfplumber 0.11.10 doesn't expose** | The planned parser alone would miss it. **Fixed and measured in this review** with a rendering check: 3/3 hidden fixtures flagged, 0/6 others, about 10 ms per page |
| G6 | EI-001 separates "candidate claimed" from "independently verified" | The evidence status names had to change (`SOURCED`, not `SUPPORTED`/verified) |
| G7 | Attack bodies carry client-supplied `role`, `approved_by`, `owner_id`, `document_id`, `tampered_payload` | Mass-assignment hardening (`extra="forbid"`) is required |
| G8 | No metadata or off-page fixture, though both are named in the plan / DS-003 | Don't claim detection for those classes until fixtures exist |
| G9 | The library itself is high quality: consistent threat model, a blocked-is-never-pass rule, an LLM judge barred from critical outcomes, and a baseline that never disables auth | It is reusable as-is once mapped |

## 5. Perspectives requested that do not apply

The master prompt lists Hardware & Embedded, Robotics & Automation and Computer Vision jurors. This is a web software product with no sensors, actuators or vision pipeline. The only "vision-adjacent" element is PDF rendering for hidden-text detection, covered under document security. These are marked **N/A** rather than padded with invented criticism. The only hardware question is optional local LLM inference (see TECHNOLOGY_STACK.md).

## 6. Genuinely missing information

1. Actual team size and skills: who can write FastAPI and who can write React.
2. Which LLM the team can legally and practically call during the event, and with what credentials.
3. Whether any work before the event is allowed (the judge raised this).
4. ~~The current contents of the GitHub `sentinel/` library~~: now read in full (§4b).
5. The organizers' reading of "recorded without approval" and "real volumes". Ask them at kickoff.

## 7. Audit conclusion

The **design** holds up. The **plan** does not yet. It builds the proof last, on an unbuilt API, with an undecided team and model. The fixes are to reorder the work, write the test harness, narrow the forensics and simplify the story. The vision does not need to shrink. See COURT_VERDICT.md for the court's result and FINAL_PROJECT_SPECIFICATION.md for the redesign.
