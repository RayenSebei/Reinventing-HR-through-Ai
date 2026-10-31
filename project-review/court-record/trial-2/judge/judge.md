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
