# Opening — Prosecution

**1. Nothing of the product exists, and the plan leaves no slack for that.**
The record says: "no confirmed Vouch code, API routes or schemas are known to exist yet" and the repo "contains ONLY a `sentinel/` folder." Seven subsystems (case creation, CV forensics, evidence dossier, rubric ranking, payload-bound approvals, deny-by-default gateway, hash-chained ledger) plus RBAC across four roles, a frontend and SENTINEL integration all have to fit into 17 hours. The schedule gives approvals and gateway two hours and the frontend two hours. Team size is still open ("about four people" vs "a two-person split"), and so is the model. Cost: the demo's key moment, "payload is modified, gateway rejects," is the last part built, so it is the part most likely to be missing.

**2. SENTINEL's live 70 seconds rests on tests that cannot run yet.**
"The scenarios are specifications, not executable tests." "16 of 24 explicitly say routes/fields 'require API-contract confirmation'." "No runner or harness code for these scenarios exists." The existing SENTINEL code has a 3.12/3.11.9 mismatch and its proven results are "NOT HR." Integration gets 1.5 hours. Cost: the largest block of the demo either fails on stage or gets faked, and faking it breaks the team's own "show real pass/fail" promise.

**3. The security claims are tested only against the team's own planted attacks.**
"Hidden-content detection only expected to be tested on the team's own planted fixtures." The fixtures are "English only," the generator "cannot produce French accents or Arabic," and there is "no PDF-metadata attack fixture," even though metadata is in the plan. The planned parser "does NOT expose text render mode." Meanwhile the team's own notes say Tunisian CVs come "in French, Arabic, English or mixed." Cost: the product's main claim, defence before the model reads untrusted documents, has no evidence behind it for the inputs real users would send.

**4. The "final product" pitch has no buyer evidence and walks into incumbents.**
"No buyer, price or market claim has been validated." Incumbents "already ship HR AI agents." Cost: judges are told to see this as a startup, and the team cannot answer who pays for it or why they would.

**5. Key requirements are left undefined.**
"'Real volumes' is undefined." It is "unclear whether 'nothing is recorded without approval' covers AI drafts, uploaded files and logs." Cost: both are scored requirements, and judges can press on either one.
