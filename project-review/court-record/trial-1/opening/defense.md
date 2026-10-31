# Opening — Defense

The charge says Vouch should not go ahead as described. The record shows a plan that lines up closely with the judging criteria and is deliberately narrow.

1. **It matches the spec's hardest requirement.** The event's golden rule is "the agent executes, the human decides about people," and it requires that "nothing is sent or recorded without human approval." Vouch makes this the core design: approval is "bound to the SHA-256 of the exact payload; expiry, replay protection, single use," and the Action Gateway is "the only executor." Most teams will show approval as a button in the UI. Vouch can show it being enforced: "payload is modified, gateway rejects." Judges looking at the Security axis will find something they can actually check.

2. **The scope is disciplined.** The plan is "ONE polished end-to-end recruitment workflow," with a long list of things it will not build ("No microservices, Kubernetes, fine-tuning, multi-agent swarms"; no HRIS, chatbot or auto-rejection). It uses a boring stack (FastAPI, SQLite, pdfplumber) and has a "deterministic fallback" if no LLM is available. That fallback means the demo still works if the model choice falls through.

3. **The ranking can be defended under questioning.** A "deterministic weighted rubric" with recruiter-set weights, evidence quotes "checked deterministically against source text," and "no automatic rejection" answer the team's own concerns that LLM "scores [are] unstable between runs" and that automation bias is a risk. It also delivers the spec's "ranked shortlist… short job-related justification."

4. **SENTINEL is a real head start, with its limits stated.** Its role is an outside tester that probes "Vouch's PUBLIC API," not the gatekeeper, so SENTINEL's audited gaps (no real approval, no RBAC) do not carry into Vouch. Twenty-four HR scenarios and 9 adversarial CVs already exist. The pitch is honest about it: "not to claim 'production-secure'," and the hash chain is "tamper-evident, not immutable."

**Concessions:**
- No Vouch code exists yet.
- The 24 scenarios have never been run.
- Team size and the model choice are still open.
- The market claims are unvalidated.

These are risks to how well the team executes. They are not flaws in the design, and the hour-by-hour schedule already budgets time for each one.
