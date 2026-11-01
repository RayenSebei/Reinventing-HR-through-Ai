"""Case-scoped interview scheduling and persistent follow-up tasks."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import db, ledger
from .errors import conflict, invalid, not_found
from .security import READ_ALL_ROLES, is_member, require_case_read, require_case_write


_INTERVIEW_FIELDS = (
    "interviewer_id", "interview_type", "scheduled_start", "duration_minutes",
    "timezone", "location", "preparation_notes", "feedback", "status",
)
_TASK_FIELDS = (
    "title", "description", "task_type", "candidate_id", "interview_id",
    "proposal_id", "assigned_to", "due_at", "priority", "status",
)


def _when(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _interview(row) -> dict:
    return dict(row)


def _task(row) -> dict:
    return dict(row)


def _candidate_is_shortlisted(conn, case_id: str, candidate_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM shortlisted_candidates s JOIN rankings r "
        "ON r.case_id=s.case_id AND r.version=s.ranking_version "
        "WHERE s.case_id=? AND s.candidate_id=? AND r.status='CONFIRMED' LIMIT 1",
        (case_id, candidate_id),
    ).fetchone() is not None


def _validate_interview_links(conn, case_id: str, candidate_id: str, interviewer_id: str) -> None:
    candidate = conn.execute("SELECT case_id FROM candidates WHERE id=?", (candidate_id,)).fetchone()
    interviewer = conn.execute("SELECT id FROM users WHERE id=?", (interviewer_id,)).fetchone()
    if not candidate or candidate["case_id"] != case_id:
        raise not_found("Candidate")
    if not interviewer or conn.execute(
        "SELECT 1 FROM case_members WHERE case_id=? AND user_id=?", (case_id, interviewer_id)
    ).fetchone() is None:
        raise invalid("The interviewer must be a member of this case.")
    if not _candidate_is_shortlisted(conn, case_id, candidate_id):
        raise conflict("NOT_SHORTLISTED", "An interview can only be scheduled for a confirmed shortlisted candidate.")


def _assert_no_overlap(conn, candidate_id: str, interviewer_id: str, start: str,
                       duration_minutes: int, exclude_id: str | None = None) -> None:
    start_dt = _when(start)
    end_dt = start_dt.timestamp() + duration_minutes * 60
    sql = (
        "SELECT id, candidate_id, interviewer_id, scheduled_start, duration_minutes FROM interviews "
        "WHERE status IN ('scheduled','confirmed') AND (candidate_id=? OR interviewer_id=?)"
    )
    args: list = [candidate_id, interviewer_id]
    if exclude_id is not None:
        sql += " AND id<>?"
        args.append(exclude_id)
    for row in conn.execute(sql, tuple(args)).fetchall():
        existing_start = _when(row["scheduled_start"]).timestamp()
        existing_end = existing_start + row["duration_minutes"] * 60
        if start_dt.timestamp() < existing_end and existing_start < end_dt:
            if row["candidate_id"] == candidate_id:
                message = "This candidate already has an overlapping interview."
            else:
                message = "This interviewer already has an overlapping interview."
            raise conflict("INTERVIEW_CONFLICT", message, interview_id=row["id"])
    # Internal meetings block the interviewer's time too (agenda.py).
    from .agenda import overlapping_meeting
    meeting = overlapping_meeting(conn, [interviewer_id], start, duration_minutes)
    if meeting:
        raise conflict("INTERVIEW_CONFLICT", "This interviewer has a meeting at that time.", meeting_id=meeting["id"])


def create_interview(user: dict, body) -> dict:
    case_id = body.case_id
    require_case_write(user, case_id, roles=("recruiter",))
    start = body.scheduled_start
    if _when(start) <= db.utcnow():
        raise invalid("scheduled_start must be in the future.")
    interview_id = db.new_id("INT")
    with db.tx() as conn:
        if _when(start) <= db.utcnow():
            raise invalid("scheduled_start must be in the future.")
        _validate_interview_links(conn, case_id, body.candidate_id, body.interviewer_id)
        _assert_no_overlap(conn, body.candidate_id, body.interviewer_id, start, body.duration_minutes)
        now = db.now()
        conn.execute(
            "INSERT INTO interviews(id,case_id,candidate_id,interviewer_id,interview_type,scheduled_start,"
            "duration_minutes,timezone,location,preparation_notes,created_by,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (interview_id, case_id, body.candidate_id, body.interviewer_id, body.interview_type, start,
             body.duration_minutes, body.timezone, body.location, body.preparation_notes,
             user["id"], now, now),
        )
        ledger.append(conn, user["id"], "INTERVIEW_CREATED", case_id, interview_id,
                      {"candidate_id": body.candidate_id, "interviewer_id": body.interviewer_id,
                       "scheduled_start": start, "duration_minutes": body.duration_minutes})
        return _interview(conn.execute("SELECT * FROM interviews WHERE id=?", (interview_id,)).fetchone())


def list_interviews(user: dict, *, case_id: str | None = None, candidate_id: str | None = None,
                    status: str | None = None, from_date: str | None = None, to_date: str | None = None,
                    limit: int = 50, offset: int = 0) -> dict:
    if limit < 1 or limit > 100 or offset < 0:
        raise invalid("limit must be 1..100, offset >= 0.")
    if status not in (None, "scheduled", "confirmed", "completed", "cancelled"):
        raise invalid("Unsupported interview status.")
    if from_date:
        try:
            datetime.fromisoformat(from_date)
        except ValueError:
            raise invalid("from_date must be an ISO date.")
    if to_date:
        try:
            datetime.fromisoformat(to_date)
        except ValueError:
            raise invalid("to_date must be an ISO date.")

    if case_id is not None:
        require_case_read(user, case_id)
        case_ids = [case_id]
    elif user["role"] in READ_ALL_ROLES:
        case_ids = [row["id"] for row in db.q("SELECT id FROM cases ORDER BY id")]
    else:
        case_ids = [row["case_id"] for row in db.q(
            "SELECT case_id FROM case_members WHERE user_id=? ORDER BY case_id", (user["id"],))]
    if not case_ids:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    where = ["i.case_id IN (" + ",".join("?" for _ in case_ids) + ")"]
    args: list = list(case_ids)
    if candidate_id:
        where.append("i.candidate_id=?")
        args.append(candidate_id)
    if status:
        where.append("i.status=?")
        args.append(status)
    if from_date:
        where.append("i.scheduled_start>=?")
        args.append(from_date + "T00:00:00Z")
    if to_date:
        where.append("i.scheduled_start<?")
        args.append(to_date + "T23:59:59.999999Z")
    where_sql = " AND ".join(where)
    total = db.one(f"SELECT COUNT(*) n FROM interviews i WHERE {where_sql}", tuple(args))["n"]
    rows = db.q(
        f"SELECT i.*,c.pseudonym candidate_pseudonym,cs.title case_title,u.name interviewer_name "
        f"FROM interviews i JOIN candidates c ON c.id=i.candidate_id "
        f"JOIN cases cs ON cs.id=i.case_id JOIN users u ON u.id=i.interviewer_id "
        f"WHERE {where_sql} ORDER BY i.scheduled_start,i.id LIMIT ? OFFSET ?",
        (*args, limit, offset),
    )
    return {"items": [_interview(row) for row in rows], "total": total, "limit": limit, "offset": offset}


def get_interview(user: dict, interview_id: str) -> dict:
    row = db.one(
        "SELECT i.*,c.pseudonym candidate_pseudonym,cs.title case_title,u.name interviewer_name "
        "FROM interviews i JOIN candidates c ON c.id=i.candidate_id "
        "JOIN cases cs ON cs.id=i.case_id JOIN users u ON u.id=i.interviewer_id WHERE i.id=?",
        (interview_id,))
    if not row:
        raise not_found("Interview")
    require_case_read(user, row["case_id"])
    return _interview(row)


def update_interview(user: dict, interview_id: str, values: dict) -> dict:
    if not values:
        raise invalid("Set at least one interview field.")
    row = db.one("SELECT * FROM interviews WHERE id=?", (interview_id,))
    if not row:
        raise not_found("Interview")
    require_case_write(user, row["case_id"], roles=("recruiter", "hiring_manager"))
    if user["role"] == "hiring_manager":
        if row["interviewer_id"] != user["id"] or set(values) - {"status", "feedback"}:
            raise invalid("An interviewer may only update their interview status and feedback.")
    elif set(values) - set(_INTERVIEW_FIELDS):
        raise invalid("Unknown interview field.")
    if row["status"] in ("completed", "cancelled"):
        raise conflict("INTERVIEW_CLOSED", "A completed or cancelled interview cannot be changed.")
    if values.get("status") == "cancelled" and user["role"] != "recruiter":
        raise invalid("Only a recruiter can cancel an interview.")

    updated = dict(row)
    updated.update({key: value for key, value in values.items() if key in _INTERVIEW_FIELDS})
    for required in ("interviewer_id", "interview_type", "scheduled_start", "duration_minutes", "timezone", "status"):
        if updated[required] is None:
            raise invalid(f"{required} cannot be null.")
    if updated["status"] == "cancelled" and user["role"] != "recruiter":
        raise invalid("Only a recruiter can cancel an interview.")
    if updated["status"] in ("scheduled", "confirmed") and _when(updated["scheduled_start"]) <= db.utcnow():
        raise invalid("scheduled_start must be in the future.")
    if any(updated.get(key) is None for key in ("location", "preparation_notes", "feedback")):
        raise invalid("Interview text fields cannot be null.")

    now = db.now()
    with db.tx() as conn:
        if user["role"] == "recruiter":
            _validate_interview_links(conn, row["case_id"], row["candidate_id"], updated["interviewer_id"])
        if updated["status"] in ("scheduled", "confirmed"):
            if _when(updated["scheduled_start"]) <= db.utcnow():
                raise invalid("scheduled_start must be in the future.")
            _assert_no_overlap(conn, row["candidate_id"], updated["interviewer_id"],
                               updated["scheduled_start"], updated["duration_minutes"], interview_id)
        assignments = [f"{key}=?" for key in values]
        params = [updated[key] for key in values]
        if "status" in values and updated["status"] == "cancelled":
            assignments.append("cancelled_at=?")
            params.append(now)
        if "status" in values and updated["status"] == "completed":
            assignments.append("completed_at=?")
            params.append(now)
        assignments.append("updated_at=?")
        params.extend([now, interview_id])
        conn.execute(f"UPDATE interviews SET {','.join(assignments)} WHERE id=?", tuple(params))
        ledger.append(conn, user["id"], "INTERVIEW_UPDATED", row["case_id"], interview_id,
                      {"changed_fields": sorted(values), "status": updated["status"]})
        return _interview(conn.execute("SELECT * FROM interviews WHERE id=?", (interview_id,)).fetchone())


def create_task(user: dict, body) -> dict:
    require_case_write(user, body.case_id, roles=("recruiter",))
    return _insert_task(user, body.model_dump(), origin="manual")


def _validate_task_links(conn, case_id: str, values: dict) -> None:
    candidate_id = values.get("candidate_id")
    interview_id = values.get("interview_id")
    proposal_id = values.get("proposal_id")
    assignee_id = values.get("assigned_to")
    if candidate_id:
        candidate = conn.execute("SELECT case_id FROM candidates WHERE id=?", (candidate_id,)).fetchone()
        if not candidate or candidate["case_id"] != case_id:
            raise not_found("Candidate")
    if interview_id:
        interview = conn.execute("SELECT case_id,candidate_id FROM interviews WHERE id=?", (interview_id,)).fetchone()
        if not interview or interview["case_id"] != case_id:
            raise not_found("Interview")
        if candidate_id and interview["candidate_id"] != candidate_id:
            raise invalid("The linked interview belongs to a different candidate.")
    if proposal_id:
        proposal = conn.execute("SELECT case_id,candidate_id FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        if not proposal or proposal["case_id"] != case_id:
            raise not_found("Proposal")
        if candidate_id and proposal["candidate_id"] != candidate_id:
            raise invalid("The linked proposal belongs to a different candidate.")
    if assignee_id and conn.execute(
        "SELECT 1 FROM case_members WHERE case_id=? AND user_id=?", (case_id, assignee_id)
    ).fetchone() is None:
        raise invalid("The assignee must be a member of this case.")


def _insert_task(user: dict, values: dict, *, origin: str, dedupe_key: str | None = None) -> dict:
    task_id = db.new_id("TASK")
    now = db.now()
    with db.tx() as conn:
        if dedupe_key:
            existing = conn.execute("SELECT * FROM follow_up_tasks WHERE dedupe_key=?", (dedupe_key,)).fetchone()
            if existing:
                if existing["case_id"] != values["case_id"]:
                    raise conflict("TASK_DEDUPE_CONFLICT", "This workflow key is already associated with another case.")
                return _task(existing)
        _validate_task_links(conn, values["case_id"], values)
        conn.execute(
            "INSERT INTO follow_up_tasks(id,case_id,title,description,task_type,candidate_id,interview_id,"
            "proposal_id,assigned_to,due_at,priority,status,origin,dedupe_key,created_by,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,'open',?,?,?,?,?)",
            (task_id, values["case_id"], values["title"], values.get("description", ""),
             values.get("task_type", "follow_up"), values.get("candidate_id"), values.get("interview_id"),
             values.get("proposal_id"), values.get("assigned_to"), values.get("due_at"), values.get("priority", "normal"),
             origin, dedupe_key, user["id"], now, now),
        )
        ledger.append(conn, user["id"], "FOLLOW_UP_CREATED", values["case_id"], task_id,
                      {"task_type": values.get("task_type", "follow_up"), "candidate_id": values.get("candidate_id"),
                       "origin": origin})
        return _task(conn.execute("SELECT * FROM follow_up_tasks WHERE id=?", (task_id,)).fetchone())


def ensure_workflow_task(user: dict, *, case_id: str, dedupe_key: str, title: str, task_type: str,
                         candidate_id: str | None = None, interview_id: str | None = None,
                         proposal_id: str | None = None, assigned_to: str | None = None,
                         due_at: str | None = None, priority: str = "normal") -> dict:
    """Create one workflow follow-up for an event; repeated events return the original task."""
    values = {"case_id": case_id, "title": title, "task_type": task_type, "candidate_id": candidate_id,
              "interview_id": interview_id, "proposal_id": proposal_id, "assigned_to": assigned_to,
              "due_at": due_at, "priority": priority}
    return _insert_task(user, values, origin="workflow", dedupe_key=dedupe_key)


def list_tasks(user: dict, *, case_id: str | None = None, candidate_id: str | None = None,
               assigned_to: str | None = None, status: str | None = None, priority: str | None = None,
               bucket: str | None = None, limit: int = 50, offset: int = 0) -> dict:
    if limit < 1 or limit > 100 or offset < 0:
        raise invalid("limit must be 1..100, offset >= 0.")
    if status not in (None, "open", "in_progress", "completed"):
        raise invalid("Unsupported task status.")
    if priority not in (None, "low", "normal", "high", "urgent"):
        raise invalid("Unsupported task priority.")
    if bucket not in (None, "today", "upcoming", "overdue", "completed"):
        raise invalid("Unsupported task bucket.")
    if case_id is not None:
        require_case_read(user, case_id)
        case_ids = [case_id]
    elif user["role"] in READ_ALL_ROLES:
        case_ids = [row["id"] for row in db.q("SELECT id FROM cases ORDER BY id")]
    else:
        case_ids = [row["case_id"] for row in db.q(
            "SELECT case_id FROM case_members WHERE user_id=? ORDER BY case_id", (user["id"],))]
    if not case_ids:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}
    where = ["t.case_id IN (" + ",".join("?" for _ in case_ids) + ")"]
    args: list = list(case_ids)
    for field, value in (("candidate_id", candidate_id), ("assigned_to", assigned_to),
                         ("status", status), ("priority", priority)):
        if value is not None:
            where.append(f"t.{field}=?")
            args.append(value)
    today = db.utcnow().date().isoformat()
    if bucket == "today":
        where.extend(["t.status!='completed'", "t.due_at>=?", "t.due_at<?"])
        args.extend([today + "T00:00:00Z", (db.utcnow().date() + timedelta(days=1)).isoformat() + "T00:00:00Z"])
    elif bucket == "upcoming":
        where.extend(["t.status!='completed'", "t.due_at>=?"])
        args.append(db.now())
    elif bucket == "overdue":
        where.extend(["t.status!='completed'", "t.due_at IS NOT NULL", "t.due_at<?"])
        args.append(db.now())
    elif bucket == "completed":
        where.append("t.status='completed'")
    where_sql = " AND ".join(where)
    total = db.one(f"SELECT COUNT(*) n FROM follow_up_tasks t WHERE {where_sql}", tuple(args))["n"]
    rows = db.q(
        f"SELECT t.*,c.pseudonym candidate_pseudonym,cs.title case_title,u.name assignee_name "
        f"FROM follow_up_tasks t LEFT JOIN candidates c ON c.id=t.candidate_id "
        f"JOIN cases cs ON cs.id=t.case_id LEFT JOIN users u ON u.id=t.assigned_to "
        f"WHERE {where_sql} ORDER BY "
        "CASE WHEN t.status='completed' THEN 1 ELSE 0 END,t.due_at IS NULL,t.due_at,t.id LIMIT ? OFFSET ?",
        (*args, limit, offset),
    )
    return {"items": [_task(row) for row in rows], "total": total, "limit": limit, "offset": offset}


def get_task(user: dict, task_id: str) -> dict:
    row = db.one(
        "SELECT t.*,c.pseudonym candidate_pseudonym,cs.title case_title,u.name assignee_name "
        "FROM follow_up_tasks t LEFT JOIN candidates c ON c.id=t.candidate_id "
        "JOIN cases cs ON cs.id=t.case_id LEFT JOIN users u ON u.id=t.assigned_to WHERE t.id=?",
        (task_id,))
    if not row:
        raise not_found("Follow-up task")
    require_case_read(user, row["case_id"])
    return _task(row)


def update_task(user: dict, task_id: str, values: dict) -> dict:
    if not values:
        raise invalid("Set at least one task field.")
    row = db.one("SELECT * FROM follow_up_tasks WHERE id=?", (task_id,))
    if not row:
        raise not_found("Follow-up task")
    require_case_write(user, row["case_id"], roles=("recruiter", "hiring_manager"))
    unknown = set(values) - set(_TASK_FIELDS)
    if unknown:
        raise invalid("Unknown task field.")
    if user["role"] == "hiring_manager":
        if row["assigned_to"] != user["id"] or set(values) != {"status"}:
            raise invalid("An assignee may only update the status of their own task.")
    updated = dict(row)
    updated.update(values)
    if updated["title"] is None or updated["priority"] is None or updated["task_type"] is None or updated["status"] is None:
        raise invalid("Required task fields cannot be null.")
    if updated["description"] is None:
        raise invalid("Task description cannot be null.")
    with db.tx() as conn:
        _validate_task_links(conn, row["case_id"], updated)
        now = db.now()
        assignments = [f"{key}=?" for key in values]
        params = [values[key] for key in values]
        if values.get("status") == "completed":
            assignments.append("completed_at=?")
            params.append(now)
        elif values.get("status") in ("open", "in_progress"):
            assignments.append("completed_at=NULL")
        assignments.append("updated_at=?")
        params.extend([now, task_id])
        conn.execute(f"UPDATE follow_up_tasks SET {','.join(assignments)} WHERE id=?", tuple(params))
        ledger.append(conn, user["id"], "FOLLOW_UP_UPDATED", row["case_id"], task_id,
                      {"changed_fields": sorted(values), "status": updated["status"]})
        return _task(conn.execute("SELECT * FROM follow_up_tasks WHERE id=?", (task_id,)).fetchone())
