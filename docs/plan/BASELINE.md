# Baseline (Phase 0)

## Where tests ran
- **Your PC** (Windows, `desktop-t9fdqni`): the repo at `C:\Users\moham\Reinventing-HR-through-Ai`, clean at `6d298e8` (the `git status` noise is line endings and file modes only: `git -c core.filemode=false -c core.autocrlf=true status` is empty). Its Linux VM could not install packages (no PyPI access), so suites were **not** run there.
- **Cloud workspace** (Linux, Python 3.13.18): fresh clone of `RayenSebei/Reinventing-HR-through-Ai` at the same commit. PyPI is blocked there too; the system Python already had the stack. Version differences from `vouch/requirements.txt` (record, not a blocker): starlette 1.7.0 (pinned 1.10.0), pydantic 2.13.5 (2.14.2), python-multipart 0.0.32 (0.0.33), pyjwt 2.15.0 (2.15.1), numpy 2.5.3 (2.4.6), pillow 12.3.0 (13.0.0), pytest 9.1.1 (9.2.0). `httpx 0.28.1` / `httpcore 1.0.9` (pure Python) were taken from their official GitHub tags. **Re-run once on Windows with the exact pins** (`python -m tools.verify --all`).

## Baseline at `6d298e8` (before any change)
| Suite | Result |
|---|---|
| `cd vouch && python -m pytest -q` | 29 passed (9.75 s) |
| `cd interview-chat && python -m pytest -q` | 36 passed (8.54 s) |
| `python sentinel_hr/runner.py --spawn` | 24/24 pass, 0 fail, 0 blocked, 0 error |

## After this branch
| Suite | Result |
|---|---|
| Vouch tests | 79 = 29 original + 50 new (HITL, config, n8n lint, fuzzer, secret scan) |
| interview-chat | 36 (unchanged) |
| SENTINEL | 24/24 (runner helpers gained the two new human steps; scenario library untouched) |
| Protection-removal drill | 9/9 removals turn their tests red |
| Invariant fuzzer | see EVIDENCE.md (300 sequences in CI; 10,000 full run) |
| Legacy UI, headless Chromium | login → upload → shortlist → recipient prompt → propose → manager approve → send: no console errors |

## Tool availability (selects master-plan D3/D5)
| Tool | Cloud workspace | Your PC VM |
|---|---|---|
| SQLite FTS5 | yes | yes (Python 3.10) |
| Tesseract | yes | yes |
| Docker | yes | not checked |
| Node | 22 | 24.22.0 (desktop app) |

## How to run (Windows and Linux)
```
pip install -r vouch/requirements.txt -r interview-chat/requirements.txt
python -m tools.verify --fast      # Vouch + interview-chat
python -m tools.verify --all       # + SENTINEL 24 + protection-removal drill
python -m tools.secret_scan --history
```
Golden set v0: the SENTINEL reports at `6d298e8` (`sentinel_hr/reports/latest.*`) are the saved outputs; they are unchanged by this branch.
