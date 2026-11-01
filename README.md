# Reinventing HR through AI: Vouch

Our entry for the **Secure AI HR System** hackathon.

> **Vouch** helps recruiters screen CVs and draft recruitment emails. It flags suspicious document content, checks quoted evidence, and requires approval of the exact payload before the gateway sends an email. The demo includes a live synthetic attack suite to exercise these protections.

| Folder | What's inside |
|---|---|
| [`vouch/`](vouch/README.md) | **The app.** Backend, screens, tests, and the HR assistants (email summary, reply drafts, replies waiting, free interview slots, employee questions). Start here. |
| [`interview-chat/`](interview-chat/README.md) | First-round interview by chat with a timer: answers saved for HR, approvals, evidence report, audit log |
| [`sentinel_hr/`](sentinel_hr/README.md) | Runs 27 attack scenarios (24 original plus 3 route-privacy scenarios) against Vouch |
| [`sentinel/`](sentinel/documentation/scenario_catalog.md) | The attack scenario library and synthetic CVs (unchanged) |
| [`n8n/`](n8n/README.md) | n8n workflow that delivers approved emails, signature-checked |
| [`project-review/`](project-review/) | Review, court verdict, architecture and roadmap |

Quick start:

```bash
cd vouch && pip install -r requirements.txt
VOUCH_DEMO_MODE=1 python -m app --seed --yes     # first run only (wipes + seeds + starts); Windows: set VOUCH_DEMO_MODE=1 first
VOUCH_DEMO_MODE=1 python -m app                  # later starts keep the data
# open http://127.0.0.1:8000  (with VOUCH_DEMO_MODE=1 the password for all demo users is demo1234)
```

Latest local validation (2026-11-01): **222 backend tests passed** (`cd vouch && python -m pytest -q`), **45 interview-chat tests passed**, **27/27 SENTINEL scenarios passed with the `stub` model** (no real-model run yet), and the protection-removal drill turned **21/21** removed protections red (`python -m tools.drill`). The 21 Playwright smoke tests are from an earlier frontend change and were not re-run here; the new screens were checked with a headless-browser walk-through. These are synthetic demo checks, not a claim of production security.

The role-aware React workspace is available at `/`, with cases, evidence, ranking,
approvals, ledger, assurance, and administration. The demo seed includes ten
multilingual synthetic CVs, including three attack fixtures. See [the Vouch guide](vouch/README.md)
for frontend and Playwright validation commands.

The Playwright run also produces 16 workspace screenshots under
`vouch/frontend/test-results/screenshots/`. This is synthetic demo validation,
not a production security certification.
