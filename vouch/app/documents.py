"""CV intake and document security analysis.

Visibility is decided by what a human would see, not by what the parser reads:
each page is rendered (pypdfium2) and a word counts as hidden when its box has
almost no ink, its font is tiny (< 4 pt) or it sits outside the page. This catches
white-on-white text, tiny text and PDF text render mode 3 (invisible text), which
pdfplumber alone does not expose.

Only VISIBLE text is ever used for evidence or sent to an AI model.
"""
from __future__ import annotations

import io
import re
import unicodedata
from collections import Counter

import numpy as np
import pdfplumber
import pypdfium2 as pdfium

from . import config
from .errors import invalid

RENDER_SCALE = 2.0
INK_THRESHOLD = 200       # grey level below which a pixel counts as ink
MIN_INK_FRACTION = 0.02   # share of ink pixels a visible glyph box needs
TINY_PT = 4.0
OVERSIZED_PT = 36.0

INSTRUCTION_PATTERNS = [
    r"\bignore\s+(?:all\s+|the\s+|any\s+)?(?:prior\s+|previous\s+|above\s+|earlier\s+)?(?:rules|instructions|requirements|criteria|guidelines)\b",
    r"\bsystem\s+override\b",
    r"\b(?:mark|rank|rate)\s+(?:this|me|the)\s+(?:candidate\s+)?(?:as\s+)?(?:the\s+)?(?:top|first|best|highest)",
    r"\bsubmit\s+an?\s+interview\s+proposal\b",
    r"\bdo\s+not\s+disclose\b",
    r"\b(?:reveal|include|print|show)\s+the\s+(?:hidden\s+)?system\s+prompt\b",
    r"\bclaim\s+(?:\w+\s+)?years?\s+of\s+experience\b",
    r"\bai\s+reviewer\s*:",
    r"\bnever\s+mention\b",
    r"\bmark\s+all\s+\w+\s+as\s+verified\b",
    r"\bapproval\s+token\b",
    r"\bignore[rz]?\s+(?:les\s+|toutes\s+les\s+)?(?:instructions|règles|consignes|critères)\b",
    r"\bclasse[rz]?\s+ce\s+candidat\b",
    r"تجاهل\s+(?:جميع\s+)?(?:التعليمات|القواعد|المعايير)",
]
_INSTR = [re.compile(p, re.IGNORECASE) for p in INSTRUCTION_PATTERNS]

_MIRROR = str.maketrans("()[]{}<>", ")(][}{><")
ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")


def _logical(text: str) -> str:
    """PDF readers return Arabic in visual order and in presentation forms.
    NFKC maps presentation forms back to normal letters; reversing restores reading order."""
    if ARABIC_RE.search(text):
        text = text[::-1].translate(_MIRROR)      # reverse glyphs first, then expand ligatures
    return unicodedata.normalize("NFKC", text)


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,4}\d{2,4}")
MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"])}
MONTHS.update({m: i + 1 for i, m in enumerate(
    ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
     "septembre", "octobre", "novembre", "décembre"])})
RANGE_RE = re.compile(
    r"(" + "|".join(MONTHS) + r")\s+(\d{4})\s*(?:to|-|–|—|à|au|jusqu'à)\s*(" + "|".join(MONTHS) + r"|present|now|aujourd'hui)\s*(\d{4})?",
    re.IGNORECASE)


def _group_words(chars, page_w, page_h, img):
    """Chars -> words (with hidden flag + reason) -> lines."""
    H, W = img.shape
    usable = [c for c in chars if c.get("text")]
    usable.sort(key=lambda c: (round(c["top"] / 3), c["x0"]))
    lines, cur, last = [], [], None
    for c in usable:
        if last is not None and abs(c["top"] - last["top"]) > max(2.0, 0.5 * min(c["size"], last["size"])):
            lines.append(cur)
            cur = []
        cur.append(c)
        last = c
    if cur:
        lines.append(cur)

    out_lines = []
    for chars_in_line in lines:
        words, word = [], []
        prev = None
        for c in chars_in_line:
            gap = (c["x0"] - prev["x1"]) if prev else 0
            if c["text"].isspace() or (prev and gap > 0.25 * c["size"]):
                if word:
                    words.append(word)
                word = []
            if not c["text"].isspace():
                word.append(c)
            prev = c
        if word:
            words.append(word)

        wlist = []
        for w in words:
            reasons = Counter()
            for c in w:
                off = c["x1"] <= 0 or c["bottom"] <= 0 or c["x0"] >= page_w or c["top"] >= page_h
                if off:
                    reasons["off_page"] += 1
                    continue
                if c["size"] < TINY_PT:
                    reasons["tiny_font"] += 1
                    continue
                x0, x1 = int(c["x0"] * RENDER_SCALE), int(c["x1"] * RENDER_SCALE) + 1
                y0, y1 = int(c["top"] * RENDER_SCALE), int(c["bottom"] * RENDER_SCALE) + 1
                box = img[max(0, y0):min(H, y1), max(0, x0):min(W, x1)]
                ink = float((box < INK_THRESHOLD).mean()) if box.size else 0.0
                if ink < MIN_INK_FRACTION:
                    reasons["no_ink"] += 1
            n = len(w)
            hidden_count = sum(reasons.values())
            hidden = hidden_count * 2 > n  # majority of the word's glyphs
            wlist.append({
                "text": _logical("".join(c["text"] for c in w)),
                "x0": round(min(c["x0"] for c in w), 1), "top": round(min(c["top"] for c in w), 1),
                "x1": round(max(c["x1"] for c in w), 1), "bottom": round(max(c["bottom"] for c in w), 1),
                "size": round(max(c["size"] for c in w), 1),
                "hidden": hidden, "reason": reasons.most_common(1)[0][0] if hidden else "",
            })
        # Right-to-left line: words were collected left to right, so reverse them.
        arabic_words = sum(1 for x in wlist if ARABIC_RE.search(x["text"]))
        if wlist and arabic_words * 2 >= len(wlist):
            wlist = wlist[::-1]
        out_lines.append(wlist)
    return out_lines


def analyse_pdf(data: bytes) -> dict:
    if not data.startswith(b"%PDF"):
        raise invalid("Only PDF files are accepted.")
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise invalid(f"File is larger than {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    try:
        pdf = pdfplumber.open(io.BytesIO(data))
        rdoc = pdfium.PdfDocument(data)
    except Exception:
        raise invalid("This PDF could not be read.")
    pages_out = []
    metadata = {}
    try:
        if len(pdf.pages) > config.MAX_PAGES:
            raise invalid(f"PDF has more than {config.MAX_PAGES} pages.")
        metadata = {k: str(v)[:500] for k, v in (pdf.metadata or {}).items()}
        for i, page in enumerate(pdf.pages):
            img = np.asarray(rdoc[i].render(scale=RENDER_SCALE, grayscale=True).to_pil())
            lines = _group_words(page.chars, float(page.width), float(page.height), img)
            pages_out.append({"number": i + 1, "width": float(page.width), "height": float(page.height), "lines": lines})
    finally:
        pdf.close()
        rdoc.close()
    return {"pages": pages_out, "metadata": metadata}


def visible_lines(analysis: dict, page_no: int | None = None):
    """Yield (page, line_text, word_boxes) for visible words only."""
    for p in analysis["pages"]:
        if page_no and p["number"] != page_no:
            continue
        for line in p["lines"]:
            vis = [w for w in line if not w["hidden"]]
            if vis:
                yield p["number"], " ".join(w["text"] for w in vis), vis


def visible_text(analysis: dict) -> str:
    return "\n".join(t for _, t, _ in visible_lines(analysis))


def hidden_text(analysis: dict) -> str:
    out = []
    for p in analysis["pages"]:
        for line in p["lines"]:
            hid = [w["text"] for w in line if w["hidden"]]
            if hid:
                out.append(" ".join(hid))
    return "\n".join(out)


def _box(words):
    return {"x0": min(w["x0"] for w in words), "top": min(w["top"] for w in words),
            "x1": max(w["x1"] for w in words), "bottom": max(w["bottom"] for w in words)}


def find_findings(analysis: dict) -> list[dict]:
    findings = []
    # Hidden text, one finding per line that contains hidden words.
    for p in analysis["pages"]:
        for line in p["lines"]:
            hid = [w for w in line if w["hidden"]]
            if not hid:
                continue
            reasons = Counter(w["reason"] for w in hid)
            label = {"no_ink": "HIDDEN_TEXT", "tiny_font": "TINY_FONT", "off_page": "OFF_PAGE"}[reasons.most_common(1)[0][0]]
            findings.append({"type": label, "severity": "high", "page": p["number"],
                             "excerpt": " ".join(w["text"] for w in hid)[:300], "boxes": [_box(hid)]})
        for line in p["lines"]:
            big = [w for w in line if w["size"] >= OVERSIZED_PT and not w["hidden"]]
            if big:
                findings.append({"type": "OVERSIZED_FONT", "severity": "medium", "page": p["number"],
                                 "excerpt": " ".join(w["text"] for w in big)[:200], "boxes": [_box(big)]})

    # Instruction-like phrases anywhere (visible or hidden): shown to the recruiter, never obeyed.
    for p in analysis["pages"]:
        for line in p["lines"]:
            text = " ".join(w["text"] for w in line)
            if any(r.search(text) for r in _INSTR):
                findings.append({"type": "INSTRUCTION_PHRASE", "severity": "high", "page": p["number"],
                                 "excerpt": text[:300], "boxes": [_box(line)]})
    meta_text = " ".join(analysis.get("metadata", {}).values())
    if meta_text and any(r.search(meta_text) for r in _INSTR):
        findings.append({"type": "METADATA_INSTRUCTION", "severity": "high", "page": None,
                         "excerpt": meta_text[:300], "boxes": []})

    # Keyword stuffing: one token repeated a lot.
    tokens = [t.lower() for t in re.findall(r"[\w+#.-]{2,}", visible_text(analysis))]
    if tokens:
        counts = Counter(t for t in tokens if len(t) > 2)
        stuffed = [(tok, n) for tok, n in counts.most_common(10) if n >= 5 and n / len(tokens) > 0.06]
        if stuffed:
            findings.append({"type": "KEYWORD_DENSITY", "severity": "low", "page": None,
                             "excerpt": "Repeated keywords: " + ", ".join(f"'{t}' x{n}" for t, n in stuffed)
                                        + f" (in {len(tokens)} words)",
                             "boxes": [], "tokens": [t for t, _ in stuffed]})

    # Date ranges that overlap or contradict each other.
    ranges = date_ranges(visible_text(analysis))
    conflicts = []
    for i in range(len(ranges)):
        for j in range(i + 1, len(ranges)):
            a, b = ranges[i], ranges[j]
            if a["start"] <= b["end"] and b["start"] <= a["end"]:
                conflicts.append(f"{a['text']} overlaps {b['text']}")
    if conflicts:
        findings.append({"type": "DATE_CONFLICT", "severity": "medium", "page": None,
                         "excerpt": "; ".join(conflicts)[:300], "boxes": []})
    return findings


def date_ranges(text: str) -> list[dict]:
    out = []
    for m in RANGE_RE.finditer(text):
        m1, y1, m2, y2 = m.group(1).lower(), int(m.group(2)), m.group(3).lower(), m.group(4)
        start = y1 * 12 + MONTHS[m1]
        if m2 in MONTHS:
            end = (int(y2) if y2 else y1) * 12 + MONTHS[m2]
        else:
            end = 9999 * 12
        out.append({"text": m.group(0), "start": start, "end": end})
    return out


def contacts(text: str) -> dict:
    emails = EMAIL_RE.findall(text)
    phones = [p.strip() for p in PHONE_RE.findall(text) if sum(ch.isdigit() for ch in p) >= 8]
    return {"emails": emails, "phones": phones}


def guess_name(text: str) -> str:
    for line in text.splitlines()[:8]:
        m = re.match(r"\s*(?:name|nom|الاسم)\s*[:：]\s*(.+)", line, re.IGNORECASE)
        if m:
            return m.group(1).strip()[:80]
    return ""


def render_page_png(data: bytes, page_no: int, scale: float = 1.5) -> bytes:
    doc = pdfium.PdfDocument(data)
    try:
        if page_no < 1 or page_no > len(doc):
            raise invalid("Page out of range.")
        img = doc[page_no - 1].render(scale=scale).to_pil()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    finally:
        doc.close()
