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
