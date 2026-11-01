"""Role-scoped read projections for the dashboard workspace."""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime

from . import cases, config, db
from .canonical import canonical
from .errors import conflict, invalid, not_found
from .security import READ_ALL_ROLES, require_case_read


def _case_ids(user: dict) -> list[str]:
    if user["role"] in READ_ALL_ROLES:
        return [row["id"] for row in db.q("SELECT id FROM cases ORDER BY id")]
    return [row["case_id"] for row in db.q(
        "SELECT case_id FROM case_members WHERE user_id=? ORDER BY case_id", (user["id"],))]


def _scope_case(user: dict, case_id: str | None) -> list[str]:
    if case_id is not None:
        require_case_read(user, case_id)
        return [case_id]
    return _case_ids(user)


def candidate_table(user: dict, *, case_id: str | None, search: str, finding_type: str | None,
                    shortlisted: bool | None, sort: str, order: str, limit: int, offset: int) -> dict:
    if len(search) > 100:
        raise invalid("search must be at most 100 characters.")
    if finding_type is not None and (len(finding_type) > 64 or not finding_type.strip()):
        raise invalid("finding_type must be a non-empty value of at most 64 characters.")
    if sort not in {"created_at", "pseudonym", "finding_count", "score"} or order not in {"asc", "desc"}:
        raise invalid("Unsupported candidate sort.")
    case_ids = _scope_case(user, case_id)
    if not case_ids:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    marks = ",".join("?" for _ in case_ids)
    where = [f"c.case_id IN ({marks})"]
    args: list = list(case_ids)
    if search:
        where.append("(instr(lower(c.pseudonym),lower(?))>0 OR instr(lower(c.id),lower(?))>0)")
        args.extend((search, search))
    if finding_type:
        where.append("EXISTS (SELECT 1 FROM documents fd JOIN findings ff ON ff.document_id=fd.id "
                     "WHERE fd.candidate_id=c.id AND ff.type=?)")
        args.append(finding_type)
    if shortlisted is not None:
        exists = "EXISTS" if shortlisted else "NOT EXISTS"
        where.append(f"{exists} (SELECT 1 FROM shortlisted_candidates sc JOIN rankings sr "
                     "ON sr.case_id=sc.case_id AND sr.version=sc.ranking_version "
                     "WHERE sc.case_id=c.case_id AND sc.candidate_id=c.id AND sr.status='CONFIRMED')")
    where_sql = " AND ".join(where)
    total = db.one(f"SELECT COUNT(*) n FROM candidates c WHERE {where_sql}", tuple(args))["n"]
    sort_sql = {
        "created_at": "c.created_at",
        "pseudonym": "c.pseudonym",
        "finding_count": "(SELECT COUNT(*) FROM findings f JOIN documents d ON d.id=f.document_id "
                         "WHERE d.candidate_id=c.id AND f.type!='MODEL_FALLBACK')",
        "score": "COALESCE((SELECT CAST(json_extract(j.value,'$.score') AS INTEGER) FROM rankings r "
                 "JOIN json_each(r.payload_json) j WHERE r.case_id=c.case_id "
                 "AND json_extract(j.value,'$.candidate_id')=c.id "
                 "AND r.status IN ('DRAFT','CONFIRMED') "
                 "ORDER BY r.version DESC LIMIT 1),0)",
    }[sort]
    rows = db.q(
        f"SELECT c.id,c.case_id,c.pseudonym,c.created_at,cs.title case_title,"
        f"(SELECT id FROM documents d WHERE d.candidate_id=c.id ORDER BY d.created_at DESC LIMIT 1) document_id,"
        f"(SELECT COUNT(*) FROM findings f JOIN documents d ON d.id=f.document_id "
        f"WHERE d.candidate_id=c.id AND f.type!='MODEL_FALLBACK') finding_count "
        f"FROM candidates c JOIN cases cs ON cs.id=c.case_id WHERE {where_sql} "
        f"ORDER BY {sort_sql} {order.upper()},c.id LIMIT ? OFFSET ?", (*args, limit, offset))

    items = []
    for row in rows:
        item = dict(row)
        item["finding_types"] = [f["type"] for f in db.q(
            "SELECT DISTINCT f.type FROM findings f JOIN documents d ON d.id=f.document_id "
            "WHERE d.candidate_id=? AND f.type!='MODEL_FALLBACK' ORDER BY f.type", (row["id"],))]
        shortlisted_row = db.one(
            "SELECT 1 FROM shortlisted_candidates s JOIN rankings r "
            "ON r.case_id=s.case_id AND r.version=s.ranking_version "
            "WHERE s.case_id=? AND s.candidate_id=? AND r.status='CONFIRMED' LIMIT 1",
            (row["case_id"], row["id"]))
        item["shortlisted"] = shortlisted_row is not None
        if item["shortlisted"]:
            private = db.one("SELECT display_name FROM candidates WHERE id=?", (row["id"],))
            item["display_name"] = private["display_name"]
        ranking = db.one(
            "SELECT payload_json FROM rankings WHERE case_id=? AND status IN ('DRAFT','CONFIRMED') "
            "ORDER BY version DESC LIMIT 1", (row["case_id"],))
        rank = next((entry for entry in db.loads(ranking["payload_json"], [])
                     if entry.get("candidate_id") == row["id"]), None) if ranking else None
        item["score"] = rank["score"] if rank else None
        item["position"] = rank["position"] if rank else None
        items.append(item)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def compare_candidates(user: dict, candidate_ids: list[str]) -> dict:
    if not 2 <= len(candidate_ids) <= 4 or len(set(candidate_ids)) != len(candidate_ids):
        raise invalid("Compare between two and four unique candidate_ids.")
    placeholders = ",".join("?" for _ in candidate_ids)
    rows = db.q(f"SELECT id,case_id,pseudonym FROM candidates WHERE id IN ({placeholders})", tuple(candidate_ids))
    if len(rows) != len(candidate_ids):
        raise not_found("Candidate")
    by_id = {row["id"]: row for row in rows}
    case_ids = {row["case_id"] for row in rows}
    for case_id in case_ids:
        require_case_read(user, case_id)
    if len(case_ids) != 1:
        raise invalid("Candidates must belong to the same case.")
    case_id = next(iter(case_ids))
    candidates = []
    for candidate_id in candidate_ids:
        row = by_id[candidate_id]
        dossier = cases.dossier(user, row["id"])
        ranking = db.one(
            "SELECT payload_json FROM rankings WHERE case_id=? AND status IN ('DRAFT','CONFIRMED') "
            "ORDER BY version DESC LIMIT 1", (case_id,))
        rank = next((entry for entry in db.loads(ranking["payload_json"], [])
                     if entry.get("candidate_id") == row["id"]), None) if ranking else None
        candidates.append({"id": row["id"], "pseudonym": row["pseudonym"],
                           "score": rank["score"] if rank else None,
                           "position": rank["position"] if rank else None,
                           "evidence": dossier["evidence"], "findings": dossier["findings"]})
    return {"case_id": case_id, "candidates": candidates}


def case_analytics(user: dict, case_id: str) -> dict:
    require_case_read(user, case_id)
    case = db.one("SELECT created_at FROM cases WHERE id=?", (case_id,))
    counts = {
        "candidates": db.one("SELECT COUNT(*) n FROM candidates WHERE case_id=?", (case_id,))["n"],
        "documents": db.one("SELECT COUNT(*) n FROM documents WHERE case_id=?", (case_id,))["n"],
        "shortlisted": db.one(
            "SELECT COUNT(DISTINCT s.candidate_id) n FROM shortlisted_candidates s JOIN rankings r "
            "ON r.case_id=s.case_id AND r.version=s.ranking_version "
            "WHERE s.case_id=? AND r.status='CONFIRMED'", (case_id,))["n"],
        "proposals": db.one("SELECT COUNT(*) n FROM proposals WHERE case_id=?", (case_id,))["n"],
        "outbox": db.one("SELECT COUNT(*) n FROM outbox WHERE case_id=?", (case_id,))["n"],
    }
    ranking = db.one("SELECT MIN(confirmed_at) confirmed_at FROM rankings WHERE case_id=? AND status='CONFIRMED'",
                     (case_id,))
    seconds = None
    if ranking and ranking["confirmed_at"]:
        start = datetime.fromisoformat(case["created_at"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(ranking["confirmed_at"].replace("Z", "+00:00"))
        seconds = max(0, int((end - start).total_seconds()))
    findings = db.q(
        "SELECT f.type,COUNT(*) count,MAX(CASE f.severity WHEN 'critical' THEN 4 WHEN 'high' THEN 3 "
        "WHEN 'medium' THEN 2 ELSE 1 END) severity_rank FROM findings f JOIN documents d ON d.id=f.document_id "
        "WHERE d.case_id=? AND f.type!='MODEL_FALLBACK' GROUP BY f.type ORDER BY f.type", (case_id,))
    return {"case_id": case_id,
            "funnel": [{"stage": stage, "count": counts[key]} for stage, key in
                       (("Candidates", "candidates"), ("CVs uploaded", "documents"),
                        ("Shortlisted", "shortlisted"), ("Actions drafted", "proposals"),
                        ("Outbox", "outbox"))],
            "time_to_shortlist_seconds": seconds,
            "findings_by_type": [{"type": row["type"], "count": row["count"]} for row in findings]}


def outbox_view(user: dict, case_id: str | None, limit: int, offset: int) -> dict:
    case_ids = _scope_case(user, case_id)
    if not case_ids:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}
    marks = ",".join("?" for _ in case_ids)
    total = db.one(f"SELECT COUNT(*) n FROM outbox WHERE case_id IN ({marks})", tuple(case_ids))["n"]
    rows = db.q(
        f"SELECT o.id,o.case_id,o.proposal_id,o.delivery_status,o.created_at,p.kind,p.payload_sha256,"
        f"c.pseudonym,cs.title case_title FROM outbox o JOIN proposals p ON p.id=o.proposal_id "
        f"JOIN candidates c ON c.id=p.candidate_id JOIN cases cs ON cs.id=o.case_id "
        f"WHERE o.case_id IN ({marks}) ORDER BY o.created_at DESC,o.id LIMIT ? OFFSET ?",
        (*case_ids, limit, offset))
    return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}


def audit_ledger(user: dict, case_id: str | None, limit: int, offset: int) -> dict:
    case_ids = _scope_case(user, case_id)
    if case_ids:
        marks = ",".join("?" for _ in case_ids)
        where = f"case_id IN ({marks})"
        args: tuple = tuple(case_ids)
    else:
        where, args = "0=1", ()
    if user["role"] in READ_ALL_ROLES and case_id is None:
        where, args = "1=1", ()
    total = db.one(f"SELECT COUNT(*) n FROM ledger WHERE {where}", args)["n"]
    rows = db.q(f"SELECT seq,ts,actor,type,case_id,subject,body_json,prev_hash,hash,mac "
                f"FROM ledger WHERE {where} ORDER BY seq DESC LIMIT ? OFFSET ?", (*args, limit, offset))
    head = db.one("SELECT hash FROM ledger ORDER BY seq DESC LIMIT 1")
    return {"events": [{"seq": row["seq"], "ts": row["ts"], "actor": row["actor"], "type": row["type"],
                        "case_id": row["case_id"], "subject": row["subject"],
                        "body": db.loads(row["body_json"], {}), "prev_hash": row["prev_hash"],
                        "hash": row["hash"], "mac": row["mac"]} for row in rows],
            "total": total, "limit": limit, "offset": offset,
            "head_hash": head["hash"] if head else "0" * 64,
            "complete_chain_visible": user["role"] in READ_ALL_ROLES and case_id is None}


def signed_audit_export(user: dict) -> dict:
    case_ids = _case_ids(user)
    complete = user["role"] in READ_ALL_ROLES
    if complete:
        rows = db.q("SELECT seq,ts,actor,type,case_id,subject,body_json,prev_hash,hash,mac FROM ledger ORDER BY seq")
    elif case_ids:
        marks = ",".join("?" for _ in case_ids)
        rows = db.q(f"SELECT seq,ts,actor,type,case_id,subject,body_json,prev_hash,hash,mac FROM ledger "
                    f"WHERE case_id IN ({marks}) ORDER BY seq", tuple(case_ids))
    else:
        rows = []
    payload = {"generated_at": db.now(), "scope": "all" if complete else "accessible_cases",
               "case_ids": case_ids, "complete_chain": complete,
               "events": [{"seq": row["seq"], "ts": row["ts"], "actor": row["actor"], "type": row["type"],
                           "case_id": row["case_id"], "subject": row["subject"],
                           "body": db.loads(row["body_json"], {}), "prev_hash": row["prev_hash"],
                           "hash": row["hash"], "mac": row["mac"]} for row in rows]}
    signature = hmac.new(config.LEDGER_KEY.encode("utf-8"), canonical(payload).encode("utf-8"),
                         hashlib.sha256).hexdigest()
    return {**payload, "signature_algorithm": "HMAC-SHA256", "signature": signature}


def list_users() -> list[dict]:
    return [dict(row) for row in db.q("SELECT id,email,name,role FROM users ORDER BY name,id")]


def create_user(actor: dict, body) -> dict:
    user_id = db.new_id("USER")
    with db.tx() as conn:
        if conn.execute("SELECT 1 FROM users WHERE lower(email)=?", (body.email.lower(),)).fetchone():
            raise conflict("EMAIL_EXISTS", "A user with this email already exists.")
        from .security import hash_password
        conn.execute("INSERT INTO users VALUES (?,?,?,?,?)",
                     (user_id, body.email.lower(), body.name, body.role, hash_password(body.password)))
        from .ledger import append
        append(conn, actor["id"], "USER_CREATED", None, user_id, {"role": body.role})
    return {"id": user_id, "email": body.email.lower(), "name": body.name, "role": body.role}


def change_user_role(actor: dict, user_id: str, role: str) -> dict:
    with db.tx() as conn:
        row = conn.execute("SELECT id,email,name,role FROM users WHERE id=?", (user_id,)).fetchone()
        if not row:
            raise not_found("User")
        if row["role"] == "hr_admin" and role != "hr_admin":
            admin_count = conn.execute("SELECT COUNT(*) n FROM users WHERE role='hr_admin'").fetchone()["n"]
            if admin_count <= 1:
                raise conflict("LAST_ADMIN", "The last HR administrator cannot be demoted.")
        conn.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
        from .ledger import append
        append(conn, actor["id"], "USER_ROLE_CHANGED", None, user_id,
               {"old_role": row["role"], "new_role": role})
    return {"id": row["id"], "email": row["email"], "name": row["name"], "role": role}
