# CODEX TASK PROMPT: complete, secure and prove the Vouch HR system

Paste this as the task. Save `AGENTS.md` at the repository root first (Codex reads it automatically), and put the two reference files at `docs/MASTER_BUILD_PROMPT.md` and `docs/security/HARDENING_PROMPT.md`.

---

## ROLE AND GOAL

You are a senior engineer joining a working hackathon project (the "Secure AI HR System": 17-hour event; spec axes: resume screening and ranking, email summary, automatic replies, candidate follow-ups, interview scheduling, employee questions). You did not write the code. Your job, in order:

1. **Verify** what exists (Phase 0). Write no application code before that.
2. **Protect** the baseline: Vouch 29 tests, interview-chat 36 tests, 24 SENTINEL scenarios.
3. **Close the gaps** so the product is **Intelligent** (outputs a recruiter can use as is), **Reliable** (works end to end on real volumes without breaking), **Human in the loop** (nothing sent or recorded without approval) and **Secure**.
4. **Prove every claim** with a test that can fail, a numeric metric where you claim intelligence, and an evidence file.

Follow `AGENTS.md` at all times. Reference material (read only the sections for the phase you are in; section numbers refer to `docs/MASTER_BUILD_PROMPT.md`): Section 1 ground truth · Section 5 feature dictionary (QL, RB, HI, AX, TQ entries: Today / Do / Test / Break-risk) · Section 6 security status table · Section 7 numeric thresholds · Section 8 test harness, fixtures, invariants, load and chaos lists. Security IDs (IN, PA, CX, LM, AG, RG, OB, HL, WA, DL, IF, SC, AV, FC, AU) are defined in Section 4 of `docs/security/HARDENING_PROMPT.md`.

## WHAT YOU WORK ON

Base app: `vouch/` (FastAPI/Starlette, SQLite, PDF-only today). `interview-chat/` stays a separate module (port only its slot-proposal logic). Known facts to verify in Phase 0 (do not trust, check each and mark CONFIRMED / WRONG / PARTIAL with file and line):

- G2 Vouch accepts PDF only (no DOCX, no scans/OCR), ≤10 pages, ≤5 MB.
- G3 Default model mode is `lexicon` (word list); all committed attack results use the `stub` model; real-model quality is unmeasured.
- G4 "experience" criteria have no duration logic; negation ("no experience with X") is not handled.
- G5 Ranking is a function of evidence statuses only; justification is one template sentence.
- G6 Only two proposal kinds (`interview_invite`, `follow_up`); Vouch ignores any calendar.
- G7 **The email recipient is extracted from the CV text** (`cases.upload_cv` → `documents.contacts`): the candidate controls who is mailed.
- G8 `gateway.execute` checks outside the transaction; delivery failure is not retried.
- G9 Known defects in `docs/architecture-review.md`: criteria edit after analysis raises an FK failure; "open top-3 dossiers" gate is frontend-only; analysis runs synchronously inside the request.
- G10 The model prompt uses a fixed `<cv_text>` tag (no random boundary, no canary).
- G11 Unicode Tag block (U+E0000–E007F) is not stripped anywhere; interview-chat deletes ZWNJ/ZWJ blanket (damages Arabic).
- G12 CI runs only the Vouch tests.
- G13 Not built: inbound mail, email digest, inbound reply handling, follow-up detection, employee Q&A.
- G14 Dashboard v2 has only the Command Center; everything else is legacy static JS.
- G15 Demo password `demo1234` hard-coded; no global outbound kill switch; JWT secret random per process.
- G16 Ledger is tamper-evident but lives in the same DB.
- G17 The demo machine is Windows; Docker/Tesseract may be missing.
- G18 n8n facts (check against the official repo `https://github.com/n8n-io/n8n` for the pinned version): the Webhook node offers only Basic, Header, JWT or None auth (no built-in HMAC check); the Send Email node (`n8n-nodes-base.emailSend`) cannot set `In-Reply-To`/`References`; Remove Duplicates "Remove Items Processed in Previous Executions" exists since n8n 1.64.0. Record the n8n version and every node `type`/`typeVersion` in `n8n/`.

## HOW YOU WORK: THE PHASE LOOP

You execute **one phase per run**, the one named under `CURRENT PHASE` at the bottom. For each phase:

1. Session start per `AGENTS.md`. Confirm the previous gate is green in `docs/plan/PROGRESS.md`.
2. Read the dictionary entries for this phase's IDs.
3. For each ID: write the failing test → see it fail → implement behind a flag → see it pass → run the full baseline → update `EVIDENCE.md` and `CHANGELOG_MASTER.md` → commit `ID: summary`.
4. Evaluate every gate condition of the phase literally; paste the command output into `EVIDENCE.md`.
5. **Stop at the gate.** Post the gate report (below). Do not start the next phase.

If something blocks you (missing tool, no network, ambiguous requirement, regression after two attempts): stop, write it to `docs/plan/OPEN_QUESTIONS.md` and `PROGRESS.md`, report it, and wait. Never improvise around a blocker by weakening a check.

## PHASES (IDs and gates; details in the dictionary)

**P0 Recon and baseline (read-only for app code).** Produce in `docs/plan/`: `GROUND_TRUTH.md`, `SYSTEM_MAP.md` (Mermaid data flow with trust boundaries), `SEAM_MAP.md` (exact file/function for: upload handler, parse call, model call, prompt build, evidence build, ranking, proposal create/edit/approve/execute, delivery, ledger append, auth/role check, static serving, CI), `TOOL_INVENTORY.md`, `TRIFECTA_MATRIX.md`, `SECRETS_AND_DEPS.md` (paths only, never values), `BASELINE.md` (how to run on Windows and Linux, test inventory, **golden set v0** with saved outputs from existing fixtures, timing of a 20-CV upload, hardware and tool availability: Python version, SQLite FTS5, Docker, Tesseract, Node 24), `RECORD_REGISTER.md` (every table and every code path writing it, classified A audit / D draft / H decision / X action), `TRACEABILITY.md` skeleton, `DECISIONS.md` (D1–D11 from Section 3 of the master file), `OPEN_QUESTIONS.md`, `PROGRESS.md`. Also re-verify the security status table (master Section 6) and correct it.
GATE 0: all existing suites green on a clean checkout; golden outputs saved; every G row has a verdict; **no application file modified**.

**P1 Foundations.** RB-03 (WAL pragmas, busy_timeout), RB-09, RB-14, migration runner (`schema_migrations`), TQ-01, TQ-02, TQ-04, AX-10 (generator skeleton), HL-07 (`OUTBOUND_MODE=disabled|sink|live`, default `sink`), DL-06, SC-01, WA-02 (demo credentials only when `VOUCH_DEMO=1`). Create `tools/verify.py`; extend CI to run every suite; secret scan on tree and history; `/healthz` and `/readyz` with startup self-check.
GATE 1: `python -m tools.verify --fast` green; CI runs all suites; secret scan clean (a planted fake key fails CI); kill switch proven in all three modes; baseline unchanged.

**P2 Human in the loop made machine-checkable.** HI-01 to HI-07, TQ-03 (first drill rows), AG-02, RB-03 (single-transaction execute), RB-05, RB-07, OB-01 to OB-04, HL-01 to HL-04, decisions D10 and D11. Record register enforced by a test and DB triggers; proposal-kind registry (smallest seam in `gateway.py`); server-side review gates; recipient confirmation by a human before any proposal exists; risk-tiered approval queue; delivery retry with idempotency key (Vouch's key is the guarantee; the n8n Remove Duplicates node on `outbox_id` is only a second layer); n8n workflow hardening per master R25 (Webhook Header Auth + Raw Body, Code node HMAC-SHA256 check with `crypto.timingSafeEqual()`, secret from an env var, `ccEmail`/`bccEmail` empty and asserted by a test on the workflow JSON); **invariant fuzzer** over the real API (invariants I1–I14, Section 8.3).
GATE 2: fuzzer ≥10,000 random sequences with 0 violations; approve-then-edit refused; execute without approval refused through API, function and direct DB insert; CRLF/BCC fixtures neutralized; FX31 (bad webhook HMAC sends nothing; CC/BCC in workflow JSON fails lint) green; hostile CV email cannot produce a proposal until a human confirms; top-N review gate enforced server-side; criteria edit after analysis no longer fails and keeps evidence; SENTINEL 24/24; each protection removed in the drill turns its named tests red.

**P3 Ingestion and parsing.** QL-09, IN-05, IN-07, PA-01 to PA-08, CX-02, CX-04, RB-01 (durable SQLite job queue + `python -m app worker`), IF-05, AV-02. Upload returns 202 + job id; DOCX via zip + `defusedxml`; scans via Tesseract in the sandbox driver (`docker` if available, else `lite`, labeled "not a security boundary"); strip Unicode Tag and bidi controls, never ZWNJ/ZWJ between Arabic letters.
GATE 3: companion Gate 3 conditions; extraction fidelity ≥0.98 text/DOCX, ≥0.90 scans; golden set unchanged on text PDFs; worker killed mid-job → job completes exactly once; poison PDF ends `dead` and the batch continues; 200 uploads accepted without blocking reads.

**P4 Intelligence core.** QL-01 to QL-07, QL-10, QL-17, LM-01 to LM-03, FC-01, FC-03, CX-03, CX-05. Typed rubric (skill, experience_years, education, language, certification, must_have), facts with evidence spans, date arithmetic in code, evidence levels L0–L3 with negation/hedge handling in EN/FR/AR, rank bands with score ranges and weight-sensitivity, justification generated only from verified facts, spotlighting boundary + canary, `FEAT_SCORING_MODE=off|shadow|on` with a human-read diff report before `on`, gold-set generator and `python -m tools.quality`.
GATE 4: every threshold in Section 7.1 met with the `replay` model; the `lexicon` floor still passes zero hallucinated evidence and fairness; shadow diff vs v1 explained in writing.

**P5 Replies, follow-ups, scheduling.** AX-03 to AX-06, QL-11, QL-15, QL-16, RB-10, OB-01 to OB-08, IN-06, HI-08, HI-10. Template-first i18n replies (EN/FR/AR); inbound candidate replies matched through a signed thread token (HMAC of outbox id) in the subject/footer, never by claimed address (the n8n Send Email node cannot set `In-Reply-To`, G18; use `In-Reply-To` only if a transport Message-ID was actually returned and stored); follow-up state machine with business days, quiet hours, max reminders, opt-out; calendar sources (JSON, ICS busy-blocks only) and deterministic slot engine; slot offer → human-confirmed acceptance → calendar event proposal → ICS from fixed template → availability re-check at execute; decline messages only after a recorded human decision.
GATE 5: scenario S2 green in `tools.e2e` (CV → shortlist → recipient confirm → slot offer approved → edit-after-approval refused → send → candidate reply → human confirm → event + ICS approved → no follow-up fires after reply); slot property tests, DST fixture and concurrent double-booking test green.

**P6 Email summary (stretch if the clock is 17 h).** AX-01, AX-02, QL-12, QL-13, IN-01 to IN-03, IN-06, LM-05, LM-10, LM-12, AV-04. Read-only mail sources (EML folder default), allowlist HTML sanitizer, rules-first triage with LLM second pass under an urgency floor, digest verified against headers, "needs human answer" queue linked to reply drafts.
GATE 6: Section 7.2 thresholds; injected email cannot lower its own urgency; LLM down → rule-only digest labeled.

**P7 Employee questions (cut first).** AX-08, QL-14, RG-01 to RG-06, LM-04. New read-only `employee` role; FTS5 with ACL as a `WHERE` pre-filter; extractive cited answers with numeric verification; refusal and "Ask HR" draft ticket.
GATE 7: Section 7.3 thresholds; zero restricted-chunk leaks across roles × docs × phrasings × languages.

**P8 Product surface.** RB-13, AX-09, HI-04 (UI), HI-09, HI-11, WA-03 to WA-05, WA-07, WA-08, LM-05 (rendering). Screens: Today, Candidates + evidence, Ranking, Approvals, Scheduling, Follow-ups, Digest, Employee Q&A, Security Center, System health. Text nodes only, CSP unchanged, RTL checked.
GATE 8: Playwright e2e green headless in CI; 0 CSP violations; legacy screens still reachable.

**P9 Reliability proof.** RB-02, RB-04, RB-06, RB-08, RB-11, RB-12, AV-01, AV-03, AV-05, TQ-05. `ModelClient` wrapper (timeout, retry, circuit breaker, fallback chain live → replay → lexicon, batch isolation), degradation matrix tests, load profiles L1–L4, chaos C1–C12.
GATE 9: `python -m tools.verify --reliability` prints the SLO table (Section 7.4) all green; 0 lost jobs and 0 duplicate sends under chaos.

**P10 Security breadth and real-model validation.** Remaining rows of the Section 6 table, AX-07 (optional), QL-08, LM-09, AU-01 to AU-06, DL-04, IF-01 to IF-04, SC-02 to SC-07, FC-02, FC-04 to FC-06.
GATE 10: every Section 6 row is DONE or listed in `RESIDUAL_RISK.md` with owner and compensating control; live-model report committed (model, date, prompt version).

**P11 Proof and release.** TQ-06, TQ-07. `python -m tools.verify --all` as the single command; `EVIDENCE.md`; `RESIDUAL_RISK.md`; README rewritten (record table generated from the register, numbers with reproduce commands labeled stub/replay/live, honest limits); demo script with timings; backup video; flag-off rollback drill.
GATE 11: traceability matrix has no spec sentence without a passing test; fresh-clone drill (clone → install → verify --all → demo path) in under 15 minutes.

## GATE REPORT FORMAT (post at every gate, max 15 lines)

```
GATE <n> <PASS|FAIL|BLOCKED>
Changed: files, flags and modes
Tests: suite → pass/fail counts, before vs after
Metrics vs thresholds: table (only metrics this phase owns)
Golden-set diffs and your judgment
IDs now satisfied
Open questions / decisions needed from the human
Risks for the next gate
Commit range and rollback note
```
FAIL or BLOCKED reports must say exactly which condition failed and what you tried.

## HARD STOPS (stop and ask; do not work around)

- A baseline test turns red and two fixes did not repair it.
- A change would alter a protected module outside a listed seam.
- A threshold cannot be met honestly.
- You need a dependency you cannot pin and verify, or network access that is unavailable.
- The ground truth contradicts the plan in a way that changes scope (for example G7 is WRONG, or SQLite lacks FTS5 and no fallback is acceptable).
- You are about to claim a result you have not reproduced with a command.
- You need an n8n node, parameter or behavior you cannot find in the official n8n repo/docs for the pinned version (build the logic in Vouch instead, or ask).

## CURRENT PHASE

Phase 0 is done, and Phases 1 and 2 are partly done (branch `vouch-hardening`, 2026-11-01). Read `docs/plan/PROGRESS.md` first: it lists exactly which IDs are DONE, with their tests, and what remains. **Current task: finish the remaining Phase 1 and Phase 2 items listed there**, then stop at Gate 2 with the report. Do not redo finished items; extend their tests if you touch them.

---

### To continue after a gate (paste as the next task)

```
Gate <n> is approved. CURRENT PHASE: Phase <n+1>.
Decisions since last gate: <list or "none">.
Follow AGENTS.md and the phase loop. Stop at the gate and report.
```
