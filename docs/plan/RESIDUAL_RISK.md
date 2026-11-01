# Residual risk (this pass)

| Risk | Why it remains | Compensating control | Owner | Next step |
|---|---|---|---|---|
| Duplicate email if n8n sent it but its answer to Vouch was lost, then a human presses Retry | Vouch cannot know whether the SMTP send happened; n8n Remove Duplicates not adopted (see N8N_VERIFICATION.md) | Retry is human-only, max `VOUCH_MAX_DELIVERY_ATTEMPTS`, same approved bytes, every attempt ledgered; `Idempotency-Key: outbox_id` header sent | team | Test Remove Duplicates on the pinned n8n and decide |
| n8n workflow not executed on a real n8n in this pass | n8n could not be installed here | Node types, versions and parameters checked against the official source; static lint tests | team | Import once before the demo (N8N_VERIFICATION.md) |
| Suites not run on the Windows demo machine with the exact pinned versions | Its VM has no PyPI access | Ran in a Linux workspace with near-identical versions (BASELINE.md) | team | `python -m tools.verify --all` on Windows |
| History secret scan only covered the shallow clone in the workspace | Full history lives on your PC | Scanner is stdlib; CI runs it with full history (`fetch-depth: 0`) | CI | First CI run |
| Fuzzer covers the gateway/recipient/kill-switch invariants (I1, I2, I4, I5, I6, I9), not yet I3, I7, I8, I10–I14 | Those need decision records, slot bookings and KB, not built yet | SENTINEL AU-* cover case scoping (I7) | team | Extend with Phases 5–7 |
| Every remaining row of master Section 6 not marked DONE in GROUND_TRUTH.md | Phases 3–10 not started | — | team | Follow the phase plan |
