# Reinventing HR through AI: Vouch

Our entry for the **Secure AI HR System** hackathon.

> **Vouch** helps recruiters screen CVs and draft recruitment emails. It flags suspicious document content, checks quoted evidence, and requires approval of the exact payload before the gateway sends an email. The demo includes a live synthetic attack suite to exercise these protections.

| Folder | What's inside |
|---|---|
| [`vouch/`](vouch/README.md) | **The app.** Backend, screens, tests. Start here. |
| [`interview-chat/`](interview-chat/README.md) | First-round interview by chat with a timer: answers saved for HR, approvals, evidence report, audit log |
| [`sentinel_hr/`](sentinel_hr/README.md) | Runs our 24 attack scenarios against Vouch, plus extra test CVs (French, Arabic, ...) |
| [`sentinel/`](sentinel/documentation/scenario_catalog.md) | The attack scenario library and synthetic CVs (unchanged) |
| [`n8n/`](n8n/README.md) | n8n workflow that delivers approved emails, signature-checked |
| [`project-review/`](project-review/) | Review, court verdict, architecture and roadmap |

Quick start:

```bash
cd vouch && pip install -r requirements.txt && VOUCH_DEMO=1 python -m app --seed
# open http://127.0.0.1:8000  (with VOUCH_DEMO=1 the demo password is demo1234;
# without it, --seed prints a one-time random password)
# Windows PowerShell: $env:VOUCH_DEMO="1"; python -m app --seed

python -m tools.verify --all   # every test suite, the 24 attacks and the protection-removal drill
```

Current results: **24/24 attack scenarios blocked**, and **29/29 tests pass** (19 existing tests plus 10 dashboard tests). These come from our own tests on synthetic data, not a claim of production security. The committed attack report uses the stub model; a real-model run remains a separate validation step.

The dashboard v2 Phase 1 preview is now available at `/`. It includes a live,
role-scoped Command Center and keeps the operational screens at `/legacy`.
See [the checkpoint](docs/dashboard-checkpoint.md), [architecture review](docs/architecture-review.md),
and [dashboard plan](docs/dashboard-plan.md) for the scope and remaining work.

Validation at this checkpoint: 29 tests pass (including the original 24 attack
scenarios), plus frontend typecheck, lint and production build. This is synthetic
demo validation, not a production security certification.
