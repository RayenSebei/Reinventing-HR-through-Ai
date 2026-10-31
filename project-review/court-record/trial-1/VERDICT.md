# The verdict: GUILTY, 11 to 1

**The case:** Case: Build "Vouch" — a secure, evidence-first AI recruitment platform with SENTINEL as an independent AI-security assurance layer — as our team's entry to the 17-hour "Secure AI HR System" hackathon, and pitch it as a startup product to companies and HR departments.

**The charge:** The case fails as stated: it should not go ahead the way it is described.

## How the jury voted

| Juror | Vote | Why |
|---|---|---|
| The Accountant | GUILTY | You can't cost a 17-hour build when nobody knows if there are two people or four to do it, so the labor budget could be half what's needed, and the pitch asks HR buyers for money with no validated buyer or price and only team-reported or secondary-source numbers behind it. |
| The First-Time Customer | GUILTY | As an HR buyer seeing this for the first time, I'm being asked to trust an "independent assurance layer" that has never once been run against the product, which doesn't exist yet, and I'd be switching away from the Workday or BambooHR agents I already have with no price and no other customer to point to, so I wouldn't buy it this week as described. |
| The Competitor | GUILTY | If I were Workday or a rival team, I'd copy the payload-bound approval gate as a feature and ignore the rest, because the one thing I can't easily copy, "independent" assurance, is SENTINEL testing an API that doesn't exist yet with attacks written by the same team that builds the defense, and it is booked for the last hours of a schedule with no slack. |
| The Retired Judge | GUILTY | Every claim that this can be built and demonstrated in 17 hours is a plan, not proof, and the defense itself concedes that no Vouch code exists, no scenario has ever run, and neither the team size nor the model is settled, so the case as described rests on hope rather than on evidence in the record. |
| The Teenager | GUILTY | The only part anyone in that room will actually remember is the live "we hacked it and it blocked us" moment, and it's crammed into hours 13 to 14.5 on an app that doesn't exist yet, so as described you're betting the whole hype beat on stuff nobody has ever run, and the rest is hash chains and evidence dossiers that put people to sleep. |
| The Engineer | GUILTY | The approval gateway and hash checks are small, buildable code, but the plan as described starts from an empty workspace, tries to build PDF forensics, quote-verified dossiers, four-role per-case RBAC, a ledger, a frontend and SENTINEL integration in 17 hours with no settled team or model, and leaves integration of the pitch's headline differentiator for hours 13–14.5 with no fallback, so the part most likely to break is the part the demo depends on. |
| The Small-Business Owner | GUILTY | I've never opened a shop without knowing who's behind the counter on Monday, and this plan fills every one of 17 hours with no slack and still doesn't know whether two people or four are doing the work, so as written it's a gamble, even if the idea underneath is sound. |
| The Statistician | GUILTY | The plan has a sample size of zero (no Vouch code, zero of 24 scenarios executed, SENTINEL's numbers come from a non-HR corpus and the team reported them itself), and it chains about nine sequential components into a schedule with no slack, so even if each step is fairly likely to work, the odds that all of them work on stage are poor. |
| The Parent | GUILTY | As a parent I don't let the family stake everything on one trip where the car isn't built yet, and this plan puts its whole pitch on two live moments, the gateway rejection and SENTINEL's pass/fail, scheduled last on code that doesn't exist, with no backup if they fail on stage. |
| The Investor | GUILTY | The design is smart and fits what the judges score, but I would not put my money into a plan where nothing is built, the team size and model are still undecided, both payoff moments of the demo (the gateway rejection and SENTINEL's live pass/fail) are scheduled last with no fallback, and even the defense's fixes (moving integration earlier, cutting the forensics) admit the plan does not work as described. |
| The Designer | GUILTY | A stranger could follow the tagline and the "payload is modified, gateway rejects" moment in five seconds, but as described the pitch asks them to learn two products (Vouch and SENTINEL) and a jargon-stacked positioning line in five minutes, and the screens they would judge get only two hours, built after everything else. |
| The Lawyer | NOT GUILTY | Recruitment AI usually gets into legal trouble through automated decisions about people, discrimination and personal data, and this plan deliberately avoids each one (fictional data only, no auto-rejection, no protected characteristics, human approval bound to the exact payload); the gaps I do see are where real CVs would go and the unproven word "independent" in the pitch, both of which can be fixed with clearer terms and wording, so they are not reasons to stop. |

## Charges that stuck

1. The 70-second SENTINEL demo, the pitch's headline, relies on scenarios that have never run against a Vouch API, and that API does not exist yet (10 jurors).
2. The build starts from nothing, the schedule has no slack, and the team size (two or four) and the model are both undecided (7 jurors).
3. The gateway rejection and SENTINEL's live results are scheduled last, with no fallback if they fail (6 jurors).

## What the defense got right

1. Approval bound to the exact payload, enforced by a gateway, answers the event's golden rule. Even jurors who voted guilty called it smart and buildable.
2. The plan avoids recruitment AI's usual legal traps: no auto-rejection, no protected characteristics, fictional data only.

## Conditions for acquittal

1. Freeze the API contract first. Then run the 5 demo scenarios against a thin approval-and-gateway slice by about hour 7.
2. Fix the headcount and the model now, give each person their hours, and limit the forensics to the fixtures you will demo.
3. Record a backup video of both live moments.

## The sentence

The idea stands, but the plan does not yet. Settle the team and the model this week, and build the two payoff moments first. Bring a recording as backup, and do not call SENTINEL "independent" until its attacks have hit real code. The record does not say whether work before the event is allowed, so ask the organizers.

_The full trial is in /home/claude/.court/20261031-170223: the opening statements, the rebuttals and every juror's vote._

_Made with [/court](https://github.com/alexyc9381/court-skill), a free Claude Code skill by Alex Chen ([@nocodealex](https://instagram.com/nocodealex))._
