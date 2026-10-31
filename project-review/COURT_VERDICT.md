# COURT_VERDICT — 12-juror court on Vouch + SENTINEL (retrial with repo evidence)

_Produced with the installed `/court` skill: 12 jurors, seed 216771, 17 sub-agent calls. This **retrial** used a case file extended with facts verified directly in the GitHub repo (commit 84bf25f). Parts A–C are the court's actual output, copied without edits. Part D is Claude's own assessment, labelled separately._

**Trial history:**
- **First trial** (`court-record/trial-1/`): GUILTY 11–1, based on the handover's description only.
- **Retrial** (`court-record/trial-2/`): GUILTY 11–1, after inspecting the repo.

The verdict didn't change, but the charges did. The live SENTINEL demo charge now rests on verified facts: the scenarios are prose specifications, and no runner exists. The defense gained a measured point: the rendering check catches all 3 hidden-text fixtures.

## How the real court differs from the master prompt

- The skill seats its own **fixed** 12-juror roster. It does not seat the 12 expert roles named in the master prompt.
- Jurors vote GUILTY / NOT GUILTY on "the case fails as stated". **The court produces no /10 or /100 scores**, and none were fabricated in Parts A–C.
- Sub-agents saw only the case file (Part C), not this conversation.

---

## Part A — Rendered verdict (verbatim)

# The verdict: GUILTY, 11 to 1

**The case:** Case: Build "Vouch" — a secure, evidence-first AI recruitment platform with SENTINEL as an independent AI-security assurance layer — as our team's entry to the 17-hour "Secure AI HR System" hackathon, and pitch it as a startup product to companies and HR departments.

**The charge:** The case fails as stated: it should not go ahead the way it is described.

## How the jury voted

| Juror | Vote | Why |
|---|---|---|
| The Accountant | GUILTY | The only budget actually on the table is 17 hours and a crew whose size nobody has fixed, and the described plan spends all of it on seven subsystems built from an empty workspace plus a live SENTINEL run with no harness, leaving zero contingency, while the startup pitch to companies has no buyer, no price and no unit cost (the model, and therefore its cost, is still undecided) behind it. |
| The First-Time Customer | GUILTY | As an HR buyer who has never heard of Vouch, I would not switch to it this week: the incumbents I already use ship HR AI agents, nothing of Vouch exists to try, and its security proof covers only English test CVs the team made itself, while my CVs come in French, Arabic and mixed languages. |
| The Competitor | GUILTY | As the incumbent I could ship payload-bound approvals and a hidden-text render check as a feature next quarter, and its "independent, vendor-neutral" testing pitch falls apart when the same team builds both the product and the examiner, so I would ignore it today: nothing exists, and the one thing I can't easily copy is unproven against French, Arabic or mixed CVs. |
| The Retired Judge | GUILTY | The concept is sound, but every proof the pitch relies on (the live SENTINEL pass/fail, payload-bound approvals, defence against the French and Arabic CVs real users would send) is still a plan written for an empty workspace, and a pitch built on hope dressed up as fact should not go ahead in the form described. |
| The Teenager | GUILTY | The only bit anyone would actually remember is watching live attacks get blocked on stage, and that bit has zero working code behind it, so as described this is a slideshow about a security ledger that probably crashes in the 70 seconds that matter. |
| The Engineer | GUILTY | Each piece is ordinary engineering and the payload-hash gateway is small enough to build. But the plan asks a team whose size isn't even settled to build seven subsystems, four-role per-case RBAC, a frontend, and a SENTINEL runner, clock control and test evidence export that don't exist yet, all from an empty workspace in 17 hours, so the first thing to break will be the 70-second live SENTINEL segment the demo is built around. |
| The Small-Business Owner | GUILTY | I've never opened a shop without knowing how many hands I had on day one, and this plan books seven subsystems, four-role access control, a frontend and a live test run into 17 hours starting from an empty workspace, while it still doesn't know whether two people or four are doing the work or which model it can count on. |
| The Statistician | GUILTY | Every piece of evidence offered for this plan comes from tiny samples the team built itself (9 one-page English Helvetica fixtures, 22 attacks on a non-HR corpus, all self-reported), while the plan as described needs about seven subsystems, RBAC, a frontend and a live SENTINEL harness to be built from an empty workspace and all work in sequence within 17 hours, so the odds of the whole chain working shrink with every link and nothing in the record measures any of them. |
| The Parent | GUILTY | I like that it protects the people on the other end, with no automatic rejection and a human approving every action, but as described it asks a team that still has not decided whether it is two people or four to build every safeguard from an empty workspace in 17 hours, and then stake 70 seconds of the demo on live tests that cannot run yet, so the promise of trust is bigger than what they can deliver. |
| The Investor | GUILTY | The idea is a real gap worth backing, but as described I would be paying for a seven-subsystem build plus a live test harness that has no code yet, in 17 hours, with team size and model still open and no buyer validated, so the chance of a broken demo is higher than the payoff justifies. |
| The Designer | GUILTY | A stranger watching this five-minute demo has to absorb two brands (Vouch and SENTINEL), a jargon-heavy positioning line and six segments covering seven subsystems, and the longest segment depends on tests that cannot run yet, so the one clear story (a poisoned CV gets caught, then a tampered approval gets refused) is buried under machinery. |
| The Lawyer | NOT GUILTY | Hiring is a high-liability place to put AI, but this design already holds the lines a lawyer would demand (human decides, no auto-rejection, no protected characteristics, a reason for every ranking, payload-bound approval, an audit trail), and its real gap, a missing privacy and retention position covering where CVs go, how long they are kept and how a hash-chained ledger handles deletion, is a decision the team can state, not a reason to stop. |

## Charges that stuck

1. The 70-second live SENTINEL demo, the plan's main moment, has nothing behind it yet: the scenarios are written specifications with no runner, and 16 of 24 still need the API contract confirmed (9 jurors).
2. Seven subsystems, four-role access control and a frontend, all built from an empty workspace with no Vouch code in 17 hours, leaves no slack (8 jurors).
3. Nobody has settled the team size ("about four" in one document, two in another) or the model, so no one can say who builds which block (5 jurors).

## What the defense got right

1. The design is built around the event's golden rule: each approval is tied to the SHA-256 hash of the exact payload, and one gateway is the only part allowed to act. Even jurors who voted guilty called this sound.
2. The riskiest technical piece has already been measured: on 9 fixtures, the rendering check flagged the 3 hidden-text CVs and none of the other 6, at about 10 ms per page.

## Conditions for acquittal

1. Cut the required build to case, CV upload with the rendering check, and the payload-bound approval and gateway. The evidence dossier, full ranking and four-role access control become stretch goals.
2. Freeze the API contract now, then write a runner for only the 5 demo scenarios and show them passing end to end before the clock starts.
3. Name four people, give each one a block of the schedule, pick the model, and leave contingency hours.

## The sentence

The concept stands, but the plan promises more than the record shows. This week, shrink it to one story under one name: a poisoned CV is caught, a tampered approval is refused. Make sure each claim is something you have already run. Add a short statement on where CVs go and how long they are kept.

_The full trial is in /home/claude/.court/20261031-173248: the opening statements, the rebuttals and every juror's vote._

_Made with [/court](https://github.com/alexyc9381/court-skill), a free Claude Code skill by Alex Chen ([@nocodealex](https://instagram.com/nocodealex))._

---

## Part B — Statements (verbatim)

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


# Opening — Defense

**1. It answers the brief the organizers actually wrote.** The spec's core risk is that agents "read outside content (CVs, emails) and can act", and its rule is "nothing is sent or recorded without human approval". Vouch makes that its product, not a feature: approval "bound to the SHA-256 of the exact payload; expiry, replay protection, single use", with an Action Gateway as "the only executor". Security-first beats security-bolted-on against this rubric.

**2. The scope is disciplined.** "ONE polished end-to-end recruitment workflow", and explicitly not building "HRIS, payroll... generic employee chatbot, auto-rejection". No "microservices, Kubernetes, fine-tuning, multi-agent swarms". Breadth was traded for one complete path.

**3. The demo shows proof instead of claims.** Most teams will say "secure"; this demo has "manager approves, payload is modified, gateway rejects", then runs "5 SENTINEL scenarios live... and show[s] real pass/fail". The 24 scenarios already exist with "expected API response, expected DB state, expected ledger event". So the tests are designed before the build, and the team already refuses to claim "production-secure".

**4. The riskiest technical piece has already been checked.** Hidden-text detection was measured: a rendering check "flagged the hidden text in hidden_text.pdf, white_on_white.pdf and suspicious_font_sizes.pdf, flagged nothing in the clean CV and the other five", at "roughly 10 ms per page". That fixes pdfplumber's render-mode blind spot before it costs build time.

**5. The ranking is defensible in front of HR buyers.** "Deterministic weighted rubric", "LLM... does not assign an unexplained score", "no protected characteristics; no automatic rejection", plus evidence quotes "checked deterministically against source text". This deals with the unstable-score and bias problems the team's own Tunisian notes raised.

**Concessions:** No Vouch code exists yet ("ONLY a `sentinel/` folder"). Scenarios are not executable, and 16 of 24 need API confirmation. Fixtures are English-only, so French/Arabic claims are untested. Team size and model are undecided. Market claims are "not validated with customer interviews". SENTINEL's results are self-reported and come from non-HR scenarios. These are execution risks with planned fixes, not proof the concept is wrong.


# Rebuttal — Prosecution

**1. Answers the brief — survives only in part.** It answers the approval rule, but the spec also demands "Intelligent" and "Reliable... on real volumes". "Real volumes" is undefined, and the team has not settled whether "recorded" covers drafts, uploads and logs. Answering one requirement is not answering the brief.

**2. Disciplined scope — fails.** It is one workflow, but that workflow holds ingestion, hidden-content detection, evidence dossiers, ranking, payload-bound approvals with expiry and replay protection, a gateway, a hash-chained ledger, four-role per-case RBAC, a frontend and SENTINEL integration. All of it starts from an "initially empty" workspace, with team size and model still undecided.

**3. Proof instead of claims — fails as stated.** The scenarios "are specifications, not executable tests". No runner exists, and 16 of 24 need API-contract confirmation. The live 70-second segment needs a harness, clock control and a test evidence export, all squeezed into a 1.5-hour slot. Under the team's own rules, "any critical failure is a demo blocker."

**4. Riskiest piece checked — weak.** The check showed that the planned parser misses invisible text. It was tested only on the team's own 9 one-page, English, Helvetica fixtures. There is no metadata fixture, and nothing in French or Arabic.

**5. Defensible ranking — partly survives.** A fixed rubric does deal with score instability. But the LLM still extracts the evidence, and that extraction is untested on mixed-language CVs. Automation bias, career gaps and the name-swap fairness test have no fixture.

**Concessions:** The charge is "as described." Execution *is* the case, so these risks are not side issues.

**Decide on:** can the described system, including the live SENTINEL run, be built from zero in 17 hours?


# Rebuttal — Defense

**1. Survives in part.** No code exists and team size is open, conceded. But "the last part built" is wrong: approvals and gateway are scheduled at 9–11h, before frontend (11–13h) and SENTINEL (13–14.5h); the stack (monolith, SQLite, one workflow) is deliberately small.

**2. Survives as a risk, not a fatal flaw.** No runner exists. But each scenario already states the expected response, DB state and ledger event, and the "API-contract confirmation" it awaits is the team's own API. The demo needs 5 of 24, and "blocked is never a pass" rules out faking.

**3. Partly fails.** The event permits "fictional data only," so planted fixtures are all that is allowed. The parser gap was measured and a fix found: a rendering check flagged all three hidden-text CVs, none of the other six, at about 10 ms per page. Missing French/Arabic and metadata fixtures are real but closable gaps.

**4. Survives weakly.** No buyer is validated. But the stated opening (pre-model defence against untrusted documents, vendor-neutral testing) differs from "ships HR agents." The record is silent on how judges weigh market proof.

**5. Fails as a reason to stop.** The design already draws the line: telemetry auto-logged, consequential changes and external communications need approval. "Real volumes" is undefined in the spec too; the team need only state a target.

**Decisive point:** Can the team build a real approval and gateway path in 17 hours and run a small live SENTINEL set against it? If yes, the case stands.


### Juror files (verbatim)

**juror-01**

VOTE: GUILTY
REASON: The only budget actually on the table is 17 hours and a crew whose size nobody has fixed, and the described plan spends all of it on seven subsystems built from an empty workspace plus a live SENTINEL run with no harness, leaving zero contingency, while the startup pitch to companies has no buyer, no price and no unit cost (the model, and therefore its cost, is still undecided) behind it.
DECIDING FACT: The schedule allocates every hour from 0 to 17 with no slack, yet "no confirmed Vouch code, API routes or schemas are known to exist yet," team size is "about four people" in one document and "a two-person split" in another, and no runner exists for scenarios of which "16 of 24 explicitly say routes/fields 'require API-contract confirmation'."
WOULD FLIP IF: The described scope were cut so the 17-hour schedule, at a confirmed headcount, carried real contingency hours, for example by shrinking the live SENTINEL segment to a runner pre-built for just the 5 demo scenarios.


**juror-02**

VOTE: GUILTY
REASON: As an HR buyer who has never heard of Vouch, I would not switch to it this week: the incumbents I already use ship HR AI agents, nothing of Vouch exists to try, and its security proof covers only English test CVs the team made itself, while my CVs come in French, Arabic and mixed languages.
DECIDING FACT: The repo "contains ONLY a `sentinel/` folder" with no Vouch application code, and "No buyer, price or market claim has been validated with customer interviews."
WOULD FLIP IF: A working Vouch build ran the live SENTINEL scenarios against its real API and caught hidden instructions in French/Arabic or mixed-language CVs, and at least one HR buyer confirmed they would pay for that pre-model document defence over their incumbent's agent.


**juror-03**

VOTE: GUILTY
REASON: As the incumbent I could ship payload-bound approvals and a hidden-text render check as a feature next quarter, and its "independent, vendor-neutral" testing pitch falls apart when the same team builds both the product and the examiner, so I would ignore it today: nothing exists, and the one thing I can't easily copy is unproven against French, Arabic or mixed CVs.
DECIDING FACT: The repo contains ONLY a `sentinel/` folder with no Vouch code, no runner, and 16 of 24 scenarios still needing API-contract confirmation, while incumbents (Workday, Rippling, BambooHR, HiBob) already ship HR AI agents and no buyer, price or market claim has been validated.
WOULD FLIP IF: The scope were cut to the one thing I can't copy overnight (pre-model document forensics plus the payload-bound approval and gateway path, shown working end to end on mixed French/Arabic/English fixtures), with the live SENTINEL run reduced to the few scenarios a working harness can actually execute.


**juror-04**

VOTE: GUILTY
REASON: The concept is sound, but every proof the pitch relies on (the live SENTINEL pass/fail, payload-bound approvals, defence against the French and Arabic CVs real users would send) is still a plan written for an empty workspace, and a pitch built on hope dressed up as fact should not go ahead in the form described.
DECIDING FACT: The record says the scenarios "are specifications, not executable tests": no runner or harness exists, 16 of 24 say they need API-contract confirmation, and Vouch's API did not exist when they were written. Yet the 70-second centrepiece of the demo promises "real pass/fail", with 1.5 hours set aside to integrate it.
WOULD FLIP IF: The scope were cut to what the record can support, meaning one approval-and-gateway path plus a small SENTINEL set wired to a confirmed API contract with a working runner, and the claims were limited to what those runs actually show.


**juror-05**

VOTE: GUILTY
REASON: The only bit anyone would actually remember is watching live attacks get blocked on stage, and that bit has zero working code behind it, so as described this is a slideshow about a security ledger that probably crashes in the 70 seconds that matter.
DECIDING FACT: The scenarios "are specifications, not executable tests": no runner or harness exists, 16 of 24 still need API-contract confirmation, and the repo contains ONLY a `sentinel/` folder with no Vouch code at all.
WOULD FLIP IF: The team cut the build down to the CV upload, the approval and the gateway, and had a runner that already executes the 5 demo scenarios against a working Vouch endpoint before the clock starts, so the live attack moment is real instead of hoped for.


**juror-06**

VOTE: GUILTY
REASON: Each piece is ordinary engineering and the payload-hash gateway is small enough to build. But the plan asks a team whose size isn't even settled to build seven subsystems, four-role per-case RBAC, a frontend, and a SENTINEL runner, clock control and test evidence export that don't exist yet, all from an empty workspace in 17 hours, so the first thing to break will be the 70-second live SENTINEL segment the demo is built around.
DECIDING FACT: The repo holds only the `sentinel/` folder with no Vouch code, and its 24 scenarios are prose specifications with no runner (16 of 24 still need API-contract confirmation), yet SENTINEL integration gets only the 13–14.5h slot, after everything else has to work.
WOULD FLIP IF: The team settles on four people and cuts the build to ingestion plus the rendering check, the evidence dossier, the rubric, and the approval and gateway path, with the API contract frozen in hour one and an executable runner for just the 5 demo scenarios written alongside the backend rather than at hour 13.


**juror-07**

VOTE: GUILTY
REASON: I've never opened a shop without knowing how many hands I had on day one, and this plan books seven subsystems, four-role access control, a frontend and a live test run into 17 hours starting from an empty workspace, while it still doesn't know whether two people or four are doing the work or which model it can count on.
DECIDING FACT: The team size is not settled ("about four people" in one document, a two-person split in the handover), and no Vouch code, API routes or schemas exist yet, so nobody can say who builds the 9–11h approval and gateway block that the main demo moment depends on.
WOULD FLIP IF: The team committed to at least four named people, each owning a block of the schedule, and cut the plan to what that headcount can deliver (for example, a smaller live SENTINEL set with a runner written up front), so there's slack left for a bad hour.


**juror-08**

VOTE: GUILTY
REASON: Every piece of evidence offered for this plan comes from tiny samples the team built itself (9 one-page English Helvetica fixtures, 22 attacks on a non-HR corpus, all self-reported), while the plan as described needs about seven subsystems, RBAC, a frontend and a live SENTINEL harness to be built from an empty workspace and all work in sequence within 17 hours, so the odds of the whole chain working shrink with every link and nothing in the record measures any of them.
DECIDING FACT: No Vouch code exists (the repo "contains ONLY a `sentinel/` folder") and "NO scenario has been executed against a working Vouch API"; the only measured result in the record is a hidden-text check run on 9 synthetic files.
WOULD FLIP IF: The described scope were cut so the 5-minute demo depended only on CV ingestion, the payload-bound approval and gateway, and the 5 SENTINEL scenarios, and those 5 scenarios were shown passing end to end against a running Vouch API before the event began.


**juror-09**

VOTE: GUILTY
REASON: I like that it protects the people on the other end, with no automatic rejection and a human approving every action, but as described it asks a team that still has not decided whether it is two people or four to build every safeguard from an empty workspace in 17 hours, and then stake 70 seconds of the demo on live tests that cannot run yet, so the promise of trust is bigger than what they can deliver.
DECIDING FACT: The repo contains only a `sentinel/` folder with no Vouch code, the scenarios "are specifications, not executable tests" with no runner, and 16 of 24 still "require API-contract confirmation", yet the demo promises to "show real pass/fail" live.
WOULD FLIP IF: The team confirmed its headcount and cut the plan down to the approval-plus-gateway path with a small set of SENTINEL scenarios that already have a working runner before the event, so the safety story they pitch is one they can actually show working.


**juror-10**

VOTE: GUILTY
REASON: The idea is a real gap worth backing, but as described I would be paying for a seven-subsystem build plus a live test harness that has no code yet, in 17 hours, with team size and model still open and no buyer validated, so the chance of a broken demo is higher than the payoff justifies.
DECIDING FACT: The repo contains "ONLY a `sentinel/` folder" with no Vouch backend, frontend, API or tests, and "No runner or harness code for these scenarios exists," yet the demo's biggest segment (70s) depends on running them live against that API.
WOULD FLIP IF: The scope were cut to a committed core (case, CV upload with the rendering-based hidden-text check, payload-bound approval and gateway) with a fixed team size and model, and a runnable harness for the 5 demo scenarios written against that API, so the evidence dossier, full ranking and four-role RBAC become stretch goals rather than requirements.


**juror-11**

VOTE: GUILTY
REASON: A stranger watching this five-minute demo has to absorb two brands (Vouch and SENTINEL), a jargon-heavy positioning line and six segments covering seven subsystems, and the longest segment depends on tests that cannot run yet, so the one clear story (a poisoned CV gets caught, then a tampered approval gets refused) is buried under machinery.
DECIDING FACT: The demo plan gives its largest block, 70 seconds, to running 5 SENTINEL scenarios live and showing "real pass/fail", but the record says the scenarios "are specifications, not executable tests", no runner exists, and 16 of 24 still "require API-contract confirmation" against a Vouch API that does not exist yet.
WOULD FLIP IF: The pitch were cut to one product name and one story, adversarial CV caught, then evidence-backed shortlist, then modified payload rejected by the gateway, with SENTINEL moved out of the live demo and shown as backing evidence in the README.


**juror-12**

VOTE: NOT GUILTY
REASON: Hiring is a high-liability place to put AI, but this design already holds the lines a lawyer would demand (human decides, no auto-rejection, no protected characteristics, a reason for every ranking, payload-bound approval, an audit trail), and its real gap, a missing privacy and retention position covering where CVs go, how long they are kept and how a hash-chained ledger handles deletion, is a decision the team can state, not a reason to stop.
DECIDING FACT: The plan specifies "no automatic rejection" and "no protected characteristics," and it enforces "nothing is sent or recorded without human approval" with an approval bound to the SHA-256 of the exact payload, so the product never makes the hiring decision on its own.
WOULD FLIP IF: The team pitched it to HR departments as sending candidates' CVs to a hosted external LLM (the model choice is still open) with no stated answer on consent, data location, retention and deletion, or presented the ranked shortlist as the decision rather than as input to a human.


### Judge (verbatim)

## Charges that stuck

1. The 70-second live SENTINEL demo, the plan's main moment, has nothing behind it yet: the scenarios are written specifications with no runner, and 16 of 24 still need the API contract confirmed (9 jurors).
2. Seven subsystems, four-role access control and a frontend, all built from an empty workspace with no Vouch code in 17 hours, leaves no slack (8 jurors).
3. Nobody has settled the team size ("about four" in one document, two in another) or the model, so no one can say who builds which block (5 jurors).

## What the defense got right

1. The design is built around the event's golden rule: each approval is tied to the SHA-256 hash of the exact payload, and one gateway is the only part allowed to act. Even jurors who voted guilty called this sound.
2. The riskiest technical piece has already been measured: on 9 fixtures, the rendering check flagged the 3 hidden-text CVs and none of the other 6, at about 10 ms per page.

## Conditions for acquittal

1. Cut the required build to case, CV upload with the rendering check, and the payload-bound approval and gateway. The evidence dossier, full ranking and four-role access control become stretch goals.
2. Freeze the API contract now, then write a runner for only the 5 demo scenarios and show them passing end to end before the clock starts.
3. Name four people, give each one a block of the schedule, pick the model, and leave contingency hours.

## The sentence

The concept stands, but the plan promises more than the record shows. This week, shrink it to one story under one name: a poisoned CV is caught, a tampered approval is refused. Make sure each claim is something you have already run. Add a short statement on where CVs go and how long they are kept.


---

## Part C — The case file the court saw

Case: Build "Vouch" — a secure, evidence-first AI recruitment platform with SENTINEL as an independent AI-security assurance layer — as our team's entry to the 17-hour "Secure AI HR System" hackathon, and pitch it as a startup product to companies and HR departments.

#### The event (official specification, verbatim facts)
- 17-hour hackathon. Teams act as startups, design and prototype an AI-agent solution that takes over daily HR tasks, then pitch it to companies/HR departments. Five-minute demo + final presentation + technical README + source code/workflows.
- Problem: HR teams are overloaded by resumes and emails; AI agents can help but they read outside content (CVs, emails) and can act (send, rank, record), so the solution must be smart AND trustworthy.
- Golden rule: "the agent executes, the human decides about people."
- Example functional axes (teams pick one or more, or propose their own): Resume Screening & Ranking (ranked shortlist vs a job offer, short job-related justification per candidate); Email Summary (daily digest by type/urgency, flag emails needing a human); Automatic Replies (drafts from candidate's own file, every reply human-approved); Candidate Follow-ups & Interview Scheduling (reminders, slots from recruiter calendar); Employee Questions (answers from company documents).
- Requirements: Intelligent (outputs a recruiter can use as is); Reliable (end to end, "on real volumes", without breaking); Human in the loop ("nothing is sent or recorded without human approval"); Security (AI security, system security, web application security).
- Constraints: organizers provide nothing; fictional data only, no real personal data; free choice of models, frameworks, architecture.

#### What the team plans to build (from the team's handover document)
Positioning: "secure, evidence-first AI recruitment operations platform with an independent AI security assurance layer". Not an HRIS, not a generic HR chatbot. Tagline: "Every HR AI action ships with its evidence, its authority and its approval."

Chosen scope: ONE polished end-to-end recruitment workflow:
1. Recruiter creates a recruitment case (job title, description, required skills, experience, education, criteria + weights confirmed by recruiter).
2. Upload fictional CVs: keep original, SHA-256 hash, extract text, metadata, detect suspicious content / hidden instructions, compare visible PDF content vs extracted text (white-on-white, tiny font, hidden layers, metadata, prompt injection, keyword stuffing, contradictions).
3. Evidence dossier: each job requirement mapped to an exact quote + page + status (Supported / Not established / Requires review). Quotes checked deterministically against source text. Missing evidence is not proof of absence.
4. Transparent ranking: deterministic weighted rubric (example weights skills 40 / experience 25 / education 15 / projects 20, recruiter-defined); LLM extracts/interprets evidence but does not assign an unexplained score; missing evidence shown separately; hidden text cannot inflate score; no protected characteristics; no automatic rejection.
5. AI prepares actions (follow-up, interview invitation, proposed slot, draft reply) but cannot execute.
6. Human approval: persistent backend record, correct role, bound to the SHA-256 of the exact payload; expiry, replay protection, single use. Changing recipient/time after approval invalidates it.
7. Action Gateway (deny by default, schema validation, authz, approval + payload-hash check, replay prevention) is the only executor. Trust Ledger records events with a hash chain (described as tamper-evident, not immutable). Telemetry/security logs recorded automatically; consequential record changes and external communications need approval.

Roles: Recruiter, Hiring Manager (approves), HR Admin, Auditor. Backend-enforced, resource-level (per recruitment case) authorization.

Proposed stack: React + TypeScript; Python FastAPI, Pydantic, SQLAlchemy; SQLite; pdfplumber (optional second parser); hosted LLM if allowed, else local or deterministic fallback; pytest. Modular monolith + separate SENTINEL service. No microservices, Kubernetes, fine-tuning, multi-agent swarms. Real email/calendar integrations only if core is done. Explicitly NOT building: HRIS, payroll, attendance, leave, generic employee chatbot, auto-rejection, automated hiring decisions, emotion analysis, flight-risk prediction.

14 non-negotiable security rules include: documents/emails are data not instructions; AI never approves its own actions; no external communication or consequential record change without explicit human approval; approval bound to exact payload; SENTINEL has no DB access; baseline config may only switch off AI-specific defenses, never auth/RBAC/approval/gateway.

#### SENTINEL (existing asset)
- An existing team project (~21k lines Python, plus React dashboard) built for a separate AI-agent-safety challenge, forked from an organizer's starter kit. Contains scenario schema/loader, mutation validation, static attackers, runner/evaluator, metrics (ASR attack success rate, BTU benign task utility, FBR false-block rate), JSONL traces, defenses ("authority_core", "sentinel_hybrid").
- Team's own reported results on its original (enterprise/finance/SOC, NOT HR) 62-scenario corpus: on mock model BTU=1.000, defense success 1.000; on live Qwen3-8B via Ollama, 22/22 attacks that reached the agent stopped, BTU 0.652 (8 benign shortfalls attributed to base model), false-block rate cut from 11.5% to 1.4% by sentinel_hybrid. These are team-reported, not independently verified here.
- Known limits from the team's own audit: its simulated human approval is not a real persistent approval; its ToolGateway does not authenticate users or enforce HR roles; its dashboard is a local demo service; mock model is not proof of real AI behavior; required Python 3.12 vs 3.11.9 locally.
- Planned role: independent examiner that sends synthetic attacks to Vouch's PUBLIC API and reports pass/fail/blocked/unobservable. Not the gatekeeper.
- An AI coding agent (Codex) reportedly created an HR scenario library in the GitHub repo: 24 YAML scenarios (4 each: prompt injection, authorization, approval integrity, evidence integrity, document attacks, AI policy; severity 10 critical / 9 high / 4 medium / 1 low) and 9 synthetic PDF CVs (clean, visible injection, hidden text, white-on-white, tiny font, keyword stuffing, contradictory dates, fake manager approval, fabricated qualification). Only artifact checks were done (YAML parses, IDs unique, PDFs contain markers). NO scenario has been executed against a working Vouch API. Vouch's API did not exist when scenarios were written.

#### Current state
- The Vouch application itself: the handover says the workspace was initially empty; no confirmed Vouch code, API routes or schemas are known to exist yet. The planned 17-hour schedule is a plan, not work done.
- Planned schedule: 0–1h architecture/contracts; 1–4h backend/DB/auth/data; 4–7h CV ingestion, document security, evidence; 7–9h ranking; 9–11h approvals + gateway; 11–13h frontend; 13–14.5h SENTINEL integration; 14.5–16h E2E tests/fixes; 16–17h rehearsal/README/pitch.
- Team size not settled: one document says about four people, the handover offers a two-person split.
- Model not settled: hosted LLM, local Qwen3-8B/Ollama, or deterministic fallback; no confirmed credentials, latency, or French/Arabic/English quality.

#### Demo plan (5 min)
Problem (30s) → upload adversarial CV, show original vs extracted text vs findings (50s) → evidence dossier + transparent ranked shortlist (55s) → generate interview invitation proposal, manager approves, payload is modified, gateway rejects (55s) → run 5 SENTINEL scenarios live (prompt injection, cross-case access, forged approval, payload tampering, unsupported qualification) and show real pass/fail (70s) → product value (40s). Team says not to claim "production-secure".

#### Context, notes and tensions the team itself recorded
- Team member notes (Tunisia): CVs often in French, Arabic, English or mixed; local diplomas/companies; HR may stop reading CVs and just follow the ranking (automation bias); LLM scores unstable between runs → fixed rubric, low temperature; hide name/photo/gender/age/address/nationality; test two identical CVs with different names/genders for equal rank; career changers and employment gaps get unfairly low scores; give reasons; privacy of CVs sent to external AI.
- Earlier documents opposed any aggregate ranking/score; the official spec expects a ranked shortlist, so the team switched to a transparent deterministic ranking.
- Unclear whether "nothing is recorded without approval" covers AI drafts, uploaded files and logs.
- "Real volumes" is undefined; no batch-size target.
- Hidden-content detection only expected to be tested on the team's own planted fixtures.
- A teammate separately suggested an interview chatbot for the main challenge (friends did a similar project); not in the chosen scope.
- Team research (their own, partly unverified) says incumbents (Workday, Rippling, BambooHR, HiBob) already ship HR AI agents; the claimed opening is pre-model defence against untrusted documents plus vendor-neutral independent testing. It cites a finding of hidden prompt injection in about 1% of ~196k real résumés (secondary source). No buyer, price or market claim has been validated with customer interviews.
- Alternative concepts considered in research: FlowDesk, SkillSight.

#### Verified contents of the GitHub repo (inspected directly, commit 84bf25f, 31 Oct 2026)
- The public repo RayenSebei/Reinventing-HR-through-Ai contains ONLY a `sentinel/` folder (33 files, one commit "Add SENTINEL adversarial scenario library"). There is no Vouch application code in it: no backend, frontend, API, or tests.
- Scenario library confirmed: 24 scenarios in 6 YAML files, IDs unique, 4 per category (PI prompt injection, AU authorization, AP approval integrity, EI evidence integrity, DS document security, AI policy). Severity confirmed: 10 critical, 9 high, 4 medium, 1 low.
- Each scenario has: attacker profile, preconditions, exact attack input, expected API response, expected DB state, expected ledger event, evaluation criteria, failure conditions, security principle.
- The scenarios are specifications, not executable tests. The API request steps are written in prose (e.g. "Upload the named file ... using the documented public upload operation"). 16 of 24 explicitly say routes/fields "require API-contract confirmation". The catalog says: "Do not guess routes ... map them to documented operations before running." No runner or harness code for these scenarios exists in the repo.
- Supporting docs present: threat model, scenario catalog, evaluation methodology (PASS/FAIL/BLOCKED/ERROR outcomes; blocked is never a pass; an LLM judge may not decide critical outcomes; any critical failure is a demo blocker), and a baseline-vs-protected test matrix (only AI-specific defenses may be switched off; auth, approval and gateway stay on in both).
- A fixture contract defines synthetic identities (R-ALPHA, R-BETA recruiters, M-ALPHA manager, anonymous) and per-scenario cases/proposals. Some scenarios need test-only mechanisms: AP-004 needs clock control for expiry; AP-002 needs a pre-executed proposal; state/ledger assertions need a Vouch-owned test evidence export, because SENTINEL gets no DB access.
- One synthetic job description (Junior Software Reliability Analyst: Python in a project, explain a test strategy, version control).
- 9 synthetic PDF CVs, generated by a standard-library Python script: all single-page, Helvetica, English only. The generator converts every non-ASCII character to "?", so it cannot produce French accents or Arabic. There are no French, Arabic or mixed-language fixtures, no DOCX, no scanned/image CVs, and no PDF-metadata attack fixture (although metadata attacks are listed in the plan).
- Hidden-content techniques used by the fixtures: invisible text (PDF text render mode 3) in hidden_text.pdf; white fill colour in white_on_white.pdf; 1-point text plus 72-point "PYTHON" in suspicious_font_sizes.pdf.
- Measured during this review: pdfplumber 0.11.10 (the planned parser) reports colour and size per character but does NOT expose text render mode, so hidden_text.pdf's invisible text looks like normal black text to a colour/size check. A rendering-based check (render the page with pypdfium2, a library pdfplumber already depends on, and flag characters with no ink under their box, plus size < 4 pt) flagged the hidden text in hidden_text.pdf, white_on_white.pdf and suspicious_font_sizes.pdf, flagged nothing in the clean CV and the other five, and took roughly 10 ms per page on these files. This was tested only on these 9 synthetic one-page files.

#### What the owner wants judged
The intended FINAL product (not just the prototype), on: AI design and accuracy, software architecture, systems integration, cybersecurity/privacy, UX, product scope, cost/feasibility, hidden weaknesses, and originality. The owner explicitly wants rigorous criticism, not encouragement. Question for the court: is this the right thing to build and pitch, and can it realistically be built and win as described?


---

## Part D — Claude's assessment (NOT court output)

The master prompt asks for per-lens /10 scores, a /100 total and a four-way verdict. The court produces none of these, so the figures below are **Claude's own engineering judgment** after reading the court record and the sources. They should be weighed as one reviewer's opinion, not as jury votes.

### Mapping the court's verdict to the four categories

The court found **GUILTY 11–1** on "should not go ahead *as described*". The judge's sentence was "The idea stands, but the plan does not yet." In the master prompt's terms that is **APPROVED WITH MODIFICATIONS**, conditional on the three acquittal conditions. It is not MAJOR REDESIGN: no juror attacked the core architecture. Every guilty vote was about sequencing, staffing, proof and story.

### Per-lens scores (intended final product, as planned today)

| Lens | /10 | Main reason | What blocks 10/10 |
|---|---:|---|---|
| AI Architect | 6 | Correct division: LLM extracts, code decides | FR/AR/EN extraction unmeasured; fallback has no extraction method; no eval set |
| Software Architect | 8 | Modular monolith, clear trust boundaries, deny-by-default gateway | No frozen API contract; approval semantics not yet written down |
| Hardware & Embedded | N/A | No hardware in scope | — |
| Robotics & Automation | N/A | No physical autonomy in scope | — |
| Computer Vision | N/A | Only PDF rendering, covered under security | — |
| UX/UI | 5 | Evidence-first screens are the right concept | Frontend squeezed to h11–13; two-product story; automation-bias UX not designed |
| Systems Integration | 4 | Clean separation SENTINEL ↔ public API | SENTINEL has no HTTP target runner; 24 scenarios unmapped; integration scheduled last |
| Cybersecurity | 8 | Payload-bound approvals, per-case RBAC, ledger, explicit rules | Detection tested only on own fixtures; "independent" claim premature |
| Product Manager | 6 | One workflow, strong "won't build" list | Pitch leads with the most abstract part; fairness mechanism missing |
| Technical Investor | 5 | Cheap stack, reuse of prior work | No validated buyer; incumbents can copy the gate |
| Critical Skeptic | 4 | — | Zero executed tests, zero code, schedule with no slack |
| Innovation | 7 | Pre-model document defence + adversarial assurance for HR is a real gap per team research | The moat (vendor-neutral assurance, HR attack corpus) is only claimed so far |

**Claude's overall: 59/100** (mean of the 9 applicable lenses = 5.9, scaled ×10). This scores the plan as it stands, before the redesign. With the redesign in FINAL_PROJECT_SPECIFICATION.md delivered on schedule, the gaps that drag the score down (integration, skeptic, UX) are the ones most directly addressed.

### Effect of the repo evidence on these scores

The repo confirmed the handover in every count (24 scenarios, 10/9/4/1 severities, 9 PDFs). It also showed three things the handover did not:
1. The scenarios are prose specs with no machine steps.
2. The fixtures are ASCII-only, so French and Arabic cannot be tested.
3. The planned parser misses text render mode 3.

Items 1 and 2 confirm Systems Integration at 4 and AI Architect at 6. Item 3 was also *fixed and measured* during this review (the rendering check), which supports Cybersecurity at 8. The scores are unchanged, and the overall stays **59/100**.

### Where Claude departs from the retrial judge's conditions

The judge would make the evidence dossier, full ranking and four-role access control "stretch goals". Claude keeps a **minimal** version of each in the required build, for two reasons:
- **Ranking:** the official Resume Screening axis expects "a ranked shortlist … short justification". A deterministic rubric over lexicon-found quotes is about an hour of work.
- **Access control:** demo scenario AU-001 (cross-case access) cannot PASS without per-case authorization. "Four roles" can shrink to the two the demo uses (recruiter, manager), with the other two seeded but not given screens.

Everything else in the judge's conditions is adopted.

### Disagreements visible in the court record

- **Lawyer (NOT GUILTY) vs the other 11.** The Lawyer judged legal and regulatory exposure and found the design deliberately avoids the usual traps. The other 11 judged executability and evidence. The split is about *what* was judged, not a factual dispute.
- **Defense vs prosecution on "deterministic fallback".** The defense called it a demo safety net. The prosecution noted the record never says how it extracts evidence from FR/AR CVs. The redesign resolves this (deterministic multilingual skill lexicon plus a recorded LLM replay).
- **Designer vs everyone else on SENTINEL's role.** Most jurors wanted SENTINEL proven earlier. The Designer wanted it *demoted* in the story, shown as Vouch's own test suite. The redesign takes both positions: build it earlier, present it shorter.
