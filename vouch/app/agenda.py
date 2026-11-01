"""Agenda: one calendar feed of interviews and internal meetings, plus the interview format.

Internal meetings (not about recruitment) block people's time, so an interview cannot be booked
on top of a meeting and a meeting cannot be booked on top of an interview. People who are not
invited see a meeting only as "Busy": no title, description or location.

Interview format. Vouch SUGGESTS a format from the confirmed ranking (job-related evidence only):
  - a CV with document findings or borderline evidence -> "recruiter" (a person must look),
  - a strong match (score >= FAST_TRACK_SCORE, nothing missing) -> "senior_hr" (fast track),
  - otherwise -> "ai_chat" first round, with stated safeguards (a person reads every transcript,
    the candidate can ask for a human at any time; the AI chat never rejects anyone).
A recruiter on the case DECIDES. The suggestion and the decision are both recorded in the ledger.

Who conducted the interview: "ai" (interview-chat) or "human". AI -> human is allowed; once a
person has interviewed the candidate the record is never turned back into "ai".
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

from . import db, ledger
from .errors import conflict, forbidden, invalid, not_found
from .security import READ_ALL_ROLES, is_member, require_case_read, require_case_write

FAST_TRACK_SCORE = int(os.environ.get("VOUCH_FAST_TRACK_SCORE", "80"))
MAX_RANGE_DAYS = 62
_MEETING_ROLES = ("recruiter", "hiring_manager", "hr_admin")
_MEETING_FIELDS = ("title", "start", "duration_minutes", "timezone", "location", "description")
FORMAT_LABELS = {"ai_chat": "AI chat interview (first round)", "recruiter": "Recruiter",
                 "senior_hr": "Senior HR interviewer"}


def _when(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# --- shared busy-time check (used by meetings and by scheduling) ----------------------------
def overlapping_meeting(conn, user_ids, start: str, duration_minutes: int, exclude_id: str | None = None):
    """First scheduled meeting where any of user_ids is organizer or attendee and the time overlaps."""
    ids = list(dict.fromkeys(user_ids))
    if not ids:
        return None
    s = _when(start)
    e = s + timedelta(minutes=duration_minutes)
    marks = ",".join("?" for _ in ids)
    sql = (f"SELECT DISTINCT m.id, m.start, m.duration_minutes FROM meetings m "
           f"LEFT JOIN meeting_attendees a ON a.meeting_id=m.id "
           f"WHERE m.status='scheduled' AND (m.organizer_id IN ({marks}) OR a.user_id IN ({marks}))")
    args: list = [*ids, *ids]
    if exclude_id:
        sql += " AND m.id<>?"
        args.append(exclude_id)
    for row in conn.execute(sql, tuple(args)).fetchall():
        ms = _when(row["start"])
        if s < ms + timedelta(minutes=row["duration_minutes"]) and ms < e:
            return row
    return None


def _overlapping_interview(conn, user_ids, start: str, duration_minutes: int):
    ids = list(dict.fromkeys(user_ids))
    s = _when(start)
    e = s + timedelta(minutes=duration_minutes)
    marks = ",".join("?" for _ in ids)
    for row in conn.execute(f"SELECT id, scheduled_start, duration_minutes FROM interviews "
                            f"WHERE status IN ('scheduled','confirmed') AND interviewer_id IN ({marks})",
                            tuple(ids)).fetchall():
        st = _when(row["scheduled_start"])
        if s < st + timedelta(minutes=row["duration_minutes"]) and st < e:
            return row
    return None


# --- meetings ----------------------------------------------------------------------------
def _attendees(meeting_id: str) -> list[str]:
    return [r["user_id"] for r in db.q("SELECT user_id FROM meeting_attendees WHERE meeting_id=? ORDER BY user_id",
                                       (meeting_id,))]


def _meeting_out(row, viewer: dict) -> dict:
    attendees = _attendees(row["id"])
    names = {r["id"]: r["name"] for r in db.q(
        "SELECT id, name FROM users WHERE id IN (" + ",".join("?" for _ in attendees) + ")", tuple(attendees))} \
        if attendees else {}
    invited = viewer["id"] == row["organizer_id"] or viewer["id"] in attendees
    base = {"kind": "meeting", "id": row["id"], "start": row["start"], "duration_minutes": row["duration_minutes"],
            "timezone": row["timezone"], "status": row["status"], "private": not invited,
            "attendee_ids": attendees, "attendee_names": [names.get(a, a) for a in attendees],
            "organizer_id": row["organizer_id"], "can_edit": viewer["id"] == row["organizer_id"]}
    if invited:
        base.update(title=row["title"], description=row["description"], location=row["location"])
    else:
        base.update(title="Busy", description="", location="")
    return base


def _check_attendees(conn, ids: list[str]) -> None:
    for uid in ids:
        u = conn.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()
        if not u:
            raise invalid("Every attendee must be a Vouch user.")


def _assert_free(conn, people, start, minutes, exclude_meeting=None):
    if _when(start) <= db.utcnow():
        raise invalid("The meeting must start in the future.")
    m = overlapping_meeting(conn, people, start, minutes, exclude_meeting)
    if m:
        raise conflict("MEETING_CONFLICT", "Someone invited already has a meeting at that time.", meeting_id=m["id"])
    i = _overlapping_interview(conn, people, start, minutes)
    if i:
        raise conflict("MEETING_CONFLICT", "Someone invited has an interview at that time.", interview_id=i["id"])


def create_meeting(user: dict, body) -> dict:
    if user["role"] not in _MEETING_ROLES:
        raise forbidden("FORBIDDEN_ROLE", "Your role can read the agenda but not add meetings.")
    people = list(dict.fromkeys([user["id"], *body.attendee_ids]))
    mid = db.new_id("MEET")
    now = db.now()
    with db.tx() as conn:
        _check_attendees(conn, people)
        _assert_free(conn, people, body.start, body.duration_minutes)
        conn.execute("INSERT INTO meetings(id,title,description,start,duration_minutes,timezone,location,"
                     "organizer_id,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (mid, body.title, body.description, body.start, body.duration_minutes, body.timezone,
                      body.location, user["id"], "scheduled", now, now))
        for uid in people:
            conn.execute("INSERT INTO meeting_attendees VALUES(?,?)", (mid, uid))
        # The ledger records that a meeting exists and who attends, never its title or notes.
        ledger.append(conn, user["id"], "MEETING_CREATED", None, mid,
                      {"start": body.start, "duration_minutes": body.duration_minutes, "attendees": sorted(people)})
    return _meeting_out(db.one("SELECT * FROM meetings WHERE id=?", (mid,)), user)


def _own_meeting(user: dict, meeting_id: str):
    row = db.one("SELECT * FROM meetings WHERE id=?", (meeting_id,))
    if not row:
        raise not_found("Meeting")
    if row["organizer_id"] != user["id"]:
        raise forbidden("NOT_ORGANIZER", "Only the person who created this meeting can change it.")
    if row["status"] == "cancelled":
        raise conflict("MEETING_CANCELLED", "This meeting was cancelled.")
    return row


def update_meeting(user: dict, meeting_id: str, values: dict) -> dict:
    if not values:
        raise invalid("Set at least one meeting field.")
    row = _own_meeting(user, meeting_id)
    if any(values.get(k) is None for k in values):
        raise invalid("Meeting fields cannot be null.")
    merged = {**dict(row), **{k: v for k, v in values.items() if k in _MEETING_FIELDS}}
    people = list(dict.fromkeys([user["id"], *(values.get("attendee_ids") or _attendees(meeting_id))]))
    with db.tx() as conn:
        _check_attendees(conn, people)
        if {"start", "duration_minutes", "attendee_ids"} & set(values):
            _assert_free(conn, people, merged["start"], merged["duration_minutes"], meeting_id)
        sets = [f"{k}=?" for k in values if k in _MEETING_FIELDS]
        if sets:
            conn.execute(f"UPDATE meetings SET {','.join(sets)},updated_at=? WHERE id=?",
                         (*[merged[k] for k in values if k in _MEETING_FIELDS], db.now(), meeting_id))
        if "attendee_ids" in values:
            conn.execute("DELETE FROM meeting_attendees WHERE meeting_id=?", (meeting_id,))
            for uid in people:
                conn.execute("INSERT INTO meeting_attendees VALUES(?,?)", (meeting_id, uid))
        ledger.append(conn, user["id"], "MEETING_UPDATED", None, meeting_id, {"changed_fields": sorted(values)})
    return _meeting_out(db.one("SELECT * FROM meetings WHERE id=?", (meeting_id,)), user)


def cancel_meeting(user: dict, meeting_id: str) -> dict:
    _own_meeting(user, meeting_id)
    with db.tx() as conn:
        conn.execute("UPDATE meetings SET status='cancelled', updated_at=? WHERE id=?", (db.now(), meeting_id))
        ledger.append(conn, user["id"], "MEETING_CANCELLED", None, meeting_id, {})
    return _meeting_out(db.one("SELECT * FROM meetings WHERE id=?", (meeting_id,)), user)


# --- interview format -------------------------------------------------------------------------
def _ranking_row(case_id: str, candidate_id: str) -> dict | None:
    r = db.one("SELECT payload_json FROM rankings WHERE case_id=? AND status='CONFIRMED' ORDER BY version DESC LIMIT 1",
               (case_id,))
    if not r:
        return None
    return next((x for x in db.loads(r["payload_json"], []) if x.get("candidate_id") == candidate_id), None)


def recommend(case_id: str, candidate_id: str) -> tuple[str, list[str]]:
    row = _ranking_row(case_id, candidate_id)
    safeguards = ["A person reads every AI chat transcript before any decision.",
                  "The candidate can ask for a human interviewer at any time.",
                  "The AI chat never rejects anyone; it only collects answers."]
    if not row:
        return "recruiter", ["No confirmed ranking for this candidate, so a recruiter should run the interview."]
    breakdown = row.get("breakdown") or []
    met = sum(1 for b in breakdown if b.get("status") in ("SOURCED", "VERIFIED"))
    total = len(breakdown)
    match = f"Matches {met}/{total} criteria with quotes from the CV (score {row.get('score')})." if total else \
        f"Ranking score {row.get('score')}."
    flags = row.get("flags") or []
    if flags:
        return "recruiter", [match, "The CV has items flagged for human review (" + ", ".join(
            f.replace("_", " ").lower() for f in flags) + "), so a person should interview, not the AI chat."]
    if (row.get("score") or 0) >= FAST_TRACK_SCORE and not row.get("missing"):
        return "senior_hr", [match, f"Strong match (score of {FAST_TRACK_SCORE} or more, nothing missing): "
                             "fast-track to a senior HR interviewer so we don't lose the candidate."]
    missing = row.get("missing") or []
    why = [match]
    if missing:
        why.append("No evidence yet for: " + ", ".join(missing) + ". The first round can ask about it.")
    why.append("Suggested first round: AI chat interview.")
    return "ai_chat", why + safeguards


def _interview_row(interview_id: str):
    row = db.one("SELECT * FROM interviews WHERE id=?", (interview_id,))
    if not row:
        raise not_found("Interview")
    return row


def format_info(interview_row) -> dict:
    rec, reasons = recommend(interview_row["case_id"], interview_row["candidate_id"])
    f = db.one("SELECT * FROM interview_formats WHERE interview_id=?", (interview_row["id"],))
    decided = f["decided"] if f else None
    return {"interview_id": interview_row["id"], "recommended": rec, "recommended_label": FORMAT_LABELS[rec],
            "reasons": reasons, "decided": decided, "decided_label": FORMAT_LABELS.get(decided) if decided else None,
            "decided_by": f["decided_by"] if f else None, "decided_at": f["decided_at"] if f else None,
            "overridden": bool(decided and f["recommended_at_decision"] and decided != f["recommended_at_decision"]),
            "conducted_by": f["conducted_by"] if f else None,
            "conducted_by_set_by": f["conducted_by_set_by"] if f else None,
            "conducted_by_at": f["conducted_by_at"] if f else None,
            "statement": "A suggestion based only on job-related CV evidence. A recruiter decides."}


def get_format(user: dict, interview_id: str) -> dict:
    row = _interview_row(interview_id)
    require_case_read(user, row["case_id"])
    return format_info(row)


def decide_format(user: dict, interview_id: str, fmt: str) -> dict:
    row = _interview_row(interview_id)
    require_case_read(user, row["case_id"])
    require_case_write(user, row["case_id"], roles=("recruiter",))
    rec, _ = recommend(row["case_id"], row["candidate_id"])
    now = db.now()
    with db.tx() as conn:
        conn.execute("INSERT INTO interview_formats(interview_id,decided,recommended_at_decision,decided_by,decided_at) "
                     "VALUES(?,?,?,?,?) ON CONFLICT(interview_id) DO UPDATE SET decided=excluded.decided, "
                     "recommended_at_decision=excluded.recommended_at_decision, decided_by=excluded.decided_by, "
                     "decided_at=excluded.decided_at", (interview_id, fmt, rec, user["id"], now))
        ledger.append(conn, user["id"], "INTERVIEW_FORMAT_DECIDED", row["case_id"], interview_id,
                      {"recommended": rec, "decided": fmt, "overridden": rec != fmt})
    return format_info(row)


def set_conducted_by(user: dict, interview_id: str, by: str) -> dict:
    row = _interview_row(interview_id)
    require_case_read(user, row["case_id"])
    allowed = user["role"] == "recruiter" or (user["role"] == "hiring_manager" and row["interviewer_id"] == user["id"])
    if not allowed or not is_member(user, row["case_id"]):
        raise forbidden("FORBIDDEN_ROLE", "Only a recruiter on the case or the assigned interviewer can record this.")
    current = db.one("SELECT conducted_by FROM interview_formats WHERE interview_id=?", (interview_id,))
    if current and current["conducted_by"] == "human" and by == "ai":
        raise conflict("ALREADY_HUMAN", "A person already interviewed this candidate; that record can't be changed back to AI.")
    now = db.now()
    with db.tx() as conn:
        conn.execute("INSERT INTO interview_formats(interview_id,conducted_by,conducted_by_set_by,conducted_by_at) "
                     "VALUES(?,?,?,?) ON CONFLICT(interview_id) DO UPDATE SET conducted_by=excluded.conducted_by, "
                     "conducted_by_set_by=excluded.conducted_by_set_by, conducted_by_at=excluded.conducted_by_at",
                     (interview_id, by, user["id"], now))
        ledger.append(conn, user["id"], "INTERVIEW_CONDUCTED_BY", row["case_id"], interview_id,
                      {"by": by, "previous": current["conducted_by"] if current else None})
    return format_info(row)


# --- the calendar feed ---------------------------------------------------------------------------
def _parse_day(value: str | None, name: str) -> date:
    try:
        return date.fromisoformat(value or "")
    except ValueError:
        raise invalid(f"{name} must be a date like 2026-11-02.")


def agenda(user: dict, from_day: str | None, to_day: str | None) -> dict:
    start, end = _parse_day(from_day, "from"), _parse_day(to_day, "to")
    if end < start or (end - start).days > MAX_RANGE_DAYS:
        raise invalid(f"to must be on or after from, at most {MAX_RANGE_DAYS} days later.")
    lo = datetime(start.year, start.month, start.day, tzinfo=timezone.utc) - timedelta(days=1)
    hi = datetime(end.year, end.month, end.day, tzinfo=timezone.utc) + timedelta(days=2)
    if user["role"] in READ_ALL_ROLES:
        case_ids = [r["id"] for r in db.q("SELECT id FROM cases")]
    else:
        case_ids = [r["case_id"] for r in db.q("SELECT case_id FROM case_members WHERE user_id=?", (user["id"],))]
    events: list[dict] = []
    if case_ids:
        marks = ",".join("?" for _ in case_ids)
        for row in db.q(
                f"SELECT i.*, c.pseudonym candidate_pseudonym, cs.title case_title, u.name interviewer_name "
                f"FROM interviews i JOIN candidates c ON c.id=i.candidate_id JOIN cases cs ON cs.id=i.case_id "
                f"JOIN users u ON u.id=i.interviewer_id WHERE i.case_id IN ({marks}) AND i.status<>'cancelled' "
                f"AND i.scheduled_start>=? AND i.scheduled_start<? ORDER BY i.scheduled_start",
                (*case_ids, _iso(lo), _iso(hi))):
            ev = dict(row)
            ev.update(kind="interview", start=row["scheduled_start"], format=format_info(row),
                      can_edit=user["role"] == "recruiter" and is_member(user, row["case_id"]))
            events.append(ev)
    for row in db.q("SELECT * FROM meetings WHERE status='scheduled' AND start>=? AND start<? ORDER BY start",
                    (_iso(lo), _iso(hi))):
        events.append(_meeting_out(row, user))
    events.sort(key=lambda e: (e["start"], e["kind"], e["id"]))
    return {"from": start.isoformat(), "to": end.isoformat(), "events": events,
            "fast_track_score": FAST_TRACK_SCORE}

