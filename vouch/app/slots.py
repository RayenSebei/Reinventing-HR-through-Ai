"""F4: suggest free interview slots from the agenda.

Busy time = the interviewer's scheduled/confirmed interviews and internal meetings (as organizer or
attendee) plus the candidate's own interviews. A slot must sit inside working hours on a weekday,
not cross the lunch break, start at least two hours from now, and keep a 10-minute buffer around busy
time. The result is a suggestion only: booking still goes through the normal interview checks, and no
message is sent.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import config, db
from .errors import invalid
from .scheduling import _validate_interview_links, _when
from .security import require_case_write

STEP = timedelta(minutes=30)
BUFFER = timedelta(minutes=10)
LUNCH = (12, 13)


def _busy(conn, candidate_id: str, interviewer_id: str) -> list[tuple[datetime, datetime]]:
    out = []
    for r in conn.execute("SELECT scheduled_start, duration_minutes FROM interviews WHERE status IN ('scheduled','confirmed') "
                          "AND (interviewer_id=? OR candidate_id=?)", (interviewer_id, candidate_id)):
        s = _when(r["scheduled_start"])
        out.append((s, s + timedelta(minutes=r["duration_minutes"])))
    for r in conn.execute("SELECT DISTINCT m.start, m.duration_minutes FROM meetings m LEFT JOIN meeting_attendees a "
                          "ON a.meeting_id=m.id WHERE m.status='scheduled' AND (m.organizer_id=? OR a.user_id=?)",
                          (interviewer_id, interviewer_id)):
        s = _when(r["start"])
        out.append((s, s + timedelta(minutes=r["duration_minutes"])))
    return out


def find(busy, *, now: datetime, tz: ZoneInfo, duration: int, days: int, count: int) -> list[dict]:
    """Pure function (tested directly): at most two slots per day, one morning and one afternoon first."""
    length = timedelta(minutes=duration)
    earliest = now + timedelta(hours=2)
    local_now = earliest.astimezone(tz)
    per_day: dict = {}
    day = local_now.date()
    for _ in range(days + 1):
        if day.weekday() < 5:
            t = datetime(day.year, day.month, day.day, config.WORK_START_HOUR, tzinfo=tz)
            end_of_day = datetime(day.year, day.month, day.day, 0, tzinfo=tz) + timedelta(hours=config.WORK_END_HOUR)
            while t + length <= end_of_day:
                a, b = t.astimezone(timezone.utc), (t + length).astimezone(timezone.utc)
                lunch_a = t.replace(hour=LUNCH[0], minute=0)
                lunch_b = t.replace(hour=LUNCH[1], minute=0)
                crosses_lunch = t < lunch_b and t + length > lunch_a
                clash = any(a < be + BUFFER and bs - BUFFER < b for bs, be in busy)
                if a >= earliest and not crosses_lunch and not clash:
                    per_day.setdefault(day, []).append((t, a, b))
                t += STEP
        day += timedelta(days=1)
    chosen = []
    for day in sorted(per_day):
        options = per_day[day]
        morning = [o for o in options if o[0].hour < LUNCH[0]]
        afternoon = [o for o in options if o[0].hour >= LUNCH[1]]
        for group in (morning, afternoon):
            if group:
                chosen.append(group[min(1, len(group) - 1)] if group is morning else group[0])
    chosen.sort(key=lambda o: o[1])
    out = []
    for t, a, b in chosen[:count]:
        out.append({"start": a.strftime("%Y-%m-%dT%H:%M:%SZ"), "end": b.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "local_label": f"{t.strftime('%a %d %b')} · {t.strftime('%H:%M')}–{(t + length).strftime('%H:%M')}"})
    return out


def suggest(user: dict, case_id: str, params: dict) -> dict:
    require_case_write(user, case_id, roles=("recruiter",))
    allowed = {"candidate_id", "interviewer_id", "duration", "timezone", "days", "count"}
    extra = set(params) - allowed
    if extra:
        raise invalid(f"Unknown query parameter(s): {', '.join(sorted(extra))}.")
    try:
        duration = int(params.get("duration", 45))
        days = int(params.get("days", 10))
        count = int(params.get("count", 5))
    except ValueError:
        raise invalid("duration, days and count must be whole numbers.")
    if not (15 <= duration <= 240 and duration % 15 == 0):
        raise invalid("duration must be 15..240 minutes in steps of 15.")
    if not (1 <= days <= 21) or not (1 <= count <= 10):
        raise invalid("days must be 1..21 and count 1..10.")
    tz_name = params.get("timezone") or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise invalid("timezone must be an IANA time zone such as Africa/Tunis.")
    candidate_id, interviewer_id = params.get("candidate_id", ""), params.get("interviewer_id", "")
    if not candidate_id or not interviewer_id:
        raise invalid("candidate_id and interviewer_id are required.")
    with db.tx() as conn:
        _validate_interview_links(conn, case_id, candidate_id, interviewer_id)
        busy = _busy(conn, candidate_id, interviewer_id)
    slots = find(busy, now=db.utcnow(), tz=tz, duration=duration, days=days, count=count)
    return {"timezone": tz_name, "duration_minutes": duration, "slots": slots, "busy_blocks_considered": len(busy),
            "rules": f"Weekdays {config.WORK_START_HOUR:02d}:00–{config.WORK_END_HOUR:02d}:00 ({tz_name}), no lunch "
                     f"12:00–13:00, 10-minute buffer around interviews and meetings, at least 2 hours from now. "
                     "A suggestion only: nothing is booked or sent."}
