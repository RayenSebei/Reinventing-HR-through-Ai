# Opening — Defense

**1. It answers the brief the organizers actually wrote.** The spec's core risk is that agents "read outside content (CVs, emails) and can act", and its rule is "nothing is sent or recorded without human approval". Vouch makes that its product, not a feature: approval "bound to the SHA-256 of the exact payload; expiry, replay protection, single use", with an Action Gateway as "the only executor". Security-first beats security-bolted-on against this rubric.

**2. The scope is disciplined.** "ONE polished end-to-end recruitment workflow", and explicitly not building "HRIS, payroll... generic employee chatbot, auto-rejection". No "microservices, Kubernetes, fine-tuning, multi-agent swarms". Breadth was traded for one complete path.

**3. The demo shows proof instead of claims.** Most teams will say "secure"; this demo has "manager approves, payload is modified, gateway rejects", then runs "5 SENTINEL scenarios live... and show[s] real pass/fail". The 24 scenarios already exist with "expected API response, expected DB state, expected ledger event". So the tests are designed before the build, and the team already refuses to claim "production-secure".

**4. The riskiest technical piece has already been checked.** Hidden-text detection was measured: a rendering check "flagged the hidden text in hidden_text.pdf, white_on_white.pdf and suspicious_font_sizes.pdf, flagged nothing in the clean CV and the other five", at "roughly 10 ms per page". That fixes pdfplumber's render-mode blind spot before it costs build time.

**5. The ranking is defensible in front of HR buyers.** "Deterministic weighted rubric", "LLM... does not assign an unexplained score", "no protected characteristics; no automatic rejection", plus evidence quotes "checked deterministically against source text". This deals with the unstable-score and bias problems the team's own Tunisian notes raised.

**Concessions:** No Vouch code exists yet ("ONLY a `sentinel/` folder"). Scenarios are not executable, and 16 of 24 need API confirmation. Fixtures are English-only, so French/Arabic claims are untested. Team size and model are undecided. Market claims are "not validated with customer interviews". SENTINEL's results are self-reported and come from non-HR scenarios. These are execution risks with planned fixes, not proof the concept is wrong.
