# Vouch integration audit

## Branch contributions

`feature/hr-workspace-p0-p3` supplies the canonical authenticated Starlette service, React HR workspace, case membership, PDF evidence extraction, ranking/shortlist flow, approval gateway, scheduling/follow-ups, ledger, and 27 canonical SENTINEL scenarios.

`feature/interview-chat` supplies the timed multilingual candidate experience, deterministic question plan, CV-gap and short-answer follow-ups, transcript timing, combined evidence reporting, human-decision gate, one-time token design, and 13 live attack scenarios.

## Duplication and architectural conflict

Before integration, each branch had its own users, auth tokens, jobs/cases, candidates, proposals, approvals, outbox, reports, ledger, SQLite database, API conventions, and staff UI. Running both would produce conflicting sources of truth and inconsistent authorization.

The standalone interview staff API also lacks the HR branch's case-membership boundary. Its strengths are the candidate lifecycle and attack tests, not its parallel HR data model.

## Selected architecture

The HR branch remains canonical. The candidate lifecycle was ported into `vouch/app/chat_interview.py` and new canonical tables. Existing candidates and criteria generate a stable core question plan. The existing proposal/approval/gateway activates the link. The existing case scope protects staff transcript/report/decision routes. The existing ledger records lifecycle events.

The original `interview-chat/` directory remains as reference/provenance and an independently runnable test target, not as a second integrated service.

## Integration data flow

```text
candidate + confirmed shortlist
  -> invitation proposal + disabled hashed-token session
  -> different hiring manager approves exact payload digest
  -> gateway executes once and activates session
  -> candidate consent + timed multilingual transcript
  -> combined CV/interview report
  -> audit-recorded report opening
  -> authenticated human decision + reason
  -> scheduling/follow-up in the HR workspace
```

## Issues found and corrected

- Declared dependencies could not run Starlette TestClient reliably without its current `httpx2` dependency.
- Windows lacked IANA zone data, breaking both branches' scheduling flows; `tzdata` is now explicit.
- The branch merge only co-located two applications; canonical schema/API integration was added.
- Candidate chat links are disabled until gateway execution and cannot restart an interview.
- Candidate routes use token auth only and cannot authorize staff routes.
- The combined report must be explicitly opened by the deciding staff user.
- Prompt-like candidate text is retained for review, excluded from report evidence, and cannot alter the question plan.
- The HR evidence workspace now shows the candidate transcript, response times, combined report, flags, and human decisions.

## Remaining risks

- SQLite schema evolution is lightweight `CREATE TABLE`/`ALTER TABLE`, not a versioned migration system.
- Bearer interview links do not independently prove candidate identity.
- In-memory rate limits do not coordinate across workers.
- Raw candidate links necessarily appear in approved communication/outbox content even though the session credential is referenced by hash.
- Integrated upload remains PDF-only; standalone DOCX/TXT support was not duplicated into the canonical ingestion path.
- Browser automation could not complete on the audit host because Chromium exhausted available memory.
- The retained standalone module duplicates concepts and should eventually move to an archive/history location after the team confirms provenance requirements.
