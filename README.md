# Reinventing HR through AI: Vouch

Our entry for the **Secure AI HR System** hackathon.

> **Vouch** helps recruiters screen CVs and draft recruitment emails. It flags suspicious document content, checks quoted evidence, and requires approval of the exact payload before the gateway sends an email. The demo includes a live synthetic attack suite to exercise these protections.

| Folder | What's inside |
|---|---|
| [`vouch/`](vouch/README.md) | **The app.** Backend, screens, tests. Start here. |
| [`interview-chat/`](interview-chat/README.md) | First-round interview by chat with a timer: answers saved for HR, approvals, evidence report, audit log |
| [`sentinel_hr/`](sentinel_hr/README.md) | Runs 27 attack scenarios (24 original plus 3 route-privacy scenarios) against Vouch |
| [`sentinel/`](sentinel/documentation/scenario_catalog.md) | The attack scenario library and synthetic CVs (unchanged) |
| [`n8n/`](n8n/README.md) | n8n workflow that delivers approved emails, signature-checked |
| [`project-review/`](project-review/) | Review, court verdict, architecture and roadmap |

Quick start:

```bash
cd vouch && pip install -r requirements.txt
VOUCH_DEMO_MODE=1 python -m app --seed --yes     # Windows: set VOUCH_DEMO_MODE=1 first
VOUCH_DEMO_MODE=1 python -m app
# open http://127.0.0.1:8000  (with VOUCH_DEMO_MODE=1 the password for all demo users is demo1234)
```

Latest local validation: **52 backend tests passed**, including all 27 SENTINEL scenarios; **21 Playwright smoke tests passed** across four roles, two resolutions and both themes. Browser CSP checks found no violations. These are synthetic demo checks, not a claim of production security; a real-model run remains separate validation.

The role-aware React workspace is available at `/`, with cases, evidence, ranking,
approvals, ledger, assurance, and administration. The demo seed includes ten
multilingual synthetic CVs, including three attack fixtures. See [the Vouch guide](vouch/README.md)
for frontend and Playwright validation commands.

The Playwright run also produces 16 workspace screenshots under
`vouch/frontend/test-results/screenshots/`. This is synthetic demo validation,
not a production security certification.
