"""CV intake and document security analysis.

Visibility is decided by what a human would see, not by what the parser reads:
each page is rendered with and without its text objects (pypdfium2), and glyphs
with too little rendered contrast, tiny fonts (< 4 pt), or off-page placement are
filtered individually. This catches low-contrast text and PDF text render mode 3,
which pdfplumber alone does not expose.

Only VISIBLE text is ever used for evidence or sent to an AI model.
"""
from __future__ import annotations

import io
import math
import re
import unicodedata
from collections import Counter

import numpy as np
import pdfplumber
import pypdfium2 as pdfium
from pypdfium2 import raw

from . import config, pii
from .errors import invalid

RENDER_SCALE = 2.0
MIN_CONTRAST_FRACTION = 0.005
TINY_PT = 4.0
OVERSIZED_PT = 36.0
MAX_PAGE_SIDE_PT = 2000
MAX_RENDERED_PIXELS = 40_000_000

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


def is_instruction_text(text: str) -> bool:
    return any(pattern.search(text) for pattern in _INSTR)


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
for _month, _number in list(MONTHS.items()):
    MONTHS[_month[:3]] = _number
MONTHS.update({"févr": 2, "avr": 4, "juil": 7, "sept": 9, "oct": 10, "nov": 11, "déc": 12})
_MONTH_TOKEN = "(?:" + "|".join(re.escape(m) + r"\.?" for m in sorted(MONTHS, key=len, reverse=True)) + ")"
_DATE_ENDPOINT = rf"(?:{_MONTH_TOKEN}\s+\d{{4}}|\d{{1,2}}/\d{{4}}|\d{{4}}|present|now|aujourd'hui)"
RANGE_RE = re.compile(
    rf"(?<![\w])({_DATE_ENDPOINT})\s*(?:to|à|au|jusqu['’]à|[-–—])\s*({_DATE_ENDPOINT})(?![\w])",
    re.IGNORECASE)


def _group_words(chars, page_w, page_h, difference, glyph_differences=None):
    """Chars -> words (with hidden flag + reason) -> lines."""
    H, W = difference.shape
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
            glyphs = []
            for c in w:
                reason = ""
                off = c["x1"] <= 0 or c["bottom"] <= 0 or c["x0"] >= page_w or c["top"] >= page_h
                if off:
                    reason = "off_page"
                elif c["size"] < TINY_PT:
                    reason = "tiny_font"
                else:
                    x0, x1 = int(c["x0"] * RENDER_SCALE), int(c["x1"] * RENDER_SCALE) + 1
                    y0, y1 = int(c["top"] * RENDER_SCALE), int(c["bottom"] * RENDER_SCALE) + 1
                    glyph_difference = (glyph_differences or {}).get(id(c), difference)
                    box = glyph_difference[max(0, y0):min(H, y1), max(0, x0):min(W, x1)]
                    contrast = float((box > 8).mean()) if box.size else 0.0
                    if contrast < MIN_CONTRAST_FRACTION:
                        reason = "no_contrast"
                if reason:
                    reasons[reason] += 1
                glyphs.append({"text": c["text"], "hidden": bool(reason), "reason": reason,
                               "x0": c["x0"], "top": c["top"], "x1": c["x1"], "bottom": c["bottom"]})
            hidden_glyphs = [g for g in glyphs if g["hidden"]]
            visible_glyphs = [g for g in glyphs if not g["hidden"]]
            visible_boxes = visible_glyphs or glyphs
            wlist.append({
                "text": _logical("".join(g["text"] for g in visible_glyphs)),
                "hidden_text": _logical("".join(g["text"] for g in hidden_glyphs)),
                "x0": round(min(c["x0"] for c in w), 1), "top": round(min(c["top"] for c in w), 1),
                "x1": round(max(c["x1"] for c in w), 1), "bottom": round(max(c["bottom"] for c in w), 1),
                "size": round(max(c["size"] for c in w), 1),
                "visible_boxes": [{"x0": min(g["x0"] for g in visible_boxes), "top": min(g["top"] for g in visible_boxes),
                                   "x1": max(g["x1"] for g in visible_boxes), "bottom": max(g["bottom"] for g in visible_boxes)}],
                "hidden_glyphs": hidden_glyphs,
                "hidden": not visible_glyphs, "reason": reasons.most_common(1)[0][0] if hidden_glyphs else "",
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
    rendered_pixels = 0
    try:
        if len(pdf.pages) > config.MAX_PAGES:
            raise invalid(f"PDF has more than {config.MAX_PAGES} pages.")
        metadata = {k: str(v)[:500] for k, v in (pdf.metadata or {}).items()}
        for i, page in enumerate(pdf.pages):
            page_w, page_h = float(page.width), float(page.height)
            if not math.isfinite(page_w) or not math.isfinite(page_h) or page_w <= 0 or page_h <= 0 or \
                    max(page_w, page_h) > MAX_PAGE_SIDE_PT:
                raise invalid("PDF page dimensions exceed the rendering limits.")
            pixels = math.ceil(page_w * RENDER_SCALE) * math.ceil(page_h * RENDER_SCALE)
            if rendered_pixels + pixels * 2 > MAX_RENDERED_PIXELS:
                raise invalid("PDF page dimensions exceed the rendering limits.")
            rendered_pixels += pixels * 2
            render_page = rdoc[i]
            img = np.asarray(render_page.render(scale=RENDER_SCALE, grayscale=True).to_pil())
            textpage = render_page.get_textpage()
            text_objects = list(render_page.get_objects(filter=(raw.FPDF_PAGEOBJ_TEXT,), textpage=textpage))
            matrices = [obj.get_matrix() for obj in text_objects]
            try:
                for obj, matrix in zip(text_objects, matrices):
                    obj.set_matrix(matrix.translate(MAX_PAGE_SIDE_PT * 4, MAX_PAGE_SIDE_PT * 4))
                without_text = np.asarray(render_page.render(scale=RENDER_SCALE, grayscale=True).to_pil())
            finally:
                for obj, matrix in zip(text_objects, matrices):
                    obj.set_matrix(matrix)
            difference = np.abs(img.astype(np.int16) - without_text.astype(np.int16))
            chars = page.chars
            glyph_differences = {}
            char_text = "".join(c["text"] for c in chars)
            char_cursor = 0
            object_spans = []
            object_bounds = []
            for obj in text_objects:
                text = obj.extract().strip()
                start = char_text.find(text, char_cursor)
                object_spans.append((start, len(text)))
                if start >= 0 and text:
                    char_cursor = start + len(text)
                x0, y0, x1, y1 = obj.get_bounds()
                object_bounds.append((x0, page_h - y1, x1, page_h - y0))
            overlapping = set()
            if not ARABIC_RE.search(char_text):
                for left in range(len(object_bounds)):
                    ax0, ay0, ax1, ay1 = object_bounds[left]
                    for right in range(left + 1, len(object_bounds)):
                        bx0, by0, bx1, by1 = object_bounds[right]
                        if min(ax1, bx1) > max(ax0, bx0) and min(ay1, by1) > max(ay0, by0):
                            overlapping.update((left, right))
            for object_index in overlapping:
                start, length = object_spans[object_index]
                if start < 0:
                    continue
                if rendered_pixels + pixels > MAX_RENDERED_PIXELS:
                    raise invalid("PDF page dimensions exceed the rendering limits.")
                rendered_pixels += pixels
                obj = text_objects[object_index]
                matrix = matrices[object_index]
                try:
                    obj.set_matrix(matrix.translate(MAX_PAGE_SIDE_PT * 4, MAX_PAGE_SIDE_PT * 4))
                    without_object = np.asarray(render_page.render(scale=RENDER_SCALE, grayscale=True).to_pil())
                finally:
                    obj.set_matrix(matrix)
                object_difference = np.abs(img.astype(np.int16) - without_object.astype(np.int16))
                for char in chars[start:start + length]:
                    glyph_differences[id(char)] = object_difference
            textpage.close()
            lines = _group_words(chars, page_w, page_h, difference, glyph_differences)
            pages_out.append({"number": i + 1, "width": page_w, "height": page_h, "lines": lines})
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
            vis = [{**w, **(w.get("visible_boxes") or [])[0]} if w.get("visible_boxes") else w
                   for w in line if w["text"]]
            if vis:
                yield p["number"], " ".join(w["text"] for w in vis), vis


def visible_text(analysis: dict) -> str:
    return "\n".join(t for _, t, _ in visible_lines(analysis))


def pii_boxes(analysis: dict) -> list[dict]:
    boxes = []
    for page in analysis["pages"]:
        for line in page["lines"]:
            visible = [word for word in line if word["text"]]
            text = " ".join(word["text"] for word in visible)
            if text and pii.redact(text) != text:
                glyph_boxes = [box for word in visible for box in word["visible_boxes"]]
                if glyph_boxes:
                    boxes.append({"page": page["number"], **_box(glyph_boxes)})
    return boxes


def hidden_text(analysis: dict) -> str:
    out = []
    for p in analysis["pages"]:
        for line in p["lines"]:
            hid = [w["hidden_text"] for w in line if w["hidden_text"]]
            if hid:
                out.append(" ".join(hid))
    return "\n".join(out)


def _box(words):
    return {"x0": min(w["x0"] for w in words), "top": min(w["top"] for w in words),
            "x1": max(w["x1"] for w in words), "bottom": max(w["bottom"] for w in words)}


def find_findings(analysis: dict) -> list[dict]:
    findings = []
    # Hidden text, one finding per line that contains hidden glyphs.
    for p in analysis["pages"]:
        for line in p["lines"]:
            hid = [g for w in line for g in w["hidden_glyphs"]]
            if not hid:
                continue
            reasons = Counter(g["reason"] for g in hid)
            label = {"no_contrast": "HIDDEN_TEXT", "tiny_font": "TINY_FONT", "off_page": "OFF_PAGE"}[reasons.most_common(1)[0][0]]
            findings.append({"type": label, "severity": "high", "page": p["number"],
                             "excerpt": "".join(g["text"] for g in hid)[:300], "boxes": [_box(hid)]})
        for line in p["lines"]:
            big = [w for w in line if w["size"] >= OVERSIZED_PT and not w["hidden"]]
            if big:
                findings.append({"type": "OVERSIZED_FONT", "severity": "medium", "page": p["number"],
                                 "excerpt": " ".join(w["text"] for w in big)[:200], "boxes": [_box(big)]})

    # Instruction-like phrases anywhere (visible or hidden): shown to the recruiter, never obeyed.
    for p in analysis["pages"]:
        for line in p["lines"]:
            text = " ".join(w["text"] for w in line)
            if is_instruction_text(text):
                findings.append({"type": "INSTRUCTION_PHRASE", "severity": "high", "page": p["number"],
                                 "excerpt": text[:300], "boxes": [_box(line)]})
    meta_text = " ".join(analysis.get("metadata", {}).values())
    if meta_text and is_instruction_text(meta_text):
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
    impossible = [r["text"] for r in ranges if r["invalid"]]
    if impossible:
        findings.append({"type": "DATE_RANGE_INVALID", "severity": "medium", "page": None,
                         "excerpt": "Impossible date ranges: " + ", ".join(impossible)[:250], "boxes": []})
    conflicts = []
    for i in range(len(ranges)):
        for j in range(i + 1, len(ranges)):
            a, b = ranges[i], ranges[j]
            if not a["invalid"] and not b["invalid"] and a["start"] < b["end"] and b["start"] < a["end"]:
                conflicts.append(f"{a['text']} overlaps {b['text']}")
    if conflicts:
        findings.append({"type": "DATE_CONFLICT", "severity": "medium", "page": None,
                         "excerpt": "; ".join(conflicts)[:300], "boxes": []})
    return findings


def date_ranges(text: str) -> list[dict]:
    def endpoint(value: str) -> int:
        normalized = value.casefold().strip().rstrip(".")
        if normalized in ("present", "now", "aujourd'hui"):
            return 9999 * 12 + 12
        month_match = re.fullmatch(r"([a-zéûôîàùç]+)\.?\s+(\d{4})", normalized, re.I)
        if month_match:
            month = MONTHS[month_match.group(1).rstrip(".")]
            return int(month_match.group(2)) * 12 + month
        numeric_match = re.fullmatch(r"(\d{1,2})/(\d{4})", normalized)
        if numeric_match:
            month, year = map(int, numeric_match.groups())
            return year * 12 + month if 1 <= month <= 12 else -1
        return int(normalized) * 12 + 1

    out = []
    for match in RANGE_RE.finditer(text):
        start, end = endpoint(match.group(1)), endpoint(match.group(2))
        out.append({"text": match.group(0), "start": start, "end": end,
                    "invalid": start < 0 or end < 0 or end < start})
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


def render_page_png(data: bytes, page_no: int, scale: float = 1.5, redact_boxes: list[dict] | None = None) -> bytes:
    doc = pdfium.PdfDocument(data)
    try:
        if page_no < 1 or page_no > len(doc):
            raise invalid("Page out of range.")
        img = doc[page_no - 1].render(scale=scale).to_pil()
        if redact_boxes:
            from PIL import ImageDraw
            draw = ImageDraw.Draw(img)
            for box in redact_boxes:
                if box["page"] == page_no:
                    draw.rectangle((box["x0"] * scale, box["top"] * scale,
                                    box["x1"] * scale, box["bottom"] * scale), fill="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    finally:
        doc.close()
