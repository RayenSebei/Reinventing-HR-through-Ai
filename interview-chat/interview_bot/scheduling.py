"""Propose interview slots from the recruiter's calendar (data/calendar.json).

Replace load_busy() with a Google/Microsoft calendar connector later; the
rest stays the same. Slots are only PROPOSED: sending them needs approval.
"""
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .config import BASE_DIR

CAL_PATH = BASE_DIR / "data" / "calendar.json"


def load_calendar() -> dict:
    if CAL_PATH.exists():
        return json.loads(CAL_PATH.read_text(encoding="utf-8"))
    return {"timezone": "Africa/Tunis", "work_days": [0, 1, 2, 3, 4], "work_hours": [9, 17],
            "slot_minutes": 60, "busy": []}


def propose_slots(count: int = 3, now: datetime | None = None, horizon_days: int = 14) -> list[dict]:
    cal = load_calendar()
    tz = ZoneInfo(cal.get("timezone", "Africa/Tunis"))
    now = (now or datetime.now(tz)).astimezone(tz)
    step = timedelta(minutes=cal.get("slot_minutes", 60))
    busy = [(datetime.fromisoformat(b["start"]).astimezone(tz), datetime.fromisoformat(b["end"]).astimezone(tz))
            for b in cal.get("busy", [])]
    start_h, end_h = cal.get("work_hours", [9, 17])
    day = (now + timedelta(days=1)).replace(hour=start_h, minute=0, second=0, microsecond=0)  # never same day
    slots = []
    while len(slots) < count and day < now + timedelta(days=horizon_days):
        if day.weekday() in cal.get("work_days", [0, 1, 2, 3, 4]):
            t = day
            while t + step <= day.replace(hour=end_h) and len(slots) < count:
                if not any(t < b_end and t + step > b_start for b_start, b_end in busy):
                    slots.append({"start": t.isoformat(), "end": (t + step).isoformat()})
                    t += step * 3          # spread the proposals across the day
                else:
                    t += step
        day += timedelta(days=1)
    return slots
