# Rebuttal — Prosecution

1. **Matches the hardest requirement: survives only as design.** Payload-bound approval is the right idea, but none of it exists. Approvals and the gateway sit at hours 9–11, after everything else has to work, and the team still hasn't settled whether "nothing is recorded without approval" covers drafts, uploads and logs.

2. **Disciplined scope: fails.** The feature list is short, but the depth is not. From an empty workspace it needs hidden-content PDF forensics, a quote-verified evidence dossier, a ranking engine, payload-hashed approvals, a gateway, a hash-chained ledger, four-role per-case RBAC, a frontend and SENTINEL integration, all in 17 hours with team size unknown (two or four people). The record never says how the "deterministic fallback" would pull evidence out of French, Arabic or mixed CVs, so it does not protect the "Intelligent" requirement.

3. **Defensible ranking: partly survives.** The arithmetic is deterministic, but its inputs come from LLM extraction. Quality in French and Arabic is unknown, and the record names no fix for its own career-changer and employment-gap concern.

4. **SENTINEL head start: weak.** The 24 scenarios were written before Vouch's API existed. They have never been run and will have to be rebuilt against whatever API exists by then. SENTINEL integration gets 1.5 hours (13–14.5h), there is a Python 3.12 vs 3.11.9 mismatch, and 70 seconds of the demo depend on it.

**Concessions:** "the schedule budgets time" is not true. The schedule has no slack, and it cannot budget for a team or a model that hasn't been chosen.

**Decisive point:** The pitch's value rests on two live moments, the gateway rejecting a tampered payload and SENTINEL's real pass/fail. Both are scheduled last, on a system that doesn't exist yet, with no fallback described if either fails.
