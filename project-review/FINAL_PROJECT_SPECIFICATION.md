# FINAL_PROJECT_SPECIFICATION — Vouch (optimized)

_The vision is kept: an evidence-first, approval-enforced AI recruitment workflow with built-in adversarial assurance. What changes is the build order, the demo story, the SENTINEL integration method and the extraction design. Each change answers a court charge._

## 1. Product statement

**Plain sentence for judges (one product, no jargon):**
> Vouch lets an AI screen CVs and draft recruitment emails, but it can't be tricked by a CV, can't make claims it can't quote, and can't send anything a manager didn't approve, and we prove it by attacking it live.

SENTINEL keeps its name inside the product as **Vouch Assurance (powered by SENTINEL)**. That is one product with a built-in attack suite, which answers the Designer juror. The word "independent" is reserved for the future, when third parties contribute scenarios (FUTURE UPGRADE), which answers the Competitor and Lawyer jurors.

## 2. Exact capabilities

### 2.1 Hackathon build (MVP, 17 h)

| ID | Capability | Acceptance |
|---|---|---|
| C1 | Login with 4 seeded roles; per-case authorization | A recruiter on case A gets 403 on case B's candidates, enforced in the backend |
| C2 | Create a recruitment case with criteria, weights summing to 100, and recruiter confirmation | Unconfirmed criteria block ranking |
| C3 | Upload PDF CVs (single or batch); SHA-256 hash; original stored read-only | Duplicate hash is detected |
| C4 | Document findings: hidden text (render check: no ink under the glyph, covering render mode 3 and white-on-white), tiny (<4 pt) and oversized font, off-page text, instruction-like phrases, keyword stuffing (repetition density), date contradictions | All 9 fixtures produce their expected finding; the clean CV produces none (render check already measured: 3/3 hidden-text fixtures flagged, 0/6 others) |
| C5 | Evidence dossier: requirement → quote → page → status `SOURCED / NEEDS_REVIEW / NOT_FOUND` (`VERIFIED` is reserved for a trusted external verifier and never emitted in the MVP) | Every `SOURCED` quote is an exact normalized substring of the *visible* text; otherwise it is downgraded. UI says "Claimed in CV (quote checked)", never "verified" (scenario EI-001) |
| C6 | Deterministic ranking with per-criterion breakdown; ties shown as ties; no auto-reject | Same input gives the same output (byte-identical JSON); hidden text contributes 0 |
| C7 | Recruiter confirms the shortlist (the human decision is recorded) | The shortlist is "draft" until confirmed |
| C8 | AI drafts an interview invitation or follow-up from the candidate's own dossier | The draft cannot reference another candidate's data |
| C9 | Proposal → manager approval bound to the canonical payload hash, 15-minute expiry, single use, proposer ≠ approver | Any edit after approval gives a 409 at execution |
| C10 | Action Gateway executes into a **sandbox outbox**. No real email is sent | The only code path that writes to the outbox |
| C11 | Trust Ledger: hash-chained events, plus a verify endpoint | Tampering with a row is detected by verify |
| C12 | Assurance panel: runs the 5 demo scenarios (and as many of the 24 as are mapped) over HTTP; shows PASS / FAIL / BLOCKED / UNOBSERVABLE | Results come from a real run, with the timestamp shown |
| C13 | Demo safety: seeded DB, LLM replay cache, recorded backup video | The demo runs with Wi-Fi off |

### 2.2 Final product (post-hackathon)

Everything above, plus:
- real email and calendar adapters behind the gateway (SMTP / Microsoft Graph / Google);
- interview-slot proposal from a real calendar;
- inbox digest (official axis 2) and draft replies (axis 3) using the same proposal→approval→gateway path;
- cited policy Q&A (axis 5) as read-only with no actions;
- OIDC SSO and multi-tenant isolation;
- PostgreSQL;
- continuous assurance in CI and on schedule;
- third-party scenario contributions (the real "independent" claim);
- DOCX intake and OCR for scanned CVs;
- render-vs-OCR differential for hidden content;
- bias test suite with a counterfactual name/gender swap (N01) run on every model change;
- data-retention controls.

**Kept out (unchanged from the team's list):** HRIS, payroll, attendance, leave, emotion analysis, flight-risk prediction, auto-rejection, automated hiring decisions, fine-tuning, microservices.

**Interview chatbot idea:** out of scope for the hackathon. It competes with the chosen workflow for time, and the team's own note N04 lists 16 risks (consent, transcription errors, bias, emotion analysis). It can be revisited as a later "interview question generator" that reuses the evidence dossier, with no recording.

## 3. Technical decisions

Each row: current approach → limitation → alternatives → **decision** → why → requirements → integration.

### D1. Build order
- **Current:** layered build (backend, then documents, then evidence, then ranking, then approvals at h9–11, then frontend, then SENTINEL at h13–14.5).
- **Limitation:** the proof comes last. That was court charges 1 and 3.
- **Alternatives:** (a) keep layers but compress them; (b) **walking skeleton**: a thin end-to-end slice first, then deepen; (c) build SENTINEL first against mocks.
- **Decision: (b).** By **h7**, the following runs end to end through the real API with one clean and one injected CV:
  - auth;
  - case;
  - upload;
  - naive evidence;
  - ranking;
  - proposal;
  - approval;
  - gateway;
  - ledger;
  - the 5 demo scenarios.

  Everything after h7 makes the parts smarter. Nothing after h7 is needed for the demo to work.
- **Why:** it satisfies the judge's condition 1, and every later hour lowers risk instead of adding it.
- **Integration:** the API contract is frozen at h1 (D2).

### D2. API contract
- **Current:** a list of operations; no routes.
- **Decision:** FastAPI + Pydantic models written first. `openapi.json` is exported at h1 and committed. The frontend client is generated from it (`openapi-typescript`). SENTINEL's HR adapter is coded against the same file.
- **Why:** one source of truth for three consumers. Changes become diffs, not surprises.

### D3. SENTINEL integration method
- **Current:** "reuse SENTINEL" with 1.5 h at the end.
- **Limitation:** SENTINEL's runner simulates its own world in-process. Its HTTP seam calls a *defense*; it does not drive a *target app*.
- **Alternatives:**
  - (a) adapt SENTINEL's simulator to wrap Vouch: deep coupling, and slow;
  - (b) **a new thin HTTP target runner** (`sentinel_hr/`) that reads the 24 YAML scenarios, runs steps with `httpx` as seeded users, and asserts on the HTTP response plus the public observability endpoints (ledger and outbox). It reuses SENTINEL's metric names (ASR, FBR), JSONL trace format and dashboard styling;
  - (c) pytest-only security tests.
- **Decision: (b), with each scenario also exported as a pytest case** so the CI and the demo use the same assertions. The repo's 24 scenarios are prose specifications. Machine steps go in **sidecar files** (`sentinel_hr/mappings/<ID>.yaml`), so the library stays unchanged. Vouch provides test-mode-only fixture loading, a prompt canary, a model stub and a read-only auditor identity. The full per-scenario mapping is in SCENARIO_MAPPING.md: 12 scenarios can pass at h7, including all 5 demo ones.
- **Requirements:** Python 3.12 for SENTINEL; the runner itself needs only `httpx` and `pyyaml`, so it also works on 3.11.
- **Integration:** it runs as a separate process with only HTTP credentials for seeded test users. It has no DB access (rule 11). Anything it cannot observe through the API is reported as `UNOBSERVABLE`, never as `PASS`.

### D4. LLM role and choice
- **Current:** "hosted if allowed, else local or deterministic", undecided.
- **Decision:** a three-tier `ModelAdapter` interface with one JSON-schema output (`ExtractedClaims`):
  1. **Primary:** whichever hosted LLM the team has credentials for and the organizers allow, at temperature 0 with structured output. Pick it **before the event** by running the same 9 fixtures plus 3 FR/AR/mixed CVs through each candidate model and comparing quote-verification pass rates.
  2. **Local fallback:** Qwen3-8B via Ollama. The team already ran it inside SENTINEL. Its multilingual quality on these CVs must be measured, not assumed.
  3. **Replay:** the responses recorded from tiers 1–2 for the demo fixtures, keyed by document hash, so the live demo needs no network.
- **Why:** the LLM's output is *data* that deterministic code verifies (D5). Model quality affects coverage (how many requirements get evidence), never safety.
- **Requirements:** API key, or a GPU with enough memory for a quantized 8B model (CPU is possible but slow; measure it).

### D5. Evidence verification
- **Decision:** the LLM returns `{requirement_id, quote, page}`. The verifier normalizes both strings (Unicode NFKC, case-fold, collapse whitespace, strip diacritics for the Latin script only) and searches the **visible-text layer** of that page. An exact match gives `SOURCED`: the candidate claims it, and the quote is real. A match above a fuzzy threshold (rapidfuzz `partial_ratio`, threshold tuned on fixtures) gives `NEEDS_REVIEW`. No match gives `NOT_FOUND`, and the model's claim is logged as an `UNSUPPORTED_CLAIM` finding. `VERIFIED` requires a configured trusted verification source (for example an issuer registry), which is a future upgrade. This distinction is required by repo scenario EI-001.
- **Why:** it catches hallucinated and misattributed evidence (EI scenarios) without trusting the model. Matching against the *visible* layer means hidden text can never support a claim (rule: "hidden text cannot inflate score").

### D6. Deterministic extraction fallback
- **Decision:** a multilingual skill lexicon (YAML). Each canonical skill lists aliases in EN/FR/AR (e.g. `javascript: [js, javascript, ecmascript, جافاسكريبت]`). The fallback searches visible text with word-boundary matching and emits quotes, which then go through the same verifier.
- **Why:** it answers the prosecution's point that the fallback had no extraction method. It covers skills, which are the heaviest-weighted criterion. Experience and education fall back to `NEEDS_REVIEW` (honest, not invented).

### D7. Document security analysis
- **Current:** seven attack classes, including a render-vs-extract differential.
- **Decision (updated after testing the repo fixtures):** use **pdfplumber** (MIT) for characters and boxes, and **pypdfium2** (already a pdfplumber dependency) to render the page in greyscale at 2× scale. A character is *hidden* if any of these holds:
  - its box has almost no ink (< 2% dark pixels);
  - its size is < 4 pt;
  - its box is off the page.

  Text is split into `visible_text` and `hidden_text`. Instruction-like phrases are matched with a small regex and keyword set in EN/FR/AR. Keyword stuffing is caught by token repetition density. Oversized font (e.g. 72 pt) is flagged. Date contradictions are caught by overlapping or impossible date ranges.
- **Why:** a check on colour and size alone **fails on the repo's `hidden_text.pdf`**. That file uses text render mode 3, which pdfplumber 0.11.10 doesn't expose, so its characters report as black 9 pt text. The rendering check catches all three hidden classes in one rule. Measured on the 9 fixtures:

  | Fixture | Characters flagged as hidden |
  |---|---|
  | `hidden_text.pdf` | 95 |
  | `white_on_white.pdf` | 53 |
  | `suspicious_font_sizes.pdf` | 12 |
  | `clean_cv.pdf` and the other 5 | 0 |

  It took about 10 ms per page. **Caveats:**
  - Thin glyphs (hyphens, dots) can fall under the ink threshold, so aggregate per word before raising a finding.
  - This was tested only on these 9 one-page synthetic files.
  - A full render-vs-OCR differential (Tesseract with Arabic models) is still a FUTURE UPGRADE.
- **Security principle:** **detection is a UX feature; containment is the control.** The LLM has no tools, sees CV text only inside a delimited data field, and returns schema-validated data. Its output cannot trigger actions. A CV that evades every detector still cannot send an email or approve anything.

### D8. PII minimization before the LLM
- **Decision:** before any model call, redact email, phone, URL, postal address patterns, date of birth, the name (from the header block plus filename), and photo (images are not sent). Use regex rules in EN/FR/AR formats. Presidio is OPTIONAL: its Arabic support is weak and it adds spaCy models.
- **Why:** it answers the Lawyer's flip condition (real CVs to a hosted model) and the team's own privacy and bias notes (N01: hide name, photo, gender, age, address, nationality).

### D9. Ranking
- **Decision:** score = Σ weight × criterion score. Criterion score: `SOURCED` = 1, `NEEDS_REVIEW` = 0.5 (shown as provisional), `NOT_FOUND` = 0 (shown as "no evidence found", not "lacks"). Output includes the breakdown, missing list, findings badge and a "borderline/unusual profile" flag when `NEEDS_REVIEW` items exceed 30% of weight. The flag routes the candidate to human review instead of the bottom of the list. This answers W10 (career changers and gaps). Candidates with a critical document finding are **not penalized or hidden**: they are flagged for review, because a planted injection may not be the candidate's doing.
- **UX against automation bias:** the shortlist cannot be confirmed until the recruiter has opened each top-N dossier (tracked). The confirm button shows "You are deciding; Vouch ranked on evidence only."

### D10. Approval semantics (resolves W9)
Written into the README and enforced in code:

| Data | Recorded automatically? | Why |
|---|---|---|
| Telemetry, security findings, ledger events | Yes | Audit, not decisions about people |
| Uploaded originals + extraction | Yes, as *case working data* | The recruiter's own upload is a human act |
| AI drafts (dossier, ranking, messages) | Yes, as `DRAFT` and never shown as decided | A draft is not a record about the person |
| Confirmed shortlist | Only on recruiter confirmation | Human decision |
| Any outbound message / status change | Only via approved proposal through the gateway | Spec golden rule |

Ask the organizers at kickoff whether this reading is acceptable.

### D10b. Data handling statement (asked for by the retrial judge and the only NOT GUILTY juror)
Put this in the README and say it once in the pitch:
- **Where CVs go:**
  - Originals stay on the Vouch host.
  - Only *visible, PII-minimized* text goes to the model.
  - In the hackathon that is synthetic data only.
  - In the product: a hosted model under a data-processing agreement, or a self-hosted model for customers who need data to stay in-country.
- **How long they're kept:** a per-case retention period (configurable, e.g. 6 months after the case closes). After that, originals, extractions and dossiers are deleted.
- **Ledger vs deletion:** the ledger stores **hashes and IDs, never CV content or contact data**. Deleting a CV leaves a ledger entry ("document X deleted under retention") and the chain stays verifiable.

### D11. Approval binding
- **Decision:** the canonical payload is JSON per RFC 8785 (JCS) or sorted-key compact JSON in UTF-8. `payload_sha256` is stored on the proposal. The approval row holds (proposal_id, payload_sha256, approver_id, approver_role, case_id, nonce, expires_at, used_at). The gateway recomputes the hash from the *stored current* payload. A mismatch, expiry, use, wrong role, proposer == approver, or a case outside the approver's scope causes a deny plus a ledger event. Single use is enforced by an atomic `UPDATE … WHERE used_at IS NULL`.

### D11b. Request hardening (forced by repo scenarios AU-003, AU-004, AP-001, AP-003, EI-004)
- Every Pydantic request model uses `extra="forbid"`, so a client-supplied `role`, `approved_by`, `approval_token`, `owner_id` or `document_id` is rejected with 422.
- `/execute` takes no body.
- List endpoints cap `limit` and have no owner filter: scope always comes from the session.

### D12. Ledger
- **Decision:** `hash_i = SHA256(hash_{i-1} || canonical(event_i))`, stored in SQLite, with a `GET /ledger/verify` endpoint. It is tamper-*evident* against edits by anyone who cannot also rewrite every later hash. Anchoring the head hash externally is a FUTURE UPGRADE.

## 4. Demo (5 minutes, re-ordered)

| Time | Beat | Fallback |
|---|---|---|
| 0:00–0:25 | Problem: "an AI that reads CVs can be told what to do by the CV" | — |
| 0:25–1:25 | Upload the injected CV. Show highlighted hidden text, then show it scored 0 and flagged | Seeded case already uploaded |
| 1:25–2:20 | Ranked shortlist; open a dossier; quotes jump to the page; recruiter confirms | Replay LLM |
| 2:20–3:20 | **Climax 1:** draft invite → manager approves → edit the time → execute → **REJECTED: payload changed** | Recorded video clip |
| 3:20–4:15 | **Climax 2:** "We attack ourselves": press Run on 5 scenarios; live PASS/FAIL; then "N of 24 run, X blocked, Y unobservable", stated honestly | Last real run's report (timestamped) |
| 4:15–5:00 | Value + the limits we state honestly + roadmap | — |
