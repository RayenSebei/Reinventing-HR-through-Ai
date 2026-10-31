# Architecture review — dashboard v2

This is a bounded code review, not a production-security certification. Existing
synthetic tests establish specific behavior, not universal protection.

| Finding | Impact | Disposition |
| --- | --- | --- |
| Prior UI counts the default page of candidates/cases | Totals become inaccurate over 50 items | New overview aggregates all permitted records |
| Editing an approved proposal retains its stored APPROVED status | UI can suggest it is sendable although the gateway rejects it | Overview derives effective state from latest approval, hash, use and expiry |
| Pending proposals have no expiry timestamp | A countdown on a pending card would invent semantics | Show waiting duration; countdown only after approval |
| extraction.visible_text precedes PII redaction | Cannot label it as the exact AI input | Phase 2 must label it visible extracted text, with a redaction explanation |
| set_criteria deletes rows referenced by evidence_items | Saving criteria after CV analysis raises a foreign-key failure | Confirmed by schema/code; preserve original evidence. Safe migration/re-analysis design required before changing backend |
| Top-three dossier review gate exists only in frontend | Direct API callers can confirm a draft without reading dossiers | Documented limitation; server enforcement would require an authorized API design change |
| Gateway checks and use update are not one full transaction | Multi-worker/racing edits need a concurrency audit | Current synchronous single-process server serializes these calls; do not advertise multi-worker safety |
| PDF analysis and network model calls run synchronously | One expensive upload can delay other requests | Future worker queue, bounded resource limits and database migration needed |
| Ledger GET lacks previous hash | Phase 3 cannot infer a global previous hash from a filtered case list | New overview can expose previous hashes for its scoped recent events; full timeline design deferred |
| Assurance status exposes only running | No real per-attack progress is available | Use indeterminate progress, not a fabricated percentage |
| Global assurance report is a synthetic fixture result | Easily mistaken for live model or independent validation | Always display report model, timestamp, and self-authored synthetic disclaimer |
| SQLite DB, original PDFs and session secret are local | Demo deployment differs from hardened production | Keep loopback binding, explicit demo notice and no external delivery by default |

Protected security modules remain unchanged. Changes to these findings outside
the approved read-only overview/static-serving scope need a follow-up decision.

## Repository improvements in this checkpoint

Reproducible frontend build, exact dependency versions, local fonts, committed
assets for Python-only startup, explicit security and metric semantics, architecture
notes, overview regression tests, and frontend safety lint. CI validates these
contracts. Screenshots provide a concrete design approval checkpoint.
