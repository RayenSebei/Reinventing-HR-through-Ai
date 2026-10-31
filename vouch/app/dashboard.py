"""Read-only dashboard projections. Every case-bound row uses the same scope as list_cases.

No CV text, recipient addresses, or raw proposal payloads are returned here.
Counts are aggregates over all permitted rows, independent of API page sizes.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from . import config, db
from .security import READ_ALL_ROLES, require_case_read

SEVERITY = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def effective_status(proposal, now: str) -> str:
    """Display state only. Execution decisions remain exclusively in the gateway."""
    if proposal["status"] == "EXECUTED":
        return "sent"
    if not proposal["approval_id"]:
        return "pending"
    if proposal["decision"] != "approved":
        return "rejected"
    if proposal["approved_hash"] != proposal["payload_sha256"]:
        return "changed"
    if proposal["used_at"]:
        return "used"
    expires = datetime.fromisoformat(proposal["expires_at"].replace("Z", "+00:00"))
    if expires <= datetime.fromisoformat(now.replace("Z", "+00:00")):
        return "expired"
    return "approved"


def assurance_summary() -> dict:
    path = config.REPO / "sentinel_hr" / "reports" / "latest.json"
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        totals = report["totals"]
        return {"available": True, "pass": totals["pass"], "total": totals["scenarios"],
                "fail": totals["fail"], "not_run": totals["blocked"] + totals["error"],
                "generated_at": report["generated_at"], "model_mode": report["target"]["model_mode"]}
    except (OSError, ValueError, KeyError, TypeError):
        # An absent or partially written report is unavailable, never a green result.
        return {"available": False}


def overview(user: dict, case_id: str | None = None) -> dict:
    if case_id is not None:
        require_case_read(user, case_id)
    read_all = user["role"] in READ_ALL_ROLES
    filters, args = [], []
    if not read_all:
        filters.append("EXISTS (SELECT 1 FROM case_members m WHERE m.case_id=c.id AND m.user_id=?)")
        args.append(user["id"])
    if case_id is not None:
        filters.append("c.id=?")
        args.append(case_id)
    where = " AND ".join(filters) if filters else "1=1"
    scope = f"WITH scoped AS (SELECT c.* FROM cases c WHERE {where}) "

    def query(sql):
        return db.q(scope + sql, tuple(args))

    def count(table, condition="1=1"):
        return query(f"SELECT COUNT(*) n FROM {table} t JOIN scoped s ON s.id=t.case_id WHERE {condition}")[0]["n"]

    now = db.now()
    case_rows = query("SELECT s.id,s.title,s.criteria_confirmed_at,"
                      "(SELECT COUNT(*) FROM candidates c WHERE c.case_id=s.id) candidate_count "
                      "FROM scoped s ORDER BY s.created_at DESC, s.id")
    proposals = query("SELECT p.id,p.case_id,p.kind,p.status,p.created_at,p.created_by,p.payload_sha256,"
                      "a.id approval_id,a.decision,a.payload_sha256 approved_hash,a.used_at,a.expires_at "
                      "FROM proposals p JOIN scoped s ON s.id=p.case_id LEFT JOIN approvals a ON a.rowid="
                      "(SELECT a2.rowid FROM approvals a2 WHERE a2.proposal_id=p.id "
                      "ORDER BY a2.created_at DESC,a2.rowid DESC LIMIT 1) ORDER BY p.created_at DESC,p.id")
    statuses = {key: 0 for key in ("pending", "approved", "sent", "changed", "expired", "rejected", "used")}
    states = {}
    for proposal in proposals:
        state = effective_status(proposal, now)
        statuses[state] += 1
        states[proposal["id"]] = state

    alerts = query("SELECT f.type,f.severity,COUNT(*) n FROM findings f JOIN documents d ON d.id=f.document_id "
                   "JOIN scoped s ON s.id=d.case_id WHERE f.type!='MODEL_FALLBACK' GROUP BY f.type,f.severity")
    by_type, by_severity = {}, {key: 0 for key in SEVERITY}
    for row in alerts:
        item = by_type.setdefault(row["type"], {"type": row["type"], "count": 0, "max_severity": "low"})
        item["count"] += row["n"]
        by_severity[row["severity"]] = by_severity.get(row["severity"], 0) + row["n"]
        if SEVERITY.get(row["severity"], 0) > SEVERITY[item["max_severity"]]:
            item["max_severity"] = row["severity"]

    # Global ledger events may only be seen by roles that can already read the global ledger.
    ledger_scope = "(l.case_id IN (SELECT id FROM scoped)" + (" OR l.case_id IS NULL)" if read_all and case_id is None else ")")
    ledger_counts = query(f"SELECT COUNT(*) n,COALESCE(SUM(l.type='EXECUTION_DENIED'),0) refusals "
                          f"FROM ledger l WHERE {ledger_scope}")[0]
    events = query("SELECT l.seq,l.ts,l.actor,l.type,l.case_id,l.subject,l.hash,l.prev_hash,"
                   "COALESCE(u.name,l.actor) actor_name,COALESCE(u.role,'system') actor_role "
                   f"FROM ledger l LEFT JOIN users u ON u.id=l.actor WHERE {ledger_scope} ORDER BY l.seq DESC LIMIT 8")
    rankings = query("SELECT r.case_id,r.status,r.payload_json FROM rankings r JOIN scoped s ON s.id=r.case_id "
                     "WHERE r.rowid=(SELECT r2.rowid FROM rankings r2 WHERE r2.case_id=r.case_id "
                     "AND r2.status IN ('DRAFT','CONFIRMED') ORDER BY r2.version DESC,r2.rowid DESC LIMIT 1)")
    latest_rankings = {r["case_id"]: r for r in rankings}
    confirmed = set()
    for row in rankings:
        if row["status"] == "CONFIRMED":
            confirmed.update(item["candidate_id"] for item in db.loads(row["payload_json"], []))

    attention = []
    titles = {row["id"]: row["title"] for row in case_rows}
    if user["role"] == "recruiter":
        for row in case_rows:
            rank = latest_rankings.get(row["id"])
            if not row["criteria_confirmed_at"]:
                attention.append({"id": row["id"], "case_id": row["id"], "kind": "criteria", "title": "Confirm hiring criteria", "case_title": row["title"]})
            elif row["candidate_count"] and (not rank or rank["status"] != "CONFIRMED"):
                attention.append({"id": row["id"], "case_id": row["id"], "kind": "shortlist", "title": "Review the shortlist", "case_title": row["title"]})
    for proposal in proposals:
        state = states[proposal["id"]]
        manager = user["role"] == "hiring_manager" and proposal["created_by"] != user["id"]
        if (manager and state in ("pending", "changed", "expired")) or (user["role"] == "recruiter" and state == "approved"):
            attention.append({"id": proposal["id"], "case_id": proposal["case_id"], "kind": "approval",
                              "title": "Review invitation" if manager else "Send approved invitation", "case_title": titles[proposal["case_id"]],
                              "state": state, "expires_at": proposal["expires_at"] if state == "approved" else None,
                              "created_at": proposal["created_at"]})
    if read_all:
        attention.append({"id": "verify-ledger", "kind": "verify", "title": "Verify the ledger chain"})

    uploaded = count("documents")
    analysed = count("documents", "t.status='ANALYSED'")
    sent = count("outbox")
    deliveries = query("SELECT o.delivery_status,COUNT(*) n FROM outbox o JOIN scoped s ON s.id=o.case_id GROUP BY o.delivery_status")
    trend_days = [(datetime.now(timezone.utc).date() - timedelta(days=day)).isoformat() for day in range(6, -1, -1)]
    trends = {key: {day: 0 for day in trend_days} for key in
              ("cvs_analysed", "security_alerts", "approval_activity", "gateway_sent")}
    for row in query("SELECT date(d.created_at) day,COUNT(*) n FROM documents d JOIN scoped s ON s.id=d.case_id "
                     "WHERE date(d.created_at)>=date('now','-6 day') AND d.status='ANALYSED' GROUP BY date(d.created_at)"):
        if row["day"] in trends["cvs_analysed"]:
            trends["cvs_analysed"][row["day"]] = row["n"]
    for row in query("SELECT date(d.created_at) day,COUNT(*) n FROM findings f JOIN documents d ON d.id=f.document_id "
                     "JOIN scoped s ON s.id=d.case_id WHERE date(d.created_at)>=date('now','-6 day') "
                     "AND f.type!='MODEL_FALLBACK' GROUP BY date(d.created_at)"):
        if row["day"] in trends["security_alerts"]:
            trends["security_alerts"][row["day"]] = row["n"]
    for row in query("SELECT date(l.ts) day,COUNT(*) n FROM ledger l WHERE "
                     f"{ledger_scope} AND l.type IN ('PROPOSAL_CREATED','APPROVED','REJECTED') "
                     "AND date(l.ts)>=date('now','-6 day') GROUP BY date(l.ts)"):
        if row["day"] in trends["approval_activity"]:
            trends["approval_activity"][row["day"]] = row["n"]
    for row in query("SELECT date(o.created_at) day,COUNT(*) n FROM outbox o JOIN scoped s ON s.id=o.case_id "
                     "WHERE date(o.created_at)>=date('now','-6 day') GROUP BY date(o.created_at)"):
        if row["day"] in trends["gateway_sent"]:
            trends["gateway_sent"][row["day"]] = row["n"]
    return {
        "generated_at": now, "scope": {"case_id": case_id, "all_accessible": case_id is None},
        "kpis": {"cases": len(case_rows), "cvs_analysed": analysed,
                 "security_alerts": sum(row["n"] for row in alerts), "pending_approval": statuses["pending"] + statuses["changed"] + statuses["expired"],
                 "gateway_sent": sent, "gateway_refusals": ledger_counts["refusals"], "ledger_events": ledger_counts["n"]},
        "pipeline": [{"stage": "Uploaded", "count": uploaded, "unit": "CVs"},
                     {"stage": "Analysed", "count": analysed, "unit": "CVs"},
                     {"stage": "Shortlisted", "count": len(confirmed), "unit": "candidates"},
                     {"stage": "Drafted", "count": len(proposals), "unit": "actions"},
                     {"stage": "Approved", "count": statuses["approved"], "unit": "valid now"},
                     {"stage": "Sent", "count": sent, "unit": "outbox entries"}],
        "alerts_by_type": sorted(by_type.values(), key=lambda row: (-row["count"], row["type"])),
        "alerts_by_severity": by_severity, "proposals_by_status": statuses,
        "delivery_by_status": {row["delivery_status"]: row["n"] for row in deliveries},
        "activity_trends": {key: [days[day] for day in trend_days] for key, days in trends.items()},
        "recent_events": [dict(row) for row in events], "attention": attention[:12], "attention_total": len(attention),
        "cases": [{"id": row["id"], "title": row["title"], "candidate_count": row["candidate_count"]} for row in case_rows],
        "assurance": assurance_summary(),
    }
