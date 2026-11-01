# Vouch product demo — narration script

Voice: Piper TTS (open source), voice `en_US-lessac-medium`, generated offline. Every claim was checked against the running app.

| Time | Section | Narration |
|---|---|---|
| 00:00.35 | Intro | Meet Vouch: a secure hiring workspace, where AI does the reading, and people make every decision. |
| 00:07.24 | 01 · Overview | Sara, a recruiter, starts on her overview: ten CVs analysed, seven security findings flagged for review, and one pipeline from CV to conversation. Nobody is rejected automatically. |
| 00:21.22 | 02 · Recruitment | Each role has a weighted scorecard. Vouch extracts evidence from every CV, and highlights the exact quote on the original page, so every score can be traced back to its source. |
| 00:34.01 | 03 · Candidates | Candidates stay pseudonymous until the shortlist is confirmed. Hidden instructions and keyword stuffing are flagged as findings for a person to review, instead of being silently scored. |
| 00:45.62 | 04 · AI Inbox | The AI Inbox previews how candidate messages will be grouped, summarised, and answered. In this demo, the messages are synthetic samples, and no mailbox is connected. |
| 00:58.29 | 05 · Interviews | Interviews and internal meetings share one calendar. For each interview, Vouch suggests a format: an AI chat first round, a recruiter, or senior HR, and explains why. The recruiter makes the call. |
| 01:13.73 | 06 · Follow-ups | Follow-ups keep the team on track: confirming interviews, collecting feedback, and reviewing flagged CVs. A reminder never sends anything on its own. |
| 01:24.26 | 07 · Approvals | Nothing reaches a candidate without approval. The hiring manager approves the exact message and its fingerprint. Change a single character, and the approval no longer matches. |
| 01:35.82 | 08 · Audit Ledger | Every approval, edit, and refusal is written to an append-only ledger. Each event is linked to the one before it by a hash, so the full trail can be checked. |
| 01:46.52 | 09 · Security & Assurance | In its latest recorded run, Vouch passed all 24 of its attack scenarios. Tested, not just promised. |
| 01:54.74 | Outro | Vouch. Evidence you can trace. People in control. |

## Claims and where they are verified

| Claim | Seen in the app |
|---|---|
| Ten CVs analysed, seven security findings | Overview KPI cards and 'The evidence shield' (demo seed) |
| Nobody is rejected automatically | Overview pipeline note and sign-in page |
| Quote highlighted on the original page | Recruitment > case > Evidence (green boxes on the CV page) |
| Pseudonymous until the shortlist is confirmed | Candidates page subtitle: 'Names appear only after a confirmed shortlist' |
| Hidden instructions and keyword stuffing flagged | Candidates 'Findings' column: Instruction phrase, Metadata instruction, Keyword density |
| AI Inbox is a preview with synthetic samples, no mailbox | AI Inbox banner 'Demonstration inbox… No mailbox, AI model, approval, or delivery is connected' |
| Format suggestion with reasons, recruiter decides | Interviews > interview > 'Recommended interview format', 'Accept suggestion' |
| A reminder never sends anything | Follow-ups note: 'Tasks are reminders only. Completing one does not send a message or approve an action.' |
| Approval of the exact message and its fingerprint; a change breaks the match | Approvals: 'Current payload SHA-256', 'Approve this exact payload'; SENTINEL AP-003 |
| Append-only ledger linked by hashes | Audit Ledger: 'Append-only events linked by hashes' |
| 24 of 24 attack scenarios passed in the latest recorded run | Security & Assurance: '24/24 scenarios passed', model mode stub, with the app's caveat 'not a guarantee of production safety' |
