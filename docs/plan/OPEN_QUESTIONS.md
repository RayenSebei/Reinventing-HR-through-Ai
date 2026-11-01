# Open questions for the team

1. **Confirm the decisions in DECISIONS.md**, especially the two that change how you start the demo: `VOUCH_DEMO_MODE=1` for the `demo1234` password, and `VOUCH_OUTBOUND_MODE=live` to send through n8n.
2. **Companion security prompt** `docs/security/HARDENING_PROMPT.md` is missing from the repo. Add it, or confirm the master plan's wording is enough.
3. **n8n version to pin** for the demo (master plan decision 12). The workflow is verified against n8n 2.46.0 source.
4. **Remove Duplicates in n8n:** test on your pinned n8n what the webhook answers when a duplicate is dropped; then decide whether to add it (RESIDUAL_RISK.md row 1).
5. **Master plan Section 12 decisions** (axes that ship, clock budget, real model and budget, FR/AR template reviewers, fairness ε, approver personas, mailbox and calendar sources, holiday data owner, interview-chat in the pitch) are still unanswered; defaults apply.
6. **JWT secret:** still random per process unless `VOUCH_JWT_SECRET` is set (WA-05, Phase 8). OK for the demo?
