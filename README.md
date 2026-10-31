# Reinventing HR through AI: Vouch

Our entry for the **Secure AI HR System** hackathon.

> **Vouch** lets an AI screen CVs and draft recruitment emails, but it can't be tricked by a CV, can't make claims it can't quote, and can't send anything a manager didn't approve. And we prove it by attacking it live.

| Folder | What's inside |
|---|---|
| [`vouch/`](vouch/README.md) | **The app.** Backend, screens, tests. Start here. |
| [`sentinel_hr/`](sentinel_hr/README.md) | Runs our 24 attack scenarios against Vouch, plus extra test CVs (French, Arabic, ...) |
| [`sentinel/`](sentinel/documentation/scenario_catalog.md) | The attack scenario library and synthetic CVs (unchanged) |
| [`n8n/`](n8n/README.md) | n8n workflow that delivers approved emails, signature-checked |
| [`project-review/`](project-review/) | Review, court verdict, architecture and roadmap |

Quick start:

```bash
cd vouch && pip install -r requirements.txt && python -m app --seed
# open http://127.0.0.1:8000  (password for all demo users: demo1234)
```

Current results: **24/24 attack scenarios blocked**, and **19/19 tests pass**. These come from our own tests on synthetic data, not a claim of production security.
