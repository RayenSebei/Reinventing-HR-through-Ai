# Record register (HI-01, first version)

Every table, the code that writes it, and its class: **A** audit (automatic, append-only) · **D** draft (automatic, labelled, never a decision) · **H** decision (needs a human actor) · **X** action (only via proposal → approval → gateway).

| Table | Written by | Class | Human gate |
|---|---|---|---|
| `ledger` | `ledger.append/record` (everywhere) | A | — |
| `findings` | `cases.upload_cv`, `regenerate_dossier`, `_reevaluate_case` | A | — |
| `delivery_attempts` (new) | `delivery.deliver` | A | — |
| `documents` | `cases.upload_cv` | D | upload by a recruiter |
| `evidence_items` | `cases.upload_cv`, `regenerate_dossier`, `_reevaluate_case` | D | — |
| `evidence_archive` (new) | `cases.set_criteria` | A | — |
| `rankings` status `DRAFT` | `cases.draft_ranking` | D | — |
| `reviews` (new) | `reviews.record` via `GET /candidates/{id}/dossier` only | A | the user opening it |
| `cases`, `case_members` | `cases.create_case` | H | recruiter |
| `criteria` + `cases.criteria_confirmed_*` | `set_criteria`, `confirm_criteria` | H | recruiter |
| `rankings` status `CONFIRMED` | `cases.confirm_ranking` | H | recruiter, **server-side review gate** |
| `contact_confirmations` (new) | `contacts.confirm` | H | recruiter on the case |
| `proposals` | `gateway.create_proposal`, `edit_proposal` | D (a draft until approved) | recruiter |
| `approvals` | `gateway.decide` | H | hiring manager on the case, not the creator |
| `outbox` | `gateway.execute` only | X | approval used + matching hash; **DB trigger** + unique per proposal |
| `users` | `seed.py`, `testmode.reset` | setup | seed/test only |

Automatically recorded without a human: audit events, findings, evidence, draft rankings, reviews (as audit of what a person opened), delivery attempts.
Recorded only with a human: criteria, shortlist, recipient, approvals, rejections.
Leaves the system only with an approval: outbox rows and anything n8n sends.

Not yet enforced: a test that scans every `INSERT`/`UPDATE` in `app/` against this register (planned, HI-01 completion).
