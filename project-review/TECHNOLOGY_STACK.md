# TECHNOLOGY_STACK — final selections and justification

Rule applied: a tool earns its place only if it removes more risk than it adds within 17 hours, and it must not block the final product.

## Hardware

| Item | Need | Notes |
|---|---|---|
| Team laptops | Required | Python 3.12 + Node 20 LTS on every machine. **Check Python 3.12 before the event**: SENTINEL pins `>=3.12,<3.13` and one laptop had 3.11.9 |
| GPU | Optional | Only for the local Ollama fallback. A quantized 8B model needs roughly 6–8 GB VRAM. Measure throughput on the actual laptop before relying on it |
| Network | Not required for the demo | Replay cache + local stack |

## Software

| Layer | Choice | Rejected alternatives | Why it wins |
|---|---|---|---|
| Language (backend) | **Python 3.12** | Node/TS backend | Same language as SENTINEL, pdfplumber and the LLM SDKs; one runtime |
| API | **FastAPI + Pydantic v2** | Flask, Django | Typed request/response, free OpenAPI (the frozen contract), already used inside SENTINEL |
| ORM / DB | **SQLAlchemy 2 + SQLite** (WAL mode) → PostgreSQL later | Postgres now, Mongo | Zero-ops for the hackathon. SQLAlchemy makes the later switch a config change. Atomic `UPDATE…WHERE used_at IS NULL` works on both |
| Migrations | `create_all` at hackathon → **Alembic** later | — | Don't spend hackathon time on migrations |
| Auth | **Hand-rolled**: argon2 (`argon2-cffi`) + JWT (`pyjwt`) in an httpOnly cookie → **OIDC** later | Auth0/Keycloak | No external dependency during the demo; 4 seeded users |
| Authorization | **Plain Python policy functions** + `case_members` table | Casbin, Cedar, OPA | Four roles and one resource type don't justify a policy engine. Revisit when tenants and custom roles arrive |
| PDF | **pdfplumber** (MIT) for chars/boxes + **pypdfium2** (already a pdfplumber dependency) to render pages for the ink check | PyMuPDF (AGPL: licence problem for a commercial product), Docling (heavy model download, install risk on every laptop) | pdfplumber alone misses render-mode-3 text (verified on `hidden_text.pdf`). Render + ink check measured 3/3 hidden fixtures, 0 false flags, about 10 ms/page |
| Fixture generation | **reportlab** + embedded TTF fonts (Noto Sans, Noto Naskh Arabic) + `arabic-reshaper`/`python-bidi` | The repo's stdlib generator | The current generator is ASCII-only, so it can't produce FR/AR fixtures |
| Fuzzy match | **rapidfuzz** (MIT) | difflib | Fast, has `partial_ratio` |
| LLM primary | **Whatever hosted model the team can use legally**, with JSON-schema output, temp 0 | — | Chosen by measurement (see D4), not popularity. Must handle FR/AR/EN |
| LLM fallback | **Qwen3-8B via Ollama** | HF transformers in-process | The team already ran it in SENTINEL. Ollama isolates the GPU process |
| LLM offline | **Replay cache** (JSON keyed by doc sha256 + prompt version) | — | Makes the demo deterministic and network-free |
| PII | **Regex rules (EN/FR/AR formats)** → Presidio (optional) | Presidio now | Presidio's Arabic support is weak and adds spaCy models; regex covers the synthetic fixtures |
| Async | **One background worker thread + `jobs` table** | Celery+Redis, RQ | No extra infra; sequential processing avoids SQLite write contention |
| Orchestration | **Plain Python functions** | LangGraph, LangChain, AutoGen | The pipeline is linear and the human interrupt is just a DB state. A framework adds learning cost with no gain at this size |
| Frontend | **React 18 + TypeScript + Vite** | Next.js | SPA is enough; Vite already used in SENTINEL's dashboard |
| UI kit | **One** lightweight kit the frontend dev already knows (e.g. Tailwind + a headless kit, or MUI) | Building from scratch | Speed; consistent accessibility defaults |
| API client | **openapi-typescript** generated from the frozen `openapi.json` | Hand-written fetch | The contract is enforced at compile time |
| PDF viewer | **pdf.js** (react-pdf) with highlight overlay from bbox | — | Required for "quote jumps to page" and showing hidden text |
| Testing | **pytest**, httpx `TestClient`, optional hypothesis | — | Standard |
| Assurance | **`sentinel_hr` runner** (new, ~300–500 lines estimate): httpx + pyyaml, reusing SENTINEL's metric names, JSONL traces and dashboard patterns | Reusing the SENTINEL simulator | The simulator wraps its own world; Vouch needs black-box HTTP |
| Lint/format | ruff, mypy (backend); eslint/tsc (frontend) | — | Already configured in SENTINEL |
| Packaging | `uv` (as SENTINEL), `Makefile`, optional `docker compose` | — | One command to demo |

## AI models — how to choose before the event (no benchmarks invented)

Run a 1-hour bake-off on: the 9 fixtures, 3 hand-made CVs (FR, AR, mixed FR/AR/EN) and one job offer. For each candidate model, record:
1. schema-valid response rate;
2. % of returned quotes that pass the deterministic verifier;
3. requirements covered;
4. median latency per CV;
5. whether any injected instruction changed the output structure.

Choose the best on (2), then (1). Write the numbers into the README as **measured on N synthetic CVs**.

## What was deliberately left out

LangGraph, Docling, Presidio (as a requirement), ESCO taxonomy, Celery/Redis, Kubernetes, microservices, vector DB / RAG (no Q&A axis in the MVP), fine-tuning, OCR. Each one is either optional later or has a FUTURE UPGRADE row in IMPLEMENTATION_ROADMAP.md.
