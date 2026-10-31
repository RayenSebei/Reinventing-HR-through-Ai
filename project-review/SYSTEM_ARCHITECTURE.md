# SYSTEM_ARCHITECTURE — Vouch + Vouch Assurance (SENTINEL)

## 1. Hardware architecture

There is no specialised hardware. The system is a web application.

| Node | Hackathon | Final product |
|---|---|---|
| App host | One team laptop (or a small VM) runs the FastAPI process, SQLite file and static frontend | Container on a cloud VM / PaaS; PostgreSQL managed DB |
| LLM | Hosted API **or** a laptop with a GPU running Ollama (quantized 8B) **or** replay cache | Hosted API under a data-processing agreement, or a self-hosted inference node for customers who require it |
| Assurance runner | Second terminal/process on any laptop | CI job + scheduled job, separate credentials |
| Storage | Local disk: `data/originals/` (read-only after write), `vouch.db` | Object storage for originals (versioned, encrypted), DB |

## 2. Software architecture (modular monolith)

```mermaid
flowchart TB
  subgraph Client["Browser (React + TS)"]
    UI_R[Recruiter views]
    UI_M[Manager approval view]
    UI_A[Auditor / Assurance panel]
  end

  subgraph API["FastAPI app — single process"]
    AUTH[auth + RBAC<br/>per-case scope]
    CASES[cases]
    DOCS[documents<br/>intake + hash]
    SEC[doc_security<br/>visible / hidden split + findings]
    PII[pii_minimizer]
    AI[ai_orchestrator<br/>ModelAdapter: hosted / ollama / replay]
    EVID[evidence<br/>deterministic quote verifier]
    RANK[ranking<br/>deterministic rubric]
    PROP[proposals<br/>canonical payload + sha256]
    APPR[approvals<br/>bound, expiring, single-use]
    GW[action_gateway<br/>deny-by-default]
    LEDGER[ledger<br/>hash chain + verify]
    JOBS[jobs<br/>async worker thread]
  end

  subgraph Adapters["Execution adapters (behind gateway only)"]
    OUTBOX[(sandbox outbox)]
    EMAIL[email adapter — future]
    CAL[calendar adapter — future]
  end

  DB[(SQLite → PostgreSQL)]
  FS[(originals store)]
  LLM{{LLM provider}}

  Client -->|JWT over HTTPS| AUTH
  AUTH --> CASES & DOCS & RANK & PROP & APPR & LEDGER
  DOCS --> FS
  DOCS --> JOBS
  JOBS --> SEC --> PII --> AI --> EVID --> RANK
  AI -.->|data only, no tools| LLM
  PROP --> APPR --> GW
  GW --> OUTBOX
  GW -.-> EMAIL & CAL
  CASES & DOCS & SEC & EVID & RANK & PROP & APPR & GW --> LEDGER
  API --> DB

  subgraph Assurance["Vouch Assurance (separate process, outside trust boundary)"]
    RUN[sentinel_hr runner<br/>httpx + YAML scenarios]
    REP[JSONL traces + report]
  end
  RUN -->|public API only<br/>seeded test-user creds| AUTH
  RUN --> REP --> UI_A
```

**Trust boundaries:**
1. Browser ↔ API: everything is authenticated, and authorization is enforced server-side.
2. API ↔ LLM: the LLM receives minimized text as data and returns schema-validated JSON. It is never given tools.
3. Gateway ↔ adapters: only the gateway holds adapter handles.
4. Assurance runner ↔ API: black box, the same as any client.

## 3. AI inference pipeline

```mermaid
sequenceDiagram
  participant W as Job worker
  participant S as doc_security
  participant P as pii_minimizer
  participant M as ModelAdapter
  participant V as evidence verifier
  participant R as ranking
  participant L as ledger

  W->>S: original PDF
  S-->>W: visible_text[page], hidden_text[page], findings[]
  W->>L: DOC_ANALYZED (hash, finding counts)
  W->>P: visible_text only
  P-->>W: redacted_text + redaction map (kept server-side)
  W->>M: system prompt + criteria + <document>redacted_text</document>
  alt hosted available
    M-->>W: ExtractedClaims JSON (temp 0, schema-enforced)
  else hosted down
    M-->>W: Ollama Qwen3-8B, same schema
  else demo / offline
    M-->>W: replay cache keyed by doc sha256 + prompt version
  end
  W->>W: schema validation (reject → retry once → lexicon fallback)
  W->>V: claims + visible_text
  V-->>W: evidence items SOURCED / NEEDS_REVIEW / NOT_FOUND (+ unsupported-claim findings)
  W->>R: evidence + confirmed criteria
  R-->>W: score breakdown, flags (deterministic)
  W->>L: EVIDENCE_GENERATED, RANKING_DRAFTED
```

Prompt-injection posture: hidden text never reaches the model, because only `visible_text` is sent. Visible injected text reaches the model only inside a delimited data field, and the worst case is a bad claim, which the verifier downgrades. The model has no action capability.

## 4. Approval and execution flow

```mermaid
sequenceDiagram
  actor Rec as Recruiter
  actor Mgr as Hiring manager
  participant API
  participant G as Action Gateway
  participant O as Outbox
  participant L as Ledger

  Rec->>API: POST /cases/{c}/proposals (AI draft invite)
  API->>API: canonicalize payload, sha256 → proposal(status=PENDING)
  API->>L: PROPOSAL_CREATED(hash)
  Mgr->>API: POST /proposals/{p}/approve
  API->>API: check role=MANAGER, scope(case c), approver≠proposer
  API->>L: APPROVED(hash, expires_at, nonce)
  Rec->>API: PATCH /proposals/{p} (changes time)
  API->>API: new hash ≠ approved hash
  Rec->>API: POST /proposals/{p}/execute
  API->>G: execute(p)
  G->>G: schema ✓ authz ✓ approval exists ✓ hash match ✗
  G-->>API: 409 APPROVAL_PAYLOAD_MISMATCH
  G->>L: EXECUTION_DENIED(reason)
  Note over G,O: On the happy path: atomic mark-used → write outbox → EXECUTED
```

## 5. Data model

| Table | Key fields |
|---|---|
| users | id, email, role (RECRUITER/MANAGER/HR_ADMIN/AUDITOR), password_hash |
| case_members | case_id, user_id, case_role — **resource-level scope** |
| cases | id, title, description, status, criteria_confirmed_by, confirmed_at |
| criteria | id, case_id, label, type (skill/experience/education/project), weight, aliases_ref |
| candidates | id, case_id, pseudonym, display_name (shown only to authorized users) |
| documents | id, candidate_id, sha256, path, mime, pages, uploaded_by, uploaded_at |
| findings | id, document_id, type (HIDDEN_TEXT, TINY_FONT, OVERSIZED_FONT, OFF_PAGE, INSTRUCTION_PHRASE, KEYWORD_DENSITY, DATE_CONFLICT, UNSUPPORTED_CLAIM), severity, page, bbox, excerpt |
| evidence_items | id, candidate_id, criterion_id, quote, page, status (SOURCED/NEEDS_REVIEW/NOT_FOUND; VERIFIED reserved), source (llm/lexicon), model_ref |
| rankings | id, case_id, version, status (DRAFT/CONFIRMED), confirmed_by, payload_json |
| proposals | id, case_id, candidate_id, kind, payload_json, payload_sha256, created_by, status |
| approvals | id, proposal_id, payload_sha256, approver_id, nonce, expires_at, used_at, decision |
| outbox | id, proposal_id, rendered_message, created_at (sandbox only) |
| ledger_events | seq, ts, actor, type, subject_ref, body_json, prev_hash, hash |
| jobs | id, kind, status, progress, error |
| assurance_runs | id, started_at, scenario_id, outcome, trace_path (written by the API from a runner upload, or kept runner-side) |

## 6. API surface (frozen at h1; names are proposals to confirm in code)

```
POST /auth/login                       GET  /auth/me
POST /cases                            GET  /cases            GET /cases/{c}
PUT  /cases/{c}/criteria               POST /cases/{c}/criteria/confirm
POST /cases/{c}/candidates  (multipart, 1..n PDFs) → job_id
GET  /jobs/{id}
GET  /cases/{c}/candidates             GET  /candidates/{id}
GET  /documents/{d}/extraction         GET  /documents/{d}/findings
GET  /candidates/{id}/dossier
POST /cases/{c}/ranking   (draft)      POST /cases/{c}/ranking/{v}/confirm
GET  /cases/{c}/ranking
POST /cases/{c}/proposals              GET  /cases/{c}/proposals
GET  /proposals/{p}                    PATCH /proposals/{p}
POST /proposals/{p}/approve            POST /proposals/{p}/reject
POST /proposals/{p}/execute
GET  /cases/{c}/outbox                 (observability for assurance)
GET  /ledger?case={c}                  GET  /ledger/verify
GET  /assurance/runs                   POST /assurance/runs   (triggers runner via CLI wrapper)

# test mode only (VOUCH_TEST_MODE=1, localhost, absent from production builds)
POST /_test/fixtures/{name}            loads fixture_contract identities, cases, pre-built proposal/approval states
```

Every request model sets `extra="forbid"`, `/execute` takes no body, and list routes cap `limit` (see SCENARIO_MAPPING.md §2.7).

Errors use typed codes (`FORBIDDEN_SCOPE`, `APPROVAL_EXPIRED`, `APPROVAL_PAYLOAD_MISMATCH`, `APPROVAL_REPLAY`, `SELF_APPROVAL`, `SCHEMA_INVALID`), so SENTINEL asserts on codes rather than on message text.

## 7. Where things run

| Operation | Local | Cloud | Async |
|---|---|---|---|
| Auth, RBAC, gateway, approvals, ledger, ranking, verifier | ✓ (always, deterministic) | — | — |
| PDF analysis and extraction | ✓ | — | ✓ job per document |
| LLM extraction | Ollama / replay | Hosted API | ✓ job; UI polls `/jobs` |
| Batch upload of N CVs | ✓ | — | ✓ single worker thread, sequential (SQLite-safe) |
| Assurance run | ✓ separate process | CI (future) | ✓ |
| Outbound email/calendar | — | Future adapters | ✓ outbox drain (future) |

**Real-time requirements:** none are hard. Interactive endpoints should feel instant. CV processing is asynchronous with progress, so latency budgets apply to LLM calls only. The "real volumes" target (e.g. a batch of 50 CVs) is a goal to **measure and report**, not a claim.

## 8. Failure behaviour

| Failure | Behaviour |
|---|---|
| LLM down / timeout | Retry once, then switch to the next tier; the UI shows "evidence by lexicon (reduced coverage)". The system never blocks or fabricates |
| LLM returns invalid JSON | Schema reject → one retry with repair prompt → lexicon fallback; log a finding |
| LLM claims an unsupported quote | Downgraded by the verifier; an `UNSUPPORTED_CLAIM` finding is logged |
| PDF unparsable / encrypted / scanned | Document marked `NEEDS_MANUAL_REVIEW`; the candidate is listed but not scored |
| Approval expired / reused / mismatched | 409/410 with typed code; ledger event; nothing executed |
| Gateway adapter error | Approval *not* consumed if the adapter failed before commit (transaction); ledger `EXECUTION_FAILED` |
| Ledger verify fails | Banner in the auditor view; writes continue; incident event |
| Assurance runner can't observe something | `UNOBSERVABLE`, never `PASS` |
| Wi-Fi fails at the demo | Replay LLM; local everything; backup video |

## 9. Security and privacy safeguards (mapped to the team's 14 rules)

| Rule | Mechanism |
|---|---|
| 1 Documents are data | Visible/hidden split; delimited data field; no LLM tools |
| 2–3 AI can't approve or bypass | AI has no identity in RBAC; approvals require a human session with MANAGER role |
| 4–5 No external comms or record change without approval | Gateway is the sole writer of outbox and status; confirmed-ranking gate |
| 6–7 Payload binding | D11 hash plus atomic single use |
| 8 Job-related criteria only | Criteria types are a closed enum; PII minimizer; counterfactual swap test |
| 9–10 Traceable evidence, no fabricated negatives | Verifier; `NOT_FOUND` ≠ "lacks" |
| 11 SENTINEL has no DB access | Separate process, HTTP credentials only |
| 12 Authz on in every config | Baseline toggles only `AI_DEFENSES` (hidden split, minimizer, verifier); auth/RBAC/gateway have no switch |
| 13 No real data | Synthetic fixtures; upload size/type limits |
| 14 No auto-decisions | No reject endpoint exists; shortlist requires confirmation |

Web basics: password hashing (argon2/bcrypt), short-lived JWT in an httpOnly cookie, CSRF protection for cookie auth, CORS locked to the frontend origin, upload limits (size, PDF magic bytes), no HTML rendering of CV content (text only), rate limiting on login, and secrets in `.env` (never committed; `.env.example` only).

## 10. Deployment

- **Hackathon:** `make demo` → seeds the DB, starts uvicorn and the Vite preview, and warms the replay cache. Optionally use one `docker compose` file (app + optional Ollama). No cloud dependency.
- **Final:** one container image, managed Postgres, object storage, OIDC, and CI running unit, integration and full assurance on every PR. Deploy blocks on any critical scenario FAIL.

## 11. Testing and validation

| Layer | What | Tool |
|---|---|---|
| Unit | canonical hash, approval state machine, verifier, ranking determinism, ledger chain, visibility flags | pytest |
| Property | ranking order invariant to candidate order; hidden text never changes the score | hypothesis (optional) |
| Fixture | 9 PDFs → expected findings; 3 multilingual CVs → expected evidence | pytest + golden files |
| Integration | full workflow through HTTP | pytest + httpx TestClient |
| Adversarial | 24 scenarios via `sentinel_hr` (same assertions exported to pytest) | runner |
| Fairness | counterfactual pairs (same CV, different name/gender) → identical score | pytest |
| Demo | timed rehearsal ×2 with the network off | stopwatch |
