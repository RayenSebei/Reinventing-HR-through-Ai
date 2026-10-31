"""Remove personal data before text reaches an AI model or a dossier quote.

Regex rules for formats seen in EN / FR / AR CVs. Not perfect; it reduces what an
external model can see. Originals stay on the Vouch host.
"""
from __future__ import annotations

import re

RULES = [
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[EMAIL]"),
    (re.compile(r"https?://\S+|www\.\S+"), "[URL]"),
    (re.compile(r"(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,4}\d{2,4}"), lambda m: "[PHONE]" if sum(c.isdigit() for c in m.group(0)) >= 8 else m.group(0)),
    (re.compile(r"\b(?:born|né|née|date of birth|date de naissance|DOB)\b[^\n]{0,40}", re.I), "[BIRTH DATE]"),
    (re.compile(r"\b(?:address|adresse|العنوان)\s*[:：][^\n]*", re.I), "[ADDRESS]"),
    (re.compile(r"\b(?:name|nom|الاسم)\s*[:：][^\n]*", re.I), "[NAME]"),
    (re.compile(r"\b(?:gender|sexe|genre|nationality|nationalité|age|âge|marital status|état civil|religion)\s*[:：][^\n]*", re.I), "[PERSONAL]"),
    (re.compile(r"\b(?:phone|tel|tél|téléphone|mobile)\s*[:：][^\n]*", re.I), "[PHONE]"),
]


def redact(text: str) -> str:
    for rx, repl in RULES:
        text = rx.sub(repl, text)
    return text
