"""Deterministic, explainable ranking. No AI decides a score.

score = sum(weight * value) / 100 with SOURCED=1, NEEDS_REVIEW=0.5, NOT_FOUND=0.
Nobody is rejected. Candidates with document findings are flagged for review,
never penalised or hidden (a planted trick may not be the candidate's own doing).
"""
from __future__ import annotations

from . import policy

VALUE = {"SOURCED": 2, "VERIFIED": 2, "NEEDS_REVIEW": 1, "NOT_FOUND": 0}   # half-points, kept as ints


def rank(criteria: list[dict], candidates: list[dict]) -> list[dict]:
    rows = []
    review_threshold = policy.read()["review_weight_threshold"]
    for cand in candidates:
        ev = {e["criterion_id"]: e for e in cand["evidence"]}
        half_points = 0
        breakdown, missing = [], []
        review_weight = 0
        for c in criteria:
            e = ev.get(c["id"], {"status": "NOT_FOUND"})
            pts = c["weight"] * VALUE[e["status"]]
            half_points += pts
            breakdown.append({"criterion": c["label"], "weight": c["weight"], "status": e["status"]})
            if e["status"] == "NOT_FOUND":
                missing.append(c["label"])
            if e["status"] == "NEEDS_REVIEW":
                review_weight += c["weight"]
        score = (half_points + 1) // 2   # round half-points up deterministically
        flags = []
        if review_weight > review_threshold:
            flags.append("BORDERLINE_REVIEW")
        if cand["finding_count"]:
            flags.append("DOCUMENT_FINDINGS")
        met = sum(1 for b in breakdown if b["status"] == "SOURCED")
        why = f"Matches {met}/{len(criteria)} criteria with quotes from the CV"
        if missing:
            why += f"; no evidence found for: {', '.join(missing)}"
        rows.append({"candidate_id": cand["id"], "pseudonym": cand["pseudonym"], "score": score,
                     "breakdown": breakdown, "missing": missing, "flags": flags, "justification": why + "."})
    rows.sort(key=lambda r: (-r["score"], r["pseudonym"]))
    for i, r in enumerate(rows):
        r["position"] = 1 + sum(1 for x in rows if x["score"] > r["score"])   # ties share a position
    return rows
