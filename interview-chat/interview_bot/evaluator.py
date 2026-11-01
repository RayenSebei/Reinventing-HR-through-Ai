"""Evidence extraction and the report HR reads.

Design choices (from the team's notes):
- The LLM only EXTRACTS quotes. Every quote is checked verbatim against the
  source; quotes that are not found are dropped and counted (hallucination guard).
- The LEVEL per requirement is computed by fixed code (a rubric), not by the
  model, so the same evidence always gives the same result.
- No overall score, no hire/reject recommendation. The report says what is
  supported, what is missing, and what HR should ask next.
- The evaluator sees anonymised text (alias, PII masked).
"""
from . import llm, prompts
from .config import PROMPT_VERSION, RUBRIC_VERSION
from .security import sha256
from .textutil import keyword_hit, quote_found, sentences

MAX_QUOTES = 3


def _trim_words(text: str, n: int) -> str:
    words = text.split()
    return " ".join(words[:n])


def _mock_quotes(requirements: list, text: str, max_words: int) -> dict:
    out = {}
    sents = sentences(text)
    for req in requirements:
        hits = [s for s in sents if any(keyword_hit(s, k) for k in req.get("keywords", []))]
        out[req["id"]] = [_trim_words(s, max_words) for s in hits[:MAX_QUOTES]]
    return {"requirements": out}


def _verify(requirements: list, raw: dict, source: str) -> tuple[dict, int]:
    """Keep only quotes found verbatim in the source. Returns (quotes, dropped_count)."""
    found, dropped = {}, 0
    proposed = (raw or {}).get("requirements", {}) or {}
    for req in requirements:
        quotes = proposed.get(req["id"], []) or []
        if not isinstance(quotes, list):
            quotes = []
        keep = []
        for q in quotes[:MAX_QUOTES]:
            if isinstance(q, str) and quote_found(source, q):
                keep.append(q.strip())
            else:
                dropped += 1
        found[req["id"]] = keep
    return found, dropped


def cv_evidence(job_spec: dict, cv_text: str) -> dict:
    reqs = job_spec["requirements"]
    raw = llm.complete_json(
        "cv_evidence", prompts.CV_EVIDENCE_SYSTEM, prompts.cv_evidence_user(reqs, cv_text),
        mock=lambda: _mock_quotes(reqs, cv_text, 25),
    )
    quotes, dropped = _verify(reqs, raw, cv_text)
    return {"quotes": quotes, "unverified_quotes_dropped": dropped,
            "fallback_used": bool(raw.get("_fallback")), "model": llm.model_name(),
            "prompt_version": PROMPT_VERSION}


def gaps(job_spec: dict, cv_ev: dict) -> list:
    """Requirements with no CV evidence, must-haves first."""
    missing = [r for r in job_spec["requirements"] if not cv_ev["quotes"].get(r["id"])]
    return sorted(missing, key=lambda r: (not r.get("must_have", False), r["id"]))


def interview_evidence(job_spec: dict, candidate_lines: list[dict]) -> dict:
    reqs = job_spec["requirements"]
    transcript = "\n".join(f"[{m.get('question_id') or '-'}] Candidate: {m['text']}" for m in candidate_lines)
    source = "\n".join(m["text"] for m in candidate_lines)
    raw = llm.complete_json(
        "interview_evidence", prompts.INTERVIEW_EVIDENCE_SYSTEM,
        prompts.interview_evidence_user(reqs, transcript),
        mock=lambda: _mock_quotes(reqs, source, 30),
    )
    quotes, dropped = _verify(reqs, raw, source)
    return {"quotes": quotes, "unverified_quotes_dropped": dropped, "fallback_used": bool(raw.get("_fallback")),
            "transcript_sha256": sha256(source)}


LEVELS = {
    2: ("supported_cv_and_interview", "Evidence in CV and interview"),
    1: ("supported_one_source", "Evidence in one source only"),
    0: ("no_evidence", "No evidence found"),
}


def build_report(job_spec: dict, candidate: dict, cv_ev: dict, iv_ev: dict | None,
                 flagged_messages: list, short_answers: int, cv_findings: dict) -> dict:
    rows, must_total, must_ok, any_ok = [], 0, 0, 0
    missing_labels, ask_next = [], []
    for req in job_spec["requirements"]:
        cvq = cv_ev["quotes"].get(req["id"], [])
        ivq = (iv_ev or {}).get("quotes", {}).get(req["id"], []) if iv_ev else []
        level = (1 if cvq else 0) + (1 if ivq else 0)
        code, label = LEVELS[level]
        if req.get("must_have"):
            must_total += 1
            must_ok += 1 if level else 0
        any_ok += 1 if level else 0
        if level == 0:
            missing_labels.append(req["label"])
        if level < 2:
            ask_next.append(f"Ask for a concrete example of: {req['label']}")
        rows.append({"id": req["id"], "requirement": req["label"], "must_have": bool(req.get("must_have")),
                     "level": code, "level_label": label, "cv_quotes": cvq, "interview_quotes": ivq})

    total = len(job_spec["requirements"])
    summary = f"Evidence for {any_ok}/{total} requirements (must-have: {must_ok}/{must_total})."
    if missing_labels:
        summary += " No evidence yet: " + "; ".join(missing_labels) + "."

    review_flags = []
    if cv_findings.get("hidden_count"):
        review_flags.append({"type": "cv_hidden_content",
                             "detail": f"{cv_findings['hidden_count']} hidden element(s) removed from the CV before analysis. "
                                       "Open the CV and decide; this is not an automatic rejection."})
    if flagged_messages:
        review_flags.append({"type": "interview_manipulation_attempt",
                             "detail": f"{len(flagged_messages)} message(s) looked like instructions to the AI. "
                                       "They were not used as evidence and did not change the rules. Read them in the transcript."})
    if short_answers:
        review_flags.append({"type": "short_answers",
                             "detail": f"{short_answers} very short answer(s). This can reflect language, nerves or "
                                       "connection issues; consider a human call before concluding."})
    dropped = cv_ev.get("unverified_quotes_dropped", 0) + (iv_ev or {}).get("unverified_quotes_dropped", 0)
    if dropped:
        review_flags.append({"type": "unverified_ai_quotes_dropped",
                             "detail": f"{dropped} AI-proposed quote(s) were not found in the source and were removed."})
    if cv_ev.get("fallback_used") or (iv_ev or {}).get("fallback_used"):
        review_flags.append({"type": "llm_fallback", "detail": "The AI model was unavailable; the offline keyword method was used."})

    return {
        "candidate_alias": candidate["alias"],
        "summary": summary,
        "requirements": rows,
        "counts": {"with_evidence": any_ok, "total": total, "must_have_with_evidence": must_ok,
                   "must_have_total": must_total},
        "suggested_questions_for_human_interview": ask_next[:5],
        "review_flags": review_flags,
        "interview_completed": iv_ev is not None,
        "human_decision_required": True,
        "notice": "This report lists evidence only. It is not a decision. A human must review the CV and the "
                  "transcript and record the decision with a reason.",
        "provenance": {"model": llm.model_name(), "prompt_version": PROMPT_VERSION, "rubric_version": RUBRIC_VERSION,
                       "cv_sha256": candidate.get("cv_sha256"),
                       "transcript_sha256": (iv_ev or {}).get("transcript_sha256"),
                       "anonymised_input": True},
    }


def sort_key(report: dict) -> tuple:
    """Suggested review order: must-have evidence first, then all evidence. Ties keep alias order."""
    c = report["counts"]
    strong = sum(1 for r in report["requirements"] if r["level"] == "supported_cv_and_interview")
    return (-c["must_have_with_evidence"], -c["with_evidence"], -strong)
