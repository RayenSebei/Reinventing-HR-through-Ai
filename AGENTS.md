# AGENTS.md — standing rules for this repository (read at the start of every session)

**Product:** Vouch, an AI HR assistant (resume screening and ranking, email digest, replies, follow-ups, interview scheduling, employee Q&A). Apps: `vouch/` (base), `interview-chat/` (separate module), attack suites `sentinel/` + `sentinel_hr/`, delivery workflow `n8n/`. All data is fictional.
**Golden rule:** the agent executes, the human decides about people. Nothing is sent or recorded as a decision/action without human approval.

## Session start (always, in this order)
1. Read `docs/plan/PROGRESS.md` (where we are, what is next, open blockers). If missing, you are in Phase 0.
2. Read `docs/plan/DECISIONS.md`.
3. Read only the sections of `docs/MASTER_BUILD_PROMPT.md` and `docs/security/HARDENING_PROMPT.md` that the current phase needs (IDs are listed in the task prompt). Do not load them whole.
4. Run the baseline suites (below). If anything is red before you touch code, stop and report.

## Commands
```
cd vouch && python -m pytest -q                       # 29 tests today
cd interview-chat && python -m pytest -q              # 36 tests today
python sentinel_hr/runner.py --spawn                  # 24 attack scenarios against an isolated Vouch
cd vouch/frontend && npm ci --ignore-scripts && npm run typecheck && npm run lint && npm run build
python -m tools.verify --fast                         # once Phase 1 creates it
```
Windows is the demo platform: no bash-only steps, use `pathlib`, subprocess with argument lists, `OPENBLAS_NUM_THREADS=1` if tests run out of memory.

## Rules (non-negotiable)
1. **Read before write.** No application code edit before Phase 0 outputs exist.
2. **Additive and surgical.** New modules, wrappers, adapters. Edit existing files only at seams listed in `docs/plan/SEAM_MAP.md`, smallest possible diff. No refactors, renames, reformatting, drive-by cleanups.
3. **Protected modules:** `vouch/app/gateway.py`, `ledger.py`, `security.py`, `canonical.py`, `schemas.py`, and the SENTINEL scenario library. Change them only at a listed seam, then run all SENTINEL scenarios and the protection-removal drill.
4. **Flags:** every new behavior sits behind `FEAT_<MODULE>_MODE` or `SEC_<MODULE>_MODE` = `off|shadow|on(enforce)`. `shadow` logs what would change and changes nothing. Human-gate, authz and recipient controls go to enforce as soon as their tests pass.
5. **Tests first, red then green.** Write the failing test, run it, see it fail for the right reason, implement, see it pass. Save both runs in `docs/plan/EVIDENCE.md`. A test you never saw fail proves nothing.
6. **One ID (or tightly coupled pair) = one commit**, message `ID: summary`, with a one-line rollback in `docs/plan/CHANGELOG_MASTER.md`.
7. **Run the full baseline after every step.** A failing baseline test means stop, revert, understand. Two failed attempts at the same regression: revert and ask the human.
8. **Contracts stay valid:** API shapes, DB columns, env var names, file formats. Migrations are additive and versioned (`schema_migrations`); never edit a shipped `CREATE TABLE`.
9. **Never weaken** an existing safety check to make a test pass. Never lower a threshold in code; changing one needs a `DECISIONS.md` entry approved by the human.
10. **No network in tests, no real mail, no real personal data.** Model calls in tests use `replay` or `stub`. Only fictional data, `*.example` / `.invalid` domains.
11. **No secrets** in code, logs, prompts or fixtures. `.env.example` only.
12. **Dependencies:** none without exact pin + hash, one-line justification, stdlib alternative considered; never a version younger than 14 days. If you cannot install (no network), say so; do not vendor guesses.
13. **No weaponized exploits.** Test payloads are benign canaries containing `[[REDTEAM-CANARY-<id>]]`; sandbox tests use harmless processes that attempt forbidden actions.
14. **Do not guess.** Unclear behavior goes to `docs/plan/OPEN_QUESTIONS.md`; continue with the safest assumption, flagged.
15. **Honest claims only.** Every number in the README must come from a command in the repo. Label results `stub`, `replay` or `live`. An axis that fails its gate is switched off and listed as "Not built"; never claim it.
16. **n8n: official sources only.** Use only nodes, parameters and behaviors that exist in the official repo `https://github.com/n8n-io/n8n` (or n8n's official docs) for the pinned version; never invent nodes or features. Unconfirmed → `OPEN_QUESTIONS.md` and build the logic in Vouch. Never use "Send and Wait for Response" or any n8n wait/approval step: approvals live only in Vouch's gateway and ledger. The Webhook node has no built-in HMAC check (verify it in a Code node with `crypto.timingSafeEqual()`); the Send Email node cannot set `In-Reply-To`.

## Definition of done (per ID)
Flag works in all three modes · positive and negative tests pass · baseline suites unchanged · quality metric meets threshold (if intelligence is claimed) · failure mode tested (dependency down, bad input, concurrency) · audit event emitted · evidence in `EVIDENCE.md` · rollback documented.

## Session end (always)
Update `docs/plan/PROGRESS.md` (done, in progress, next step, blockers, exact commands to resume), commit, and post the gate or checkpoint report (max 15 lines).
