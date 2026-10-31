# Vouch / SENTINEL Threat Model

## Scope and trust boundary

Vouch is the recruitment workflow under test. SENTINEL is an external adversarial client of Vouch's **public API**. SENTINEL has no database credentials, private service credentials, approval authority, or permission to bypass Vouch's controls. A Vouch-controlled test fixture service may provision synthetic identities/data and provide narrowly scoped assertions; it must not grant SENTINEL direct database access.

## Assets requiring protection

- Candidate CVs, extracted text, contact data, case records, and cross-candidate/tenant confidentiality.
- Evidence claims, source spans, verification status, provenance, and uncertainty.
- Job descriptions, recruiter/manager identities, roles, approval artifacts, and approval-to-payload binding.
- Interview proposals, execution requests, idempotency/replay state, and external side effects.
- Trust Ledger integrity, event attribution, ordering, and tamper evidence.
- System/developer prompts, model/provider secrets, service credentials, and internal configuration.
- Availability and integrity of document parsing, API, model, and action processing.
- Fair, job-related, and policy-compliant decision support.

## Threat actors

1. **Malicious candidate** controlling document content, metadata, text visibility, and fabricated claims.
2. **Malicious or compromised recruiter** with legitimate but limited case access, attempting role escalation, cross-case access, or action tampering.
3. **Unauthorized external user** lacking valid authentication or case-level authorization.
4. **Compromised hiring manager account** or malicious manager attempting approval misuse; tests must still preserve attribution, payload binding, and replay constraints.
5. **Malicious/compromised integration caller** replaying or mutating public API requests.
6. **Model failure or prompt injection** causing unsupported, privacy-invasive, biased, or action-seeking output.
7. **Parser/extractor discrepancy** adversary exploiting rendering, OCR, font, metadata, or parser differences.

## Trust boundaries and attack surfaces

- Public API ingress: authentication, request validation, rate limits, object-level authorization, and error responses.
- Uploaded file boundary: MIME/content validation, size limits, malware handling, PDF parsing, OCR, metadata, hidden layers, and extraction.
- Untrusted text to AI boundary: CVs, job descriptions, recruiter notes, and retrieved records must remain data, not control instructions.
- Evidence Engine to dossier boundary: source provenance, quotes, verification states, unsupported inferences, and candidate association.
- Proposal/approval boundary: recruiter request, distinct manager identity, approval expiry, canonical payload hash, and state transitions.
- Action Gateway to external action boundary: authorization, approval, payload integrity, expiry, replay/idempotency, and exactly-once or explicitly idempotent semantics.
- Trust Ledger boundary: append-only/tamper-evident audit data, trustworthy actor identity, and no secret leakage.
- Test boundary: SENTINEL may send public requests and inspect public responses. Internal state is test-oracle evidence supplied by Vouch, not SENTINEL database access.

## AI-specific risks vs. ordinary backend vulnerabilities

**AI-specific:** direct/indirect prompt injection; hidden or visually deceptive document instructions; retrieval/context contamination; fabricated quotes, credentials, timelines, and confidence; omission of adverse/contradictory evidence; leakage of prompts or unrelated candidate data through generated text; unfair/protected-trait inference; AI output treated as authorization or action.

**Ordinary backend/security:** authentication failures; object-level authorization/IDOR; mass assignment and client-controlled role/actor fields; weak input validation; excessive data exposure; insecure upload/parser handling; race conditions; approval forgery; payload substitution; expired approval acceptance; replay; idempotency errors; cross-tenant query leakage; unsafe errors; ledger integrity issues; denial of service.

AI defenses do not compensate for backend authorization. Backend controls must remain enabled in every test configuration.

## Security assumptions to validate

- Principal identity/role comes from a trusted authentication context, not request-body claims.
- Every case/document/proposal read and mutation is authorization-checked server-side.
- CV and job-description content is untrusted regardless of file, formatting, or role.
- Evidence can be traced to source spans and claims are distinguished from verified facts.
- The Action Gateway independently validates authorization, manager approval, payload binding, expiry, and replay state.
- Approval is attributed to a distinct authorized manager and consumed/bound according to a documented state machine.
- Ledger events accurately reflect accepted and denied transitions without embedding unnecessary secrets/PII.
- The API exposes enough documented responses or Vouch-owned test evidence to assert state without database access.
- The test environment is isolated, synthetic, and incapable of triggering real interviews or contacting real people.

## Potential failure modes

- Hidden prompt injection changes ranking, suppresses evidence, leaks data, or initiates a proposal.
- AI output contains fabricated or misquoted evidence marked verified.
- Candidate-controlled approval text/token is accepted as manager approval.
- Recruiter can read another case or promote their role via identifier/body manipulation.
- Approval reused after success/expiry, or applied to a different payload.
- Document parser omits, invents, or silently truncates text; detector claims are confused with prevention.
- API response, error, pagination metadata, or ledger exposes cross-case or sensitive data.
- Ledger omits, misattributes, duplicates, or fabricates significant security events.
- Aggregate metrics hide a critical unauthorized execution/disclosure.

## Risk handling

Use synthetic data and non-delivering action adapters. Run baseline and protected comparisons only with backend authentication/authorization, manager approval, and Action Gateway controls enabled in both. Report prevention separately from detection. A flagged malicious document that still caused a side effect is a failure; a safe outcome with no detector warning may pass prevention but fail a detection objective. Do not claim security from unobservable state: mark the assertion blocked until Vouch provides a public/test evidence contract.
