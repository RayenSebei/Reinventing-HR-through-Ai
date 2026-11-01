"""F2: grounded reply drafts for inbox messages.

A draft is built only from facts Vouch holds: the role title, the candidate's next interview, free slots
from the calendar (F4) and fixed, reviewed wording. The candidate's own text is never copied into the
reply (so an attacker cannot make Vouch relay a link or an instruction), and the original subject is not
echoed. Sensitive topics (pay, the hiring decision, other candidates, health, discrimination, legal) get a
neutral holding reply and are flagged for a person. A code check then verifies that every date, time,
number, address or link in the draft comes from the allowed facts; otherwise the draft is refused.
The draft becomes a normal proposal (kind "reply"): the hiring manager approves the exact text before
anything is sent.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import db, gateway, schemas, slots
from .errors import ApiError, conflict, not_found
from .inbox import get as get_message
from .security import require_case_write

SENSITIVE = re.compile(
    r"\b(?:salary|salaire|pay|paid|compensation|rémunération|bonus|offer amount|"
    r"decision|décision|rejected|refus\w*|accepted|selected|other candidates?|autres? candidats?|"
    r"health|santé|medical|médical|pregnan\w*|enceinte|disabilit\w*|handicap|religio\w*|"
    r"discriminat\w*|lawyer|avocat|legal action|lawsuit|procès)\b", re.IGNORECASE)

SIGN_OFF = "\n\nBest regards,\nThe recruitment team"


def _fmt(dt: datetime, tz: ZoneInfo) -> str:
    local = dt.astimezone(tz)
    return local.strftime("%A %d %B %Y at %H:%M") + f" ({tz.key})"


def compose(*, category: str, case_title: str, sensitive: bool, interview: dict | None,
            free: list[dict], tz: ZoneInfo) -> tuple[str, str, list[str]]:
    """Return (subject, body, facts). facts = every string the body may contain dates/numbers from."""
    facts = [case_title]
    subject = f"Re: your message about {case_title}"
    lines = ["Hello,", "", f"Thank you for your message about your application for {case_title}."]
    if sensitive:
        lines.append("A member of the recruitment team will reply to you personally about this.")
    elif category == "scheduling":
        if interview:
            when = _fmt(interview["start"], tz)
            facts.append(when)
            facts.append(str(interview["duration"]))
            lines.append(f"Your {interview['duration']}-minute interview is currently planned for {when}.")
        if free:
            labels = [_fmt(datetime.fromisoformat(s["start"].replace("Z", "+00:00")), tz) for s in free]
            facts.extend(labels)
            lines.append("If you need a different time, these times are free in our calendar:" if interview
                         else "These times are free in our calendar:")
            lines.extend(f"- {label}" for label in labels)
            lines.append("Please reply with the time that suits you best.")
        elif not interview:
            lines.append("A recruiter will propose interview times shortly.")
    elif category == "withdrawal":
        lines.append("We have noted your message about withdrawing. A recruiter will confirm the next steps with you.")
    elif category == "documents":
        lines.append("For your security we do not open email attachments. A recruiter will tell you how to share "
                     "documents safely.")
    elif category == "question":
        lines.append("A member of the recruitment team will answer your question shortly.")
    else:
        lines.append("A member of the recruitment team will get back to you shortly.")
    body = "\n".join(lines) + SIGN_OFF
    return subject, body, facts


_TOKEN = re.compile(r"\d+|https?://\S+|www\.\S+|\S+@\S+")


def grounded(body: str, facts: list[str]) -> list[str]:
    """Return the tokens in the draft that are not backed by an allowed fact (empty list = grounded)."""
    allowed = " ".join(facts)
    bad = []
    for tok in _TOKEN.findall(body):
        if "@" in tok or "http" in tok or tok.startswith("www."):
            bad.append(tok)                          # no addresses or links, ever
        elif tok not in allowed:
            bad.append(tok)
    return bad


def _next_interview(candidate_id: str):
    r = db.one("SELECT scheduled_start, duration_minutes, interviewer_id, timezone FROM interviews WHERE candidate_id=? "
               "AND status IN ('scheduled','confirmed') AND scheduled_start>? ORDER BY scheduled_start LIMIT 1",
               (candidate_id, db.now()))
    if not r:
        return None
    return {"start": datetime.fromisoformat(r["scheduled_start"].replace("Z", "+00:00")).astimezone(timezone.utc),
            "duration": r["duration_minutes"], "interviewer_id": r["interviewer_id"], "timezone": r["timezone"]}


def draft(user: dict, mid: str, tz_name: str = "UTC") -> tuple[dict, bool]:
    m = get_message(user, mid)
    if m["category"] == "security_review":
        raise conflict("NEEDS_HUMAN_REVIEW", "This message has security flags. Vouch does not draft replies to it.")
    if not m["candidate"] or not m["case"]:
        raise conflict("SENDER_NOT_CONFIRMED", "The sender is not a confirmed candidate address, so Vouch cannot reply.")
    case_id, cand_id = m["case"]["id"], m["candidate"]["id"]
    case = require_case_write(user, case_id, roles=("recruiter",))
    row = db.one("SELECT reply_proposal_id FROM inbound_messages WHERE id=?", (mid,))
    if row["reply_proposal_id"]:
        return gateway.get_proposal(user, row["reply_proposal_id"]), False
    try:
        tz = ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001
        tz = ZoneInfo("UTC")
    text = db.one("SELECT safe_text, subject FROM inbound_messages WHERE id=?", (mid,))
    sensitive = bool(SENSITIVE.search(f"{text['subject']}\n{text['safe_text']}"))
    interview = _next_interview(cand_id)
    free: list[dict] = []
    if m["category"] == "scheduling" and not sensitive:
        interviewer = interview["interviewer_id"] if interview else (db.one(
            "SELECT m.user_id FROM case_members m JOIN users u ON u.id=m.user_id WHERE m.case_id=? AND u.role='hiring_manager' "
            "LIMIT 1", (case_id,)) or {"user_id": None})["user_id"]
        if interviewer:
            with db.tx() as conn:
                busy = slots._busy(conn, cand_id, interviewer)
            free = slots.find(busy, now=db.utcnow(), tz=tz, duration=interview["duration"] if interview else 45,
                              days=10, count=3)
    subject, body, facts = compose(category=m["category"], case_title=case["title"], sensitive=sensitive,
                                   interview=interview, free=free, tz=tz)
    bad = grounded(body, facts)
    if bad:
        raise ApiError(500, "UNGROUNDED_DRAFT", "The draft contained facts Vouch cannot back up, so it was not created.")
    proposal = gateway.create_proposal(user, case_id, schemas.ProposalCreate(candidate_id=cand_id, kind="follow_up"),
                                       composed={"subject": subject, "body": body, "in_reply_to": mid})
    with db.tx() as conn:
        conn.execute("UPDATE inbound_messages SET reply_proposal_id=? WHERE id=?", (proposal["id"], mid))
    proposal["sensitive_topic"] = sensitive
    return proposal, True


def message_exists(mid: str) -> None:
    if not db.one("SELECT 1 FROM inbound_messages WHERE id=?", (mid,)):
        raise not_found("Message")
