Case: Build "Vouch" — a secure, evidence-first AI recruitment platform with SENTINEL as an independent AI-security assurance layer — as our team's entry to the 17-hour "Secure AI HR System" hackathon, and pitch it as a startup product to companies and HR departments.

## The event (official specification, verbatim facts)
- 17-hour hackathon. Teams act as startups, design and prototype an AI-agent solution that takes over daily HR tasks, then pitch it to companies/HR departments. Five-minute demo + final presentation + technical README + source code/workflows.
- Problem: HR teams are overloaded by resumes and emails; AI agents can help but they read outside content (CVs, emails) and can act (send, rank, record), so the solution must be smart AND trustworthy.
- Golden rule: "the agent executes, the human decides about people."
- Example functional axes (teams pick one or more, or propose their own): Resume Screening & Ranking (ranked shortlist vs a job offer, short job-related justification per candidate); Email Summary (daily digest by type/urgency, flag emails needing a human); Automatic Replies (drafts from candidate's own file, every reply human-approved); Candidate Follow-ups & Interview Scheduling (reminders, slots from recruiter calendar); Employee Questions (answers from company documents).
- Requirements: Intelligent (outputs a recruiter can use as is); Reliable (end to end, "on real volumes", without breaking); Human in the loop ("nothing is sent or recorded without human approval"); Security (AI security, system security, web application security).
- Constraints: organizers provide nothing; fictional data only, no real personal data; free choice of models, frameworks, architecture.

## What the team plans to build (from the team's handover document)
Positioning: "secure, evidence-first AI recruitment operations platform with an independent AI security assurance layer". Not an HRIS, not a generic HR chatbot. Tagline: "Every HR AI action ships with its evidence, its authority and its approval."

Chosen scope: ONE polished end-to-end recruitment workflow:
1. Recruiter creates a recruitment case (job title, description, required skills, experience, education, criteria + weights confirmed by recruiter).
2. Upload fictional CVs: keep original, SHA-256 hash, extract text, metadata, detect suspicious content / hidden instructions, compare visible PDF content vs extracted text (white-on-white, tiny font, hidden layers, metadata, prompt injection, keyword stuffing, contradictions).
3. Evidence dossier: each job requirement mapped to an exact quote + page + status (Supported / Not established / Requires review). Quotes checked deterministically against source text. Missing evidence is not proof of absence.
4. Transparent ranking: deterministic weighted rubric (example weights skills 40 / experience 25 / education 15 / projects 20, recruiter-defined); LLM extracts/interprets evidence but does not assign an unexplained score; missing evidence shown separately; hidden text cannot inflate score; no protected characteristics; no automatic rejection.
5. AI prepares actions (follow-up, interview invitation, proposed slot, draft reply) but cannot execute.
6. Human approval: persistent backend record, correct role, bound to the SHA-256 of the exact payload; expiry, replay protection, single use. Changing recipient/time after approval invalidates it.
7. Action Gateway (deny by default, schema validation, authz, approval + payload-hash check, replay prevention) is the only executor. Trust Ledger records events with a hash chain (described as tamper-evident, not immutable). Telemetry/security logs recorded automatically; consequential record changes and external communications need approval.

Roles: Recruiter, Hiring Manager (approves), HR Admin, Auditor. Backend-enforced, resource-level (per recruitment case) authorization.

Proposed stack: React + TypeScript; Python FastAPI, Pydantic, SQLAlchemy; SQLite; pdfplumber (optional second parser); hosted LLM if allowed, else local or deterministic fallback; pytest. Modular monolith + separate SENTINEL service. No microservices, Kubernetes, fine-tuning, multi-agent swarms. Real email/calendar integrations only if core is done. Explicitly NOT building: HRIS, payroll, attendance, leave, generic employee chatbot, auto-rejection, automated hiring decisions, emotion analysis, flight-risk prediction.

14 non-negotiable security rules include: documents/emails are data not instructions; AI never approves its own actions; no external communication or consequential record change without explicit human approval; approval bound to exact payload; SENTINEL has no DB access; baseline config may only switch off AI-specific defenses, never auth/RBAC/approval/gateway.

## SENTINEL (existing asset)
- An existing team project (~21k lines Python, plus React dashboard) built for a separate AI-agent-safety challenge, forked from an organizer's starter kit. Contains scenario schema/loader, mutation validation, static attackers, runner/evaluator, metrics (ASR attack success rate, BTU benign task utility, FBR false-block rate), JSONL traces, defenses ("authority_core", "sentinel_hybrid").
- Team's own reported results on its original (enterprise/finance/SOC, NOT HR) 62-scenario corpus: on mock model BTU=1.000, defense success 1.000; on live Qwen3-8B via Ollama, 22/22 attacks that reached the agent stopped, BTU 0.652 (8 benign shortfalls attributed to base model), false-block rate cut from 11.5% to 1.4% by sentinel_hybrid. These are team-reported, not independently verified here.
- Known limits from the team's own audit: its simulated human approval is not a real persistent approval; its ToolGateway does not authenticate users or enforce HR roles; its dashboard is a local demo service; mock model is not proof of real AI behavior; required Python 3.12 vs 3.11.9 locally.
- Planned role: independent examiner that sends synthetic attacks to Vouch's PUBLIC API and reports pass/fail/blocked/unobservable. Not the gatekeeper.
- An AI coding agent (Codex) reportedly created an HR scenario library in the GitHub repo: 24 YAML scenarios (4 each: prompt injection, authorization, approval integrity, evidence integrity, document attacks, AI policy; severity 10 critical / 9 high / 4 medium / 1 low) and 9 synthetic PDF CVs (clean, visible injection, hidden text, white-on-white, tiny font, keyword stuffing, contradictory dates, fake manager approval, fabricated qualification). Only artifact checks were done (YAML parses, IDs unique, PDFs contain markers). NO scenario has been executed against a working Vouch API. Vouch's API did not exist when scenarios were written.

## Current state
- The Vouch application itself: the handover says the workspace was initially empty; no confirmed Vouch code, API routes or schemas are known to exist yet. The planned 17-hour schedule is a plan, not work done.
- Planned schedule: 0–1h architecture/contracts; 1–4h backend/DB/auth/data; 4–7h CV ingestion, document security, evidence; 7–9h ranking; 9–11h approvals + gateway; 11–13h frontend; 13–14.5h SENTINEL integration; 14.5–16h E2E tests/fixes; 16–17h rehearsal/README/pitch.
- Team size not settled: one document says about four people, the handover offers a two-person split.
- Model not settled: hosted LLM, local Qwen3-8B/Ollama, or deterministic fallback; no confirmed credentials, latency, or French/Arabic/English quality.

## Demo plan (5 min)
Problem (30s) → upload adversarial CV, show original vs extracted text vs findings (50s) → evidence dossier + transparent ranked shortlist (55s) → generate interview invitation proposal, manager approves, payload is modified, gateway rejects (55s) → run 5 SENTINEL scenarios live (prompt injection, cross-case access, forged approval, payload tampering, unsupported qualification) and show real pass/fail (70s) → product value (40s). Team says not to claim "production-secure".

## Context, notes and tensions the team itself recorded
- Team member notes (Tunisia): CVs often in French, Arabic, English or mixed; local diplomas/companies; HR may stop reading CVs and just follow the ranking (automation bias); LLM scores unstable between runs → fixed rubric, low temperature; hide name/photo/gender/age/address/nationality; test two identical CVs with different names/genders for equal rank; career changers and employment gaps get unfairly low scores; give reasons; privacy of CVs sent to external AI.
- Earlier documents opposed any aggregate ranking/score; the official spec expects a ranked shortlist, so the team switched to a transparent deterministic ranking.
- Unclear whether "nothing is recorded without approval" covers AI drafts, uploaded files and logs.
- "Real volumes" is undefined; no batch-size target.
- Hidden-content detection only expected to be tested on the team's own planted fixtures.
- A teammate separately suggested an interview chatbot for the main challenge (friends did a similar project); not in the chosen scope.
- Team research (their own, partly unverified) says incumbents (Workday, Rippling, BambooHR, HiBob) already ship HR AI agents; the claimed opening is pre-model defence against untrusted documents plus vendor-neutral independent testing. It cites a finding of hidden prompt injection in about 1% of ~196k real résumés (secondary source). No buyer, price or market claim has been validated with customer interviews.
- Alternative concepts considered in research: FlowDesk, SkillSight.

## What the owner wants judged
The intended FINAL product (not just the prototype), on: AI design and accuracy, software architecture, systems integration, cybersecurity/privacy, UX, product scope, cost/feasibility, hidden weaknesses, and originality. The owner explicitly wants rigorous criticism, not encouragement. Question for the court: is this the right thing to build and pitch, and can it realistically be built and win as described?
