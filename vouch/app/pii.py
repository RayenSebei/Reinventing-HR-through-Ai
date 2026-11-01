"""Remove personal data before text reaches an AI model or a dossier quote.

Regex rules for formats seen in EN / FR / AR CVs. Not perfect; it reduces what an
external model can see. Originals stay on the Vouch host.
"""
from __future__ import annotations

import re

_PHONE_LABEL = re.compile(r"(?im)^\s*(?:phone|tel|tél|téléphone|mobile)\s*[:：]?[^\n]*")
_PLUS_PHONE = re.compile(r"\+\d(?:[\d\s().-]*\d)")
_BARE_PHONE = re.compile(r"(?<![\d/.-])\d{8,15}(?![\d/.-])")

RULES = [
    (_PHONE_LABEL, "[PHONE]"),
    (_PLUS_PHONE, lambda m: "[PHONE]" if 8 <= sum(c.isdigit() for c in m.group(0)) <= 15 else m.group(0)),
    (_BARE_PHONE, "[PHONE]"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[EMAIL]"),
    (re.compile(r"https?://\S+|www\.\S+"), "[URL]"),
    (re.compile(r"(?im)^\s*(?:born|né|née|date of birth|date de naissance|DOB)\b[^\n]{0,40}"), "[BIRTH DATE]"),
    (re.compile(r"(?im)^\s*(?:address|adresse|العنوان)\s*[:：][^\n]*"), "[ADDRESS]"),
    (re.compile(r"(?im)^\s*(?:name|nom|الاسم)\s*[:：][^\n]*"), "[NAME]"),
    (re.compile(r"(?im)^\s*(?:gender|sexe|genre|nationality|nationalité|age|âge|marital status|état civil|religion)\s*[:：][^\n]*"), "[PERSONAL]"),
]


def redact(text: str) -> str:
    for rx, repl in RULES:
        text = rx.sub(repl, text)
    return text
