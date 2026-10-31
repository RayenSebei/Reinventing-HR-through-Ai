"""Evidence dossier: job criterion -> exact quote -> page -> status.

Statuses
  SOURCED       the candidate claims it and the quote really is in the visible CV text
  NEEDS_REVIEW  close but not exact, or something about it needs a human look
  NOT_FOUND     no supporting text found ("no evidence found", never "lacks")
  VERIFIED      reserved for a trusted outside verifier (issuer registry etc.); never set here
"""
from __future__ import annotations

import difflib
import re
import unicodedata

from . import documents, model, pii
from .lexicon import SKILLS, STOPWORDS


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).casefold()
    return re.sub(r"\s+", " ", s).strip()


def _word_rx(term: str):
    return re.compile(r"(?<![\w])" + re.escape(norm(term)) + r"(?![\w])")


def criterion_terms(c: dict) -> list[str]:
    label = norm(c["label"])
    terms = [norm(a) for a in c.get("aliases", []) if a.strip()]
    for canon, aliases in SKILLS.items():
        if any(_word_rx(t).search(label) for t in [canon] + aliases):
            terms += [norm(canon)] + [norm(a) for a in aliases]
    return list(dict.fromkeys(terms))


def key_words(c: dict) -> list[str]:
    words = re.findall(r"[\w+#.-]{3,}", norm(c["label"]))
    return [w for w in words if w not in STOPWORDS]


def _page_texts(analysis) -> dict[int, list[tuple[str, list]]]:
    pages: dict[int, list] = {}
    for page, text, words in documents.visible_lines(analysis):
        pages.setdefault(page, []).append((text, words))
    return pages


def _boxes_for(words):
    return [{"x0": min(w["x0"] for w in words), "top": min(w["top"] for w in words),
             "x1": max(w["x1"] for w in words), "bottom": max(w["bottom"] for w in words)}]


def verify_quote(quote: str, page: int, pages) -> tuple[str, list]:
    """Code-side check of a model quote against VISIBLE text of that page."""
    lines = pages.get(page) or [l for p in pages.values() for l in p]
    q = norm(quote)
    if not q:
        return "NOT_FOUND", []
    joined = " ".join(norm(t) for t, _ in lines)
    if q in joined:
        hit = [w for t, w in lines if q in norm(t) or norm(t) in q]
        return "SOURCED", _boxes_for([x for ws in hit for x in ws]) if hit else []
    # fuzzy: best window of similar length
    best = 0.0
    toks = joined.split(" ")
    qn = len(q.split(" "))
    for i in range(0, max(1, len(toks) - qn + 1)):
        cand = " ".join(toks[i:i + qn])
        best = max(best, difflib.SequenceMatcher(None, q, cand).ratio())
        if best >= 0.97:
            break
    return ("NEEDS_REVIEW", []) if best >= 0.9 else ("NOT_FOUND", [])


def lexicon_match(c: dict, pages) -> dict:
    terms = criterion_terms(c)
    keys = key_words(c)
    for page, lines in sorted(pages.items()):
        for text, words in lines:
            t = norm(text)
            hits = [term for term in terms if _word_rx(term).search(t)]
            if hits:
                repeats = max(len(_word_rx(h).findall(t)) for h in hits)
                if repeats >= 3:
                    return {"status": "NEEDS_REVIEW", "quote": text, "page": page, "boxes": _boxes_for(words),
                            "note": "Keyword repeated with no context; repetition is not evidence of experience."}
                return {"status": "SOURCED", "quote": text, "page": page, "boxes": _boxes_for(words), "note": ""}
    # fall back to the label's own key words (e.g. certification names)
    if keys:
        best = None
        for page, lines in sorted(pages.items()):
            for text, words in lines:
                t = norm(text)
                found = sum(1 for k in keys if _word_rx(k).search(t))
                if found and (best is None or found > best[0]):
                    best = (found, text, page, words)
        if best:
            found, text, page, words = best
            if found == len(keys):
                return {"status": "SOURCED", "quote": text, "page": page, "boxes": _boxes_for(words), "note": ""}
            if found * 2 >= len(keys):
                return {"status": "NEEDS_REVIEW", "quote": text, "page": page, "boxes": _boxes_for(words),
                        "note": f"Partial match ({found}/{len(keys)} key words)."}
    return {"status": "NOT_FOUND", "quote": None, "page": None, "boxes": [], "note": "No evidence found in the CV."}


def build(criteria: list[dict], analysis: dict, findings: list[dict], doc_sha: str) -> tuple[list[dict], list[dict]]:
    """Returns (evidence items, extra findings)."""
    pages = _page_texts(analysis)
    extra_findings = []
    redacted_pages = [(p, pii.redact("\n".join(t for t, _ in lines))) for p, lines in sorted(pages.items())]
    result = model.extract(criteria, redacted_pages, doc_sha)
    model_claims = {}
    if result is not None:
        if result.rejected:
            extra_findings.append({"type": "MODEL_FALLBACK", "severity": "low", "page": None,
                                   "excerpt": result.note, "boxes": []})
        valid_ids = {c["id"] for c in criteria}
        for cl in result.claims:
            if cl.criterion_id in valid_ids:
                model_claims.setdefault(cl.criterion_id, cl)

    has_date_conflict = any(f["type"] == "DATE_CONFLICT" for f in findings)
    stuffed = {t.casefold() for f in findings if f["type"] == "KEYWORD_DENSITY" for t in f.get("tokens", [])}
    items = []
    for c in criteria:
        item = None
        cl = model_claims.get(c["id"])
        if cl is not None:
            status, boxes = verify_quote(cl.quote, cl.page, pages)
            if status == "NOT_FOUND":
                extra_findings.append({"type": "UNSUPPORTED_CLAIM", "severity": "high", "page": cl.page,
                                       "excerpt": f"AI quoted text that is not in the CV: \"{cl.quote[:150]}\"", "boxes": []})
            else:
                item = {"status": status, "quote": cl.quote, "page": cl.page, "boxes": boxes,
                        "note": "" if status == "SOURCED" else "Close to the CV text but not exact.",
                        "source": f"model:{result.mode}"}
        if item is None:
            item = {**lexicon_match(c, pages), "source": "lexicon"}
        if item["status"] == "SOURCED" and item.get("quote") and stuffed and \
                any(_word_rx(tok).search(norm(item["quote"])) for tok in stuffed if tok in criterion_terms(c) or tok in key_words(c)):
            item["status"] = "NEEDS_REVIEW"
            item["note"] = "Quote comes from repeated keywords with no context; repetition is not evidence of experience."
        if item["status"] == "SOURCED" and c["kind"] == "experience" and has_date_conflict:
            item["status"] = "NEEDS_REVIEW"
            item["note"] = "Employment dates in this CV conflict; any duration is uncertain."
        if item["status"] in ("SOURCED", "NEEDS_REVIEW") and c["kind"] == "certification":
            item["note"] = (item["note"] + " " if item["note"] else "") + "Candidate claim; not independently verified."
        if item.get("quote"):
            item["quote"] = pii.redact(item["quote"])
        items.append({"criterion_id": c["id"], **item})
    return items, extra_findings
