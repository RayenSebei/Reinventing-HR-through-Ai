"""F1: inbox digest and triage ("email summary").

Every inbound message is untrusted data. The pipeline: parse (.eml via the standard library), take the
plain-text part or strip HTML (hidden HTML is dropped and flagged), remove zero-width and bidi-control
characters, drop quoted reply chains, cap the size, then:
  - flag instruction-like lines (same rules as CVs), phishing language, look-alike sender domains,
    suspicious links (punycode, raw IPs, shorteners, look-alikes, text that differs from the target),
    attachments (never opened) and a Reply-To on another domain;
  - match the sender to a candidate only through a recruiter-confirmed address (D11);
  - sort into a category and an urgency with deterministic rules (no AI model needed);
  - summarise by extraction (first meaningful sentences), with personal data redacted.
Links are never fetched. Nothing is sent from here. The ledger stores IDs, hashes and finding types only.
"""
from __future__ import annotations

import email
import hashlib
import re
import unicodedata
from datetime import timezone
from email import policy as email_policy
from email.utils import parseaddr, parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urlparse

from . import config, db, documents, ledger, pii, reply_tracking
from .errors import ApiError, conflict, forbidden, invalid, not_found
from .security import is_member

MAX_TEXT = 20_000
_INVISIBLE = re.compile("[​-‏⁠-⁤﻿‪-‮⁦-⁩­]")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
_URL = re.compile(r"\b(?:https?://|www\.)[^\s<>\"')\]]+", re.IGNORECASE)
_QUOTE_START = re.compile(r"^(?:on .{3,200} wrote:|le .{3,200} a écrit\s?:|-{2,} ?original message ?-{2,}|from: .+@.+)$",
                          re.IGNORECASE)
_SHORTENERS = {"bit.ly", "t.co", "tinyurl.com", "goo.gl", "ow.ly", "is.gd", "buff.ly", "rebrand.ly", "cutt.ly"}
_PHISHING = re.compile(
    r"\b(?:password|mot de passe|verify your (?:account|identity)|confirm your (?:account|identity|login)|login details|"
    r"bank (?:details|account)|iban|wire transfer|gift ?cards?|crypto|bitcoin|urgent payment|suspended account|"
    r"click (?:here|the link) (?:to|and) (?:verify|confirm|log ?in|unlock))\b", re.IGNORECASE)

CATEGORIES = {
    "security_review": "Needs a security review",
    "withdrawal": "Withdrawals",
    "scheduling": "Interview scheduling",
    "documents": "Documents",
    "question": "Questions",
    "other": "Other",
}
_RULES = [
    ("withdrawal", re.compile(r"\b(?:withdraw\w*|no longer interested|accepted (?:another|an other) (?:offer|position)|"
                              r"retire[rz]? ma candidature|je me désiste|plus intéressée?)\b", re.IGNORECASE)),
    ("scheduling", re.compile(r"\b(?:availab\w*|reschedul\w*|slot|time slot|which time|what time|interview (?:time|date)|"
                              r"move the interview|another time|calendar|disponib\w*|créneau|reporter|décaler)\b", re.IGNORECASE)),
    ("documents", re.compile(r"\b(?:attached|attachment|portfolio|certificate|transcript|reference letter|"
                             r"pièce jointe|ci-joint|attestation)\b", re.IGNORECASE)),
    ("question", re.compile(r"\?|\b(?:which|what|how|when|could you tell|quel(?:le)?s?|comment|pourquoi)\b", re.IGNORECASE)),
]
_URGENT = re.compile(r"\b(?:urgent|asap|as soon as possible|today|tomorrow|tonight|aujourd'hui|demain|ce soir)\b",
                     re.IGNORECASE)


class _HtmlText(HTMLParser):
    """Visible text only. Text inside script/style or elements hidden by inline style is dropped and counted."""

    _HIDDEN = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0|opacity\s*:\s*0(?:\.0+)?\b|"
                         r"color\s*:\s*(?:#fff(?:fff)?|white)\b", re.IGNORECASE)
    _VOID = {"br", "img", "hr", "meta", "link", "input", "wbr", "area", "base", "col", "embed", "source", "track"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.stack: list[bool] = []      # True = this element hides its content
        self.hidden_chars = 0
        self.anchors: list[tuple[str, str]] = []
        self._href: str | None = None
        self._anchor_text: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        hides = tag in ("script", "style", "head", "title") or bool(self._HIDDEN.search(a.get("style") or "")) \
            or "hidden" in a
        if tag in ("br", "p", "div", "li", "tr"):
            self.parts.append("\n")
        if tag == "a":
            self._href, self._anchor_text = a.get("href") or "", []
        if tag not in self._VOID:
            self.stack.append(hides)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.anchors.append((self._href, "".join(self._anchor_text).strip()))
            self._href = None
        if tag not in self._VOID and self.stack:
            self.stack.pop()
        if tag in ("p", "div", "li", "tr"):
            self.parts.append("\n")

    def handle_data(self, data):
        if any(self.stack):
            self.hidden_chars += len(data.strip())
            return
        self.parts.append(data)
        if self._href is not None:
            self._anchor_text.append(data)


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _INVISIBLE.sub("", text)
    text = _CONTROL.sub(" ", text.replace("\r\n", "\n").replace("\r", "\n"))
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith(">") or _QUOTE_START.match(stripped):
            if _QUOTE_START.match(stripped):
                break           # everything below is the quoted earlier conversation
            continue
        lines.append(re.sub(r"[ \t]+", " ", stripped))
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return out[:MAX_TEXT]


def _one_line(value: str, limit: int = 200) -> str:
    return re.sub(r"\s+", " ", _CONTROL.sub(" ", _INVISIBLE.sub("", unicodedata.normalize("NFKC", value or "")))).strip()[:limit]


# --- look-alike detection ----------------------------------------------------------------------
_CONFUSE = str.maketrans({"0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "|": "l", "!": "i"})


def _skeleton(label: str) -> str:
    return label.lower().translate(_CONFUSE).replace("rn", "m").replace("vv", "w").replace("-", "").replace("_", "")


def _distance(a: str, b: str) -> int:
    """Edit distance where swapping two neighbouring letters counts as one edit (vouch -> vouhc)."""
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = a[i - 1] != b[j - 1]
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[len(a)][len(b)]


def trusted_domains() -> set[str]:
    return {r["email"].split("@", 1)[1].lower() for r in db.q("SELECT email FROM users") if "@" in r["email"]}


def looks_like(domain: str, trusted: set[str]) -> str | None:
    """Return the trusted domain this one imitates, or None. Exact matches are not look-alikes."""
    domain = domain.lower().strip(".")
    if not domain or domain in trusted:
        return None
    first = domain.split(".")[0]
    for t in trusted:
        t_first = t.split(".")[0]
        if domain.startswith("xn--") or ".xn--" in domain:
            return t
        if _skeleton(first) == _skeleton(t_first) or _skeleton(domain) == _skeleton(t):
            return t
        if len(t_first) >= 4 and _distance(first, t_first) <= (1 if len(t_first) < 7 else 2):
            return t
        if len(t_first) >= 4 and t_first in first and first != t_first:
            return t
    return None


def _link_findings(url: str, shown: str | None, trusted: set[str]) -> dict:
    target = url if "://" in url else "http://" + url
    host = (urlparse(target).hostname or "").lower()
    reasons = []
    if host.startswith("xn--") or ".xn--" in host:
        reasons.append("punycode domain (can imitate another name)")
    if re.fullmatch(r"[\d.]+|\[[0-9a-f:]+\]", host):
        reasons.append("raw IP address instead of a name")
    if host in _SHORTENERS:
        reasons.append("link shortener hides the destination")
    imitated = looks_like(host, trusted)
    if imitated:
        reasons.append(f"looks like {imitated}")
    if shown and _URL.search(shown):
        shown_host = (urlparse(shown if "://" in shown else "http://" + shown).hostname or "").lower()
        if shown_host and shown_host != host:
            reasons.append(f"the text shows {shown_host} but the link goes to {host}")
    if urlparse(target).scheme not in ("http", "https"):
        reasons.append("not a web link")
    return {"host": host, "verdict": "suspicious" if reasons else "unverified", "reasons": reasons}


# --- parsing --------------------------------------------------------------------------------------
def parse_eml(raw: bytes) -> dict:
    try:
        msg = email.message_from_bytes(raw, policy=email_policy.default)
    except Exception:  # noqa: BLE001 - malformed mail is refused, not crashed on
        raise invalid("This file is not a readable email (.eml).")
    name, addr = parseaddr(str(msg.get("From", "")))
    _rn, reply_to = parseaddr(str(msg.get("Reply-To", "")))
    try:
        received = parsedate_to_datetime(str(msg.get("Date"))) if msg.get("Date") else None
    except (TypeError, ValueError):
        received = None
    plain, html, attachments = None, None, []
    for part in msg.walk():
        if part.is_multipart():
            continue
        filename = part.get_filename()
        if filename or part.get_content_disposition() == "attachment":
            attachments.append(_one_line(filename or "unnamed", 120))
            continue
        ctype = part.get_content_type()
        try:
            content = part.get_content()
        except Exception:  # noqa: BLE001
            continue
        if ctype == "text/plain" and plain is None:
            plain = content
        elif ctype == "text/html" and html is None:
            html = content
    return {"sender_name": name, "sender_email": addr, "reply_to": reply_to, "subject": str(msg.get("Subject", "")),
            "received_at": received, "plain": plain, "html": html, "attachments": attachments}


def analyse(sender_email: str, subject: str, plain: str | None, html: str | None,
            reply_to: str = "", attachments: list[str] | None = None) -> dict:
    """Pure analysis (no database writes). Returns safe text, findings, links, category, urgency, summary."""
    findings: list[dict] = []
    anchors: list[tuple[str, str]] = []
    if plain:
        text = clean_text(plain)
    elif html:
        parser = _HtmlText()
        parser.feed(html)
        parser.close()
        text = clean_text("".join(parser.parts))
        anchors = parser.anchors
        if parser.hidden_chars > 20:
            findings.append({"type": "HIDDEN_HTML_TEXT", "severity": "high",
                             "detail": f"{parser.hidden_chars} characters hidden from the reader were removed."})
    else:
        text = ""
    trusted = trusted_domains()
    sender_domain = sender_email.split("@", 1)[1].lower() if "@" in sender_email else ""
    imitated = looks_like(sender_domain, trusted)
    if imitated:
        findings.append({"type": "SENDER_LOOKALIKE", "severity": "high",
                         "detail": f"The sender's domain imitates {imitated}."})
    if reply_to and "@" in reply_to and reply_to.split("@", 1)[1].lower() != sender_domain:
        findings.append({"type": "REPLY_TO_MISMATCH", "severity": "medium",
                         "detail": "Replies would go to a different domain than the sender's."})
    instruction_lines = [ln for ln in text.split("\n") if ln and documents.is_instruction_text(ln)]
    if instruction_lines or documents.is_instruction_text(subject):
        findings.append({"type": "INSTRUCTION_TEXT", "severity": "high",
                         "detail": "The message contains instructions aimed at an AI or the system. They were not followed."})
    if _PHISHING.search(text) or _PHISHING.search(subject):
        findings.append({"type": "PHISHING_LANGUAGE", "severity": "high",
                         "detail": "Asks for credentials, payment or account verification."})
    for att in attachments or []:
        findings.append({"type": "ATTACHMENT_NOT_OPENED", "severity": "low",
                         "detail": f"Attachment '{att}' was not opened. Ask the candidate to upload documents instead."})
    links = []
    seen = set()
    for href, shown in anchors:
        if href and href not in seen:
            seen.add(href)
            links.append({"url": href[:300], **_link_findings(href, shown, trusted)})
    for m in _URL.finditer(text):
        url = m.group(0).rstrip(".,;:")
        if url not in seen:
            seen.add(url)
            links.append({"url": url[:300], **_link_findings(url, None, trusted)})
    if any(link["verdict"] == "suspicious" for link in links):
        findings.append({"type": "SUSPICIOUS_LINK", "severity": "high",
                         "detail": "At least one link is disguised or imitates a known domain. Links are never opened."})
    reading = "\n".join(ln for ln in text.split("\n") if ln not in instruction_lines)
    blob = f"{subject}\n{reading}"
    category = "other"
    if any(f["severity"] == "high" for f in findings):
        category = "security_review"
    else:
        for name, rx in _RULES:
            if rx.search(blob):
                category = name
                break
    urgency = "high" if category in ("security_review", "withdrawal") or _URGENT.search(blob) else "normal"
    return {"safe_text": text, "findings": findings, "links": links, "category": category, "urgency": urgency,
            "summary": summarise(reading)}


def summarise(text: str, limit: int = 220) -> str:
    """Extractive: the first meaningful sentences, personal data redacted, never invented."""
    body = " ".join(ln for ln in text.split("\n") if ln and not re.match(
        r"^(?:hi|hello|dear|bonjour|salut|thanks|thank you|regards|best|cordialement|merci)\b[ ,!.]*\w{0,20}[,!.]?$",
        ln, re.IGNORECASE))
    sentences = re.split(r"(?<=[.!?])\s+", body.strip())
    out = ""
    for s in sentences:
        if not s:
            continue
        if out and len(out) + len(s) + 1 > limit:
            break
        out = f"{out} {s}".strip()
    out = pii.redact(out or "(no readable text)")
    return out if len(out) <= limit else out[: limit - 1].rstrip() + "…"


# --- storage and access -----------------------------------------------------------------------------
def _match(conn, sender_email: str):
    return conn.execute(
        "SELECT c.id AS candidate_id, c.case_id FROM contact_confirmations k JOIN candidates c ON c.id=k.candidate_id "
        "WHERE lower(k.email)=? ORDER BY k.confirmed_at DESC LIMIT 1", (sender_email.lower(),)).fetchone()


def ingest(user: dict, *, sender_email: str, sender_name: str, subject: str, plain: str | None, html: str | None,
           raw_sha256: str, received_at: str | None, source: str, reply_to: str = "",
           attachments: list[str] | None = None) -> dict:
    if user["role"] not in ("recruiter", "hr_admin"):
        raise forbidden("FORBIDDEN_ROLE", "Only recruiters and HR admins can add messages to the inbox.")
    sender_email = _one_line(sender_email, 254)
    if not re.fullmatch(r"[^@\s]{1,64}@[^@\s]{1,253}", sender_email):
        raise invalid("The message has no readable sender address.")
    a = analyse(sender_email, _one_line(subject), plain, html, reply_to, attachments)
    mid = db.new_id("MSG")
    received = received_at or db.now()
    with db.tx() as conn:
        if conn.execute("SELECT 1 FROM inbound_messages WHERE raw_sha256=?", (raw_sha256,)).fetchone():
            raise conflict("DUPLICATE_MESSAGE", "This message is already in the inbox.")
        m = _match(conn, sender_email)
        case_id = m["case_id"] if m else None
        candidate_id = m["candidate_id"] if m else None
        if case_id and user["role"] == "recruiter" and not is_member(user, case_id):
            case_id = candidate_id = None          # do not attach it to a case the uploader cannot see
        conn.execute(
            "INSERT INTO inbound_messages(id,case_id,candidate_id,sender_email,sender_name,subject,safe_text,raw_sha256,"
            "received_at,category,urgency,summary,findings_json,links_json,status,source,created_by,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,'new',?,?,?)",
            (mid, case_id, candidate_id, sender_email.lower(), _one_line(sender_name, 120), _one_line(subject),
             a["safe_text"], raw_sha256, received, a["category"], a["urgency"], a["summary"],
             db.dumps(a["findings"]), db.dumps(a["links"]), source, user["id"], db.now()))
        ledger.append(conn, user["id"], "MESSAGE_RECEIVED", case_id, mid,
                      {"sha256": raw_sha256, "category": a["category"], "urgency": a["urgency"],
                       "finding_types": sorted({f["type"] for f in a["findings"]}), "matched": bool(candidate_id)})
        if candidate_id:
            reply_tracking.match_inbound(conn, user, candidate_id, received, mid)
    return get(user, mid)


def ingest_eml(user: dict, raw: bytes) -> dict:
    if len(raw) > config.MAX_EML_BYTES:
        raise ApiError(413, "MESSAGE_TOO_LARGE", f"Email files are limited to {config.MAX_EML_BYTES // 1024} KB.")
    p = parse_eml(raw)
    received = None
    if p["received_at"] is not None:
        when = p["received_at"]
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        received = when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if received > db.now():
            received = db.now()                    # a date in the future is not trusted
    return ingest(user, sender_email=p["sender_email"], sender_name=p["sender_name"], subject=p["subject"],
                  plain=p["plain"], html=p["html"], raw_sha256=hashlib.sha256(raw).hexdigest(),
                  received_at=received, source="eml", reply_to=p["reply_to"], attachments=p["attachments"])


def _can_see(user: dict, row) -> bool:
    if user["role"] in ("hr_admin",):
        return True
    if user["role"] != "recruiter":
        return False
    return row["case_id"] is None or is_member(user, row["case_id"])


def _row(mid: str):
    r = db.one("SELECT * FROM inbound_messages WHERE id=?", (mid,))
    if not r:
        raise not_found("Message")
    return r


def _out(user: dict, r, full: bool = False) -> dict:
    cand = db.one("SELECT pseudonym FROM candidates WHERE id=?", (r["candidate_id"],)) if r["candidate_id"] else None
    case = db.one("SELECT title FROM cases WHERE id=?", (r["case_id"],)) if r["case_id"] else None
    findings = db.loads(r["findings_json"], [])
    item = {"id": r["id"], "sender_name": r["sender_name"], "sender_email": r["sender_email"], "subject": r["subject"],
            "received_at": r["received_at"], "category": r["category"], "category_label": CATEGORIES[r["category"]],
            "urgency": r["urgency"], "summary": r["summary"], "findings": findings,
            "links": db.loads(r["links_json"], []), "status": r["status"], "source": r["source"],
            "candidate": {"id": r["candidate_id"], "pseudonym": cand["pseudonym"]} if cand else None,
            "case": {"id": r["case_id"], "title": case["title"]} if case else None,
            "reply_proposal_id": r["reply_proposal_id"], "suggested_action": _suggest(r, findings)}
    if full:
        item["safe_text"] = r["safe_text"]
    return item


def _suggest(r, findings) -> str:
    if r["category"] == "security_review":
        return "Do not reply or open links. Review the flags; report the message if it is phishing."
    if not r["candidate_id"]:
        return "Sender is not a confirmed candidate address. Check who it is before answering."
    if r["reply_proposal_id"]:
        return "A reply draft exists. It is sent only after the hiring manager approves it."
    return {"scheduling": "Draft a reply with the interview time and free slots from the calendar.",
            "withdrawal": "Draft an acknowledgement. Recording the withdrawal stays a human decision.",
            "documents": "Draft an acknowledgement; ask for uploads instead of attachments.",
            "question": "Draft a holding reply; a recruiter answers the question in person."}.get(
        r["category"], "Draft an acknowledgement or mark as handled.")


def digest(user: dict, params) -> dict:
    extra = set(params) - {"status"}
    if extra:
        raise invalid(f"Unknown query parameter(s): {', '.join(sorted(extra))}.")
    status = params.get("status", "new")
    if status not in ("new", "handled", "all"):
        raise invalid("status must be new, handled or all.")
    if user["role"] not in ("recruiter", "hr_admin"):
        raise forbidden("FORBIDDEN_ROLE", "The inbox is for recruiters and HR admins.")
    rows = [r for r in db.q("SELECT * FROM inbound_messages ORDER BY received_at DESC") if _can_see(user, r)]
    if status != "all":
        rows = [r for r in rows if r["status"] == status]
    order = list(CATEGORIES)
    groups = []
    for cat in order:
        items = [_out(user, r) for r in rows if r["category"] == cat]
        items.sort(key=lambda i: (i["urgency"] != "high", i["received_at"]), reverse=False)
        if items:
            groups.append({"category": cat, "label": CATEGORIES[cat], "count": len(items),
                           "urgent": sum(1 for i in items if i["urgency"] == "high"), "items": items})
    total = len(rows)
    return {"generated_at": db.now(), "status": status, "groups": groups,
            "totals": {"messages": total, "urgent": sum(1 for r in rows if r["urgency"] == "high"),
                       "flagged": sum(1 for r in rows if db.loads(r["findings_json"], [])),
                       "matched": sum(1 for r in rows if r["candidate_id"])},
            "method": "Rules-based triage and extractive summaries (no AI model). Links are never opened."}


def get(user: dict, mid: str) -> dict:
    r = _row(mid)
    if not _can_see(user, r):
        raise not_found("Message")
    return _out(user, r, full=True)


def set_status(user: dict, mid: str, status: str) -> dict:
    r = _row(mid)
    if not _can_see(user, r):
        raise not_found("Message")
    if status not in ("new", "handled"):
        raise invalid("status must be new or handled.")
    with db.tx() as conn:
        conn.execute("UPDATE inbound_messages SET status=? WHERE id=?", (status, mid))
        ledger.append(conn, user["id"], "MESSAGE_STATUS", r["case_id"], mid, {"status": status})
    return get(user, mid)

