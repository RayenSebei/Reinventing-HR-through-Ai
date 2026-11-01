"""Text helpers: normalisation, verified quotes, PII masking, keyword matching."""
import re
import unicodedata

_QUOTES = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "«": '"', "»": '"',
                         "–": "-", "—": "-", " ": " "})
ZERO_WIDTH = re.compile("[​‌‍⁠﻿­‪-‮⁦-⁩]")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").translate(_QUOTES)
    text = ZERO_WIDTH.sub("", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def quote_found(source: str, quote: str, min_len: int = 6) -> bool:
    """A quote counts as evidence only if it appears verbatim (after whitespace/case normalisation)."""
    q = normalize(quote).strip(" .,;:\"'")
    return len(q) >= min_len and q in normalize(source)


# ---------------------------------------------------------------- PII minimisation
# Regex masking is a baseline. For production, add Microsoft Presidio with
# custom recognisers for French/Arabic (see README).

_PII_PATTERNS = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("URL", re.compile(r"(?:https?://|www\.)\S+|(?:linkedin|github)\.com/\S+", re.I)),
    ("PHONE", re.compile(r"(?:\+|00)\d{1,3}[\s.-]?\d{2}[\s.-]?\d{3}[\s.-]?\d{3}|\b\d{2}[\s.-]\d{3}[\s.-]\d{3}\b|\b\d{8,}\b")),
    ("DATE_OF_BIRTH", re.compile(
        r"(?:date\s+(?:of|de)\s+naissance|date of birth|born(?: on)?|n[ée]e?\s+le|DOB|تاريخ الولادة|تاريخ الميلاد)\s*[:\-]?\s*(?:\d{1,4}[/.\-]\d{1,2}[/.\-]\d{1,4}|\d{1,2}\s+\w+\s+\d{4})", re.I)),
    ("AGE", re.compile(r"(?:\bage\s*[:\-]\s*\d{2}\b|\b\d{2}\s*(?:ans|years old)\b|العمر\s*[:\-]?\s*\d{2})", re.I)),
    ("GENDER", re.compile(r"(?:gender|sexe|genre|الجنس)\s*[:\-]\s*\S+", re.I)),
    ("MARITAL", re.compile(r"(?:marital status|situation familiale|[ée]tat civil|الحالة المدنية)\s*[:\-]\s*[^\n|;,]{1,30}", re.I)),
    ("NATIONALITY", re.compile(r"(?:nationality|nationalit[ée]|الجنسية)\s*[:\-]\s*[^\n|;,]{1,30}", re.I)),
    ("ADDRESS", re.compile(r"(?:address|adresse|العنوان)\s*[:\-]\s*[^\n|]{1,80}", re.I)),
]


def mask_pii(text: str, names: list[str] | None = None) -> tuple[str, dict]:
    """Return (masked text, counts per type). Names are masked word by word."""
    counts: dict[str, int] = {}
    for label, pattern in _PII_PATTERNS:
        text, n = pattern.subn(f"[{label}]", text)
        if n:
            counts[label] = counts.get(label, 0) + n
    for name in names or []:
        for part in {p for p in re.split(r"\s+", name) if len(p) >= 3}:
            text, n = re.subn(rf"(?<!\w){re.escape(part)}(?!\w)", "[NAME]", text, flags=re.I)
            if n:
                counts["NAME"] = counts.get("NAME", 0) + n
    # "[NAME] [NAME] [NAME]" would still reveal how long the name is: collapse to one token.
    text = re.sub(r"\[NAME\](?:[\s-]+\[NAME\])+", "[NAME]", text)
    return text, counts


# ---------------------------------------------------------------- keyword matching

def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?؟])\s+|\n+|\s*[•·▪●|]\s*", text or "")
    return [p.strip(" -\t") for p in parts if len(p.strip()) >= 4]


def keyword_hit(sentence: str, keyword: str) -> bool:
    s, k = normalize(sentence), normalize(keyword)
    if not k:
        return False
    if re.fullmatch(r"[\w .+#/-]+", k, re.A):          # latin keyword: whole-word match
        return re.search(rf"(?<![\w]){re.escape(k)}(?![\w])", s) is not None
    return k in s                                       # arabic or other scripts: substring
