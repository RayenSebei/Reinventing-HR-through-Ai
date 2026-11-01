"""F5: employee questions answered only from the company's HR policy documents.

Retrieval is BM25 over the sections of the Markdown files in vouch/policies (English and French
question words map to the same terms). The answer is the matching section, quoted, with its title, so
every answer cites a real passage. When no section matches well enough, or the question is personal
(someone's pay, health, a complaint about a named person), the assistant says it does not know and
points to HR. The question text is untrusted data: it is never executed and never stored; the ledger
holds only its hash and the cited section.
"""
from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter
from functools import lru_cache

from . import config, db, documents, ledger

POLICY_DIR = config.ROOT / "policies"
K1, B = 1.4, 0.75
MIN_SCORE = 2.2          # below this the best section is not a real match: abstain
MIN_COVERAGE = 0.5       # share of the question's content words the cited section must contain

_STOP = set("""a an the and or of to in on for at by with from is are be was were do does did can could should would
may might will i me my we our you your it its this that these those what which who whom how when where why if
there here have has had not no any some much many more most please tell know about get got want need en le la les
un une des du de et ou est sont je j mon ma mes nous vous votre vos il elle ce cette ces quel quelle quels quelles
comment quand ou pourquoi combien est ce qu que qui pour par avec sur dans pas ne plus peux peut puis faire fait
dois doit avoir ai received receive got asking asks ask do""".split())

SYNONYMS = {
    "vacation": "leave", "vacations": "leave", "holiday": "leave", "holidays": "leave", "conge": "leave",
    "conges": "leave", "pto": "leave", "days off": "leave", "off": "leave",
    "sick": "sick", "ill": "sick", "illness": "sick", "maladie": "sick", "malade": "sick",
    "remote": "remote", "telework": "remote", "teletravail": "remote", "home": "remote", "wfh": "remote",
    "maternity": "parental", "paternity": "parental", "baby": "parental", "parent": "parental",
    "expense": "expenses", "frais": "expenses", "reimbursement": "reimbursed", "reimburse": "reimbursed",
    "rembourse": "reimbursed", "remboursement": "reimbursed",
    "course": "training", "courses": "training", "formation": "training", "certification": "training",
    "conference": "training", "budget": "budget",
    "laptop": "equipment", "computer": "equipment", "ordinateur": "equipment", "materiel": "equipment",
    "hours": "hours", "horaires": "hours", "heures": "hours", "schedule": "hours",
    "overtime": "overtime", "supplementaires": "overtime",
    "harassment": "harassment", "harcelement": "harassment", "discrimination": "harassment",
    "phishing": "phishing", "hameconnage": "phishing", "password": "password", "scam": "phishing",
    "probation": "probation", "essai": "probation", "notice": "notice", "preavis": "notice",
    "resign": "leaving", "resignation": "leaving", "quit": "leaving", "demission": "leaving",
    "carry": "carried", "rollover": "carried",
    "jour": "day", "jours": "day", "days": "day", "an": "year", "annee": "year", "annuel": "annual", "annuelle": "annual",
    "suspicious": "phishing", "suspect": "phishing", "suspecte": "phishing", "fake": "phishing",
    "mot": "password", "passe": "password",
    "unused": "unused", "use": "unused", "used": "unused", "extra": "overtime", "additional": "overtime",
    "insult": "harassment", "insults": "harassment", "bully": "harassment", "bullying": "harassment",
    "harass": "harassment", "harcele": "harassment", "resigning": "leaving", "resigned": "leaving",
    "feries": "public", "ferie": "public", "periode": "period", "duree": "period",
    "start": "hours", "begin": "hours", "core": "core",
    "abroad": "country", "pays": "country", "etranger": "country",
}

PERSONAL = re.compile(
    r"\b(?:salary of|how much does \w+ earn|salaire de \w+|is \w+ (?:sick|pregnant|ill)|"
    r"my diagnosis|medical record of|dossier médical de|fire \w+|licencier \w+)\b", re.IGNORECASE)


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def tokens(text: str) -> list[str]:
    folded = _fold(text)
    for phrase, term in (("days off", "leave"), ("time off", "leave"), ("working hours", "hours")):
        folded = folded.replace(phrase, term)
    out = []
    for w in re.findall(r"[a-z0-9]+", folded):
        if w in _STOP or len(w) < 2:
            continue
        w = SYNONYMS.get(w, w)
        if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(SYNONYMS.get(w, w))
    return out


@lru_cache(maxsize=1)
def corpus() -> tuple[list[dict], dict, float]:
    passages = []
    for path in sorted(POLICY_DIR.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        doc_title, section, buf = path.stem, None, []

        def flush():
            if section and buf:
                text = " ".join(line for line in buf if not documents.is_instruction_text(line)).strip()
                if text:
                    passages.append({"id": f"{path.stem}#{len(passages) + 1}", "doc": path.name,
                                     "doc_title": doc_title, "section": section, "text": text})

        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                doc_title = line[2:].strip()
            elif line.startswith("## "):
                flush()
                section, buf = line[3:].strip(), []
            elif line.strip():
                buf.append(line.strip())
        flush()
    for p in passages:
        p["tf"] = Counter(tokens(p["section"] + " " + p["section"] + " " + p["text"]))
        p["len"] = sum(p["tf"].values())
    df = Counter(t for p in passages for t in p["tf"])
    avg = sum(p["len"] for p in passages) / max(len(passages), 1)
    return passages, df, avg


def _bm25(query: list[str], p: dict, df: dict, n: int, avg: float) -> float:
    score = 0.0
    for t in set(query):
        f = p["tf"].get(t, 0)
        if not f:
            continue
        idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
        score += idf * f * (K1 + 1) / (f + K1 * (1 - B + B * p["len"] / avg))
    return score


def answer(question: str) -> dict:
    passages, df, avg = corpus()
    q = tokens(question)
    base = {"question_sha256": hashlib.sha256(question.encode()).hexdigest()}
    if PERSONAL.search(question):
        return {**base, "abstained": True, "reason": "personal",
                "answer": "This is about a specific person's private situation, so I can't answer it from the handbook. "
                          "Please talk to HR directly; they handle it confidentially.", "citation": None, "related": []}
    if documents.is_instruction_text(question):
        return {**base, "abstained": True, "reason": "instruction",
                "answer": "I only answer questions about the HR handbook. Instructions to the assistant are ignored.",
                "citation": None, "related": []}
    if not q:
        return {**base, "abstained": True, "reason": "unclear", "answer": "Could you rephrase the question with a bit more detail?",
                "citation": None, "related": []}
    ranked = sorted(((_bm25(q, p, df, len(passages), avg), p) for p in passages), key=lambda x: -x[0])
    best_score, best = ranked[0]
    known = {t for t in q if df.get(t)}          # words the handbook never uses cannot be "missing" from a section
    coverage = sum(1 for t in known if t in best["tf"]) / len(known) if known else 0.0
    related = [{"doc": p["doc"], "doc_title": p["doc_title"], "section": p["section"], "id": p["id"]}
               for s, p in ranked[1:4] if s >= MIN_SCORE * 0.6][:2]
    overall = sum(1 for t in set(q) if t in best["tf"]) / len(set(q))
    if best_score < MIN_SCORE or coverage < MIN_COVERAGE or overall < 0.34:
        return {**base, "abstained": True, "reason": "not_in_handbook",
                "answer": "I could not find this in the HR handbook, so I won't guess. Please ask HR directly.",
                "citation": None, "related": related, "score": round(best_score, 2)}
    return {**base, "abstained": False, "reason": None, "answer": best["text"],
            "citation": {"doc": best["doc"], "doc_title": best["doc_title"], "section": best["section"], "id": best["id"]},
            "related": related, "score": round(best_score, 2), "confidence": "high" if coverage >= 0.8 else "medium"}


def ask(user: dict, question: str) -> dict:
    result = answer(question)
    with db.tx() as conn:
        ledger.append(conn, user["id"], "HR_QUESTION_ANSWERED", None, None,
                      {"question_sha256": result["question_sha256"], "abstained": result["abstained"],
                       "cited": result["citation"]["id"] if result["citation"] else None})
    result["method"] = "Answers quote the HR handbook (fictional demo company) and name the section. No AI model."
    return result


def sections() -> list[dict]:
    passages, _df, _avg = corpus()
    out: dict = {}
    for p in passages:
        out.setdefault(p["doc_title"], []).append(p["section"])
    return [{"title": k, "sections": v} for k, v in out.items()]
