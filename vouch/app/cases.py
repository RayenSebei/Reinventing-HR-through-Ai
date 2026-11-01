"""Cases, criteria, candidates (CV upload), dossiers and rankings."""
from __future__ import annotations

from pathlib import Path

from . import config, db, documents, evidence, ledger, pii, ranking
from .canonical import canonical, sha256_hex
from .errors import conflict, forbidden, invalid, not_found
from .security import READ_ALL_ROLES, require_case_read, require_case_write, require_role


# --- cases ------------------------------------------------------------------
def create_case(user: dict, body) -> dict:
    require_role(user, "recruiter")
    if body.manager_id:
        m = db.one("SELECT role FROM users WHERE id=?", (body.manager_id,))
        if not m or m["role"] != "hiring_manager":
            raise invalid("manager_id must be a hiring manager.")
    cid = db.new_id("CASE")
    with db.tx() as conn:
        conn.execute("INSERT INTO cases (id,title,description,owner_id,created_at) VALUES (?,?,?,?,?)",
                     (cid, body.title, body.description, user["id"], db.now()))
        conn.execute("INSERT INTO case_members VALUES (?,?)", (cid, user["id"]))
        if body.manager_id:
            conn.execute("INSERT INTO case_members VALUES (?,?)", (cid, body.manager_id))
        ledger.append(conn, user["id"], "CASE_CREATED", cid, cid, {"manager_id": body.manager_id})
    return get_case(user, cid)


def list_cases(user: dict, limit: int, offset: int) -> list[dict]:
    if user["role"] in READ_ALL_ROLES:
        rows = db.q("SELECT id FROM cases ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset))
    else:
        rows = db.q("SELECT c.id FROM cases c JOIN case_members m ON m.case_id=c.id WHERE m.user_id=? "
                    "ORDER BY c.created_at DESC LIMIT ? OFFSET ?", (user["id"], limit, offset))
    return [get_case(user, r["id"]) for r in rows]


def _criteria(case_id: str) -> list[dict]:
    return [{"id": r["id"], "label": r["label"], "kind": r["kind"], "weight": r["weight"],
             "aliases": db.loads(r["aliases_json"], [])}
            for r in db.q("SELECT * FROM criteria WHERE case_id=? ORDER BY position", (case_id,))]


def get_case(user: dict, case_id: str) -> dict:
    c = require_case_read(user, case_id)
    members = [dict(r) for r in db.q("SELECT u.id, u.name, u.role FROM users u JOIN case_members m ON m.user_id=u.id WHERE m.case_id=?", (case_id,))]
    return {"id": c["id"], "title": c["title"], "description": c["description"], "owner_id": c["owner_id"],
            "status": c["status"], "created_at": c["created_at"], "criteria": _criteria(case_id),
            "criteria_confirmed": bool(c["criteria_confirmed_at"]), "criteria_confirmed_by": c["criteria_confirmed_by"],
            "members": members, "can_edit": user["role"] == "recruiter" and any(m["id"] == user["id"] for m in members)}


def set_criteria(user: dict, case_id: str, body) -> dict:
    require_case_write(user, case_id)
    with db.tx() as conn:
        evidence_count = conn.execute(
            "SELECT COUNT(*) FROM evidence_items e JOIN candidates c ON c.id=e.candidate_id WHERE c.case_id=?",
            (case_id,)).fetchone()[0]
        if evidence_count:
            raise conflict("CRITERIA_LOCKED", "Criteria cannot change after candidate evidence exists.")
        conn.execute("DELETE FROM criteria WHERE case_id=?", (case_id,))
        for i, c in enumerate(body.criteria):
            conn.execute("INSERT INTO criteria VALUES (?,?,?,?,?,?,?)",
                         (db.new_id("CRIT"), case_id, c.label, c.kind, c.weight, canonical(c.aliases), i))
        conn.execute("UPDATE cases SET criteria_confirmed_by=NULL, criteria_confirmed_at=NULL WHERE id=?", (case_id,))
        ledger.append(conn, user["id"], "CRITERIA_SET", case_id, case_id,
                      {"criteria": [{"label": c.label, "kind": c.kind, "weight": c.weight} for c in body.criteria]})
    return get_case(user, case_id)


def confirm_criteria(user: dict, case_id: str) -> dict:
    require_case_write(user, case_id)
    if not _criteria(case_id):
        raise conflict("NO_CRITERIA", "Add job criteria first.")
    with db.tx() as conn:
        conn.execute("UPDATE cases SET criteria_confirmed_by=?, criteria_confirmed_at=? WHERE id=?", (user["id"], db.now(), case_id))
        ledger.append(conn, user["id"], "CRITERIA_CONFIRMED", case_id, case_id, {})
    return get_case(user, case_id)


# --- candidates & documents --------------------------------------------------
def _store_evidence(conn, cand_id: str, items: list[dict]) -> None:
    conn.execute("DELETE FROM evidence_items WHERE candidate_id=?", (cand_id,))
    for e in items:
        conn.execute("INSERT INTO evidence_items VALUES (?,?,?,?,?,?,?,?,?)",
                     (db.new_id("EV"), cand_id, e["criterion_id"], e["status"], e.get("quote"), e.get("page"),
                      e["source"], e.get("note", ""), db.dumps(e.get("boxes", []))))


def _store_findings(conn, doc_id: str, findings: list[dict]) -> None:
    for f in findings:
        conn.execute("INSERT INTO findings VALUES (?,?,?,?,?,?,?)",
                     (db.new_id("FND"), doc_id, f["type"], f["severity"], f["page"], f["excerpt"], db.dumps(f["boxes"])))


def upload_cv(user: dict, case_id: str, filename: str, data: bytes) -> dict:
    case = require_case_write(user, case_id)
    if not case["criteria_confirmed_at"]:
        raise conflict("CRITERIA_NOT_CONFIRMED", "Confirm the job criteria before uploading CVs.")
    sha = sha256_hex(data)
    duplicate = db.one("SELECT candidate_id FROM documents WHERE case_id=? AND sha256=?", (case_id, sha))
    if duplicate:
        raise conflict("DUPLICATE_DOCUMENT", "This CV has already been uploaded to this case.",
                       candidate_id=duplicate["candidate_id"])
    analysis = documents.analyse_pdf(data)
    findings = documents.find_findings(analysis)
    vis = documents.visible_text(analysis)
    contact = documents.contacts(vis)
    crit = _criteria(case_id)
    criteria_ids = [criterion["id"] for criterion in crit]
    items, extra = evidence.build(crit, analysis, findings, sha)
    findings += extra

    safe_name = Path(filename or "cv.pdf").name[:120]
    with db.tx() as conn:
        live_case = conn.execute("SELECT criteria_confirmed_at FROM cases WHERE id=?", (case_id,)).fetchone()
        if not live_case or not live_case["criteria_confirmed_at"]:
            raise conflict("CRITERIA_NOT_CONFIRMED", "Confirm the job criteria before uploading CVs.")
        live_criteria = [row["id"] for row in conn.execute(
            "SELECT id FROM criteria WHERE case_id=? ORDER BY position", (case_id,)).fetchall()]
        if live_criteria != criteria_ids:
            raise conflict("CRITERIA_CHANGED", "Criteria changed while this CV was being analysed; retry the upload.")
        duplicate = conn.execute("SELECT candidate_id FROM documents WHERE case_id=? AND sha256=?",
                                 (case_id, sha)).fetchone()
        if duplicate:
            raise conflict("DUPLICATE_DOCUMENT", "This CV has already been uploaded to this case.",
                           candidate_id=duplicate["candidate_id"])
        n = conn.execute("SELECT COUNT(*) FROM candidates WHERE case_id=?", (case_id,)).fetchone()[0] + 1
        cand_id, doc_id = db.new_id("CAND"), db.new_id("DOC")
        pseudonym = f"Candidate {n:03d}"
        display = documents.guess_name(vis) or pseudonym
        email = contact["emails"][0] if contact["emails"] else f"{cand_id.lower()}@candidates.example.invalid"
        path = config.ORIGINALS_DIR / f"{sha}.pdf"
        if not path.exists():
            path.write_bytes(data)
            path.chmod(0o444)
        conn.execute("INSERT INTO candidates VALUES (?,?,?,?,?,?)", (cand_id, case_id, pseudonym, display, email, db.now()))
        conn.execute("INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (doc_id, cand_id, case_id, sha, safe_name, str(path), len(analysis["pages"]), user["id"],
                      db.dumps(analysis), "ANALYSED", db.now()))
        _store_findings(conn, doc_id, findings)
        _store_evidence(conn, cand_id, items)
        ledger.append(conn, user["id"], "DOCUMENT_UPLOADED", case_id, doc_id,
                      {"sha256": sha, "candidate_id": cand_id, "pages": len(analysis["pages"])})
        ledger.append(conn, "system", "DOCUMENT_ANALYSED", case_id, doc_id,
                      {"findings": sorted({f["type"] for f in findings})})
        ledger.append(conn, "system", "EVIDENCE_GENERATED", case_id, cand_id,
                      {"statuses": sorted(e["status"] for e in items), "sources": sorted({e["source"] for e in items})})
    return dossier(user, cand_id)


def _cand(user: dict, cand_id: str):
    c = db.one("SELECT * FROM candidates WHERE id=?", (cand_id,))
    if not c:
        raise not_found("Candidate")
    require_case_read(user, c["case_id"])
    return c


def list_candidates(user: dict, case_id: str, limit: int, offset: int) -> list[dict]:
    require_case_read(user, case_id)
    out = []
    for c in db.q("SELECT * FROM candidates WHERE case_id=? ORDER BY created_at LIMIT ? OFFSET ?", (case_id, limit, offset)):
        doc = db.one("SELECT id, filename FROM documents WHERE candidate_id=?", (c["id"],))
        f = db.q("SELECT type FROM findings WHERE document_id=?", (doc["id"],)) if doc else []
        candidate = {"id": c["id"], "pseudonym": c["pseudonym"],
                     "document_id": doc["id"] if doc else None,
                     "finding_types": sorted({r["type"] for r in f})}
        if _is_shortlisted(case_id, c["id"]):
            candidate["display_name"] = c["display_name"]
            candidate["filename"] = doc["filename"] if doc else None
        out.append(candidate)
    return out


def _is_shortlisted(case_id: str, cand_id: str) -> bool:
    return db.one(
        "SELECT 1 FROM shortlisted_candidates s JOIN rankings r "
        "ON r.case_id=s.case_id AND r.version=s.ranking_version "
        "WHERE s.case_id=? AND s.candidate_id=? AND r.status='CONFIRMED' "
        "ORDER BY s.ranking_version DESC LIMIT 1", (case_id, cand_id)) is not None


def get_candidate(user: dict, cand_id: str) -> dict:
    c = _cand(user, cand_id)
    candidate = {"id": c["id"], "case_id": c["case_id"], "pseudonym": c["pseudonym"]}
    if _is_shortlisted(c["case_id"], cand_id):
        candidate["display_name"] = c["display_name"]
    return candidate


def dossier(user: dict, cand_id: str) -> dict:
    """Allow-listed fields only: no contact details, no protected traits."""
    c = _cand(user, cand_id)
    doc = db.one("SELECT * FROM documents WHERE candidate_id=?", (cand_id,))
    crit = {x["id"]: x for x in _criteria(c["case_id"])}
    ev = []
    for e in db.q("SELECT * FROM evidence_items WHERE candidate_id=?", (cand_id,)):
        cr = crit.get(e["criterion_id"])
        if not cr:
            continue
        ev.append({"criterion_id": e["criterion_id"], "criterion": cr["label"], "kind": cr["kind"], "weight": cr["weight"],
                   "status": e["status"], "quote": e["quote"], "page": e["page"], "source": e["source"],
                   "note": e["note"], "boxes": db.loads(e["boxes_json"], [])})
    findings = [{"type": f["type"], "severity": f["severity"], "page": f["page"],
                 "excerpt": pii.redact(f["excerpt"]), "boxes": db.loads(f["boxes_json"], [])}
                for f in db.q("SELECT * FROM findings WHERE document_id=?", (doc["id"],))] if doc else []
    return {"candidate_id": c["id"], "case_id": c["case_id"], "pseudonym": c["pseudonym"],
            "document": ({"id": doc["id"], "sha256": doc["sha256"], "pages": doc["pages"], "filename": doc["filename"]} if doc else None),
            "evidence": ev, "findings": findings,
            "statement": "Evidence statuses: SOURCED = quoted from the CV (a candidate claim, not independently verified); "
                         "NEEDS_REVIEW = needs a human look; NOT_FOUND = no evidence found in the CV."}


def _erase_candidate(cand_id: str, actor: str, reason: str) -> None:
    with db.tx() as conn:
        candidate = conn.execute("SELECT * FROM candidates WHERE id=?", (cand_id,)).fetchone()
        if not candidate:
            raise not_found("Candidate")
        docs = conn.execute("SELECT * FROM documents WHERE candidate_id=?", (cand_id,)).fetchall()
        for doc in docs:
            shared = conn.execute("SELECT 1 FROM documents WHERE path=? AND id!=? LIMIT 1",
                                  (doc["path"], doc["id"])).fetchone()
            path = Path(doc["path"]).resolve()
            if not shared and path.parent == config.ORIGINALS_DIR.resolve() and path.exists():
                path.chmod(0o600)
                path.unlink()
            conn.execute("DELETE FROM findings WHERE document_id=?", (doc["id"],))
        conn.execute("DELETE FROM evidence_items WHERE candidate_id=?", (cand_id,))
        proposal_ids = [r["id"] for r in conn.execute("SELECT id FROM proposals WHERE candidate_id=?", (cand_id,))]
        for proposal_id in proposal_ids:
            conn.execute("DELETE FROM approvals WHERE proposal_id=?", (proposal_id,))
            conn.execute("DELETE FROM outbox WHERE proposal_id=?", (proposal_id,))
        conn.execute("DELETE FROM proposals WHERE candidate_id=?", (cand_id,))
        conn.execute("DELETE FROM shortlisted_candidates WHERE candidate_id=?", (cand_id,))
        conn.execute("DELETE FROM documents WHERE candidate_id=?", (cand_id,))
        conn.execute("DELETE FROM candidates WHERE id=?", (cand_id,))
        ledger.append(conn, actor, "DOCUMENT_ERASED", candidate["case_id"], cand_id,
                      {"document_hashes": sorted(doc["sha256"] for doc in docs), "reason": reason})


def delete_candidate(user: dict, cand_id: str) -> dict:
    candidate = _cand(user, cand_id)
    if user["role"] == "recruiter":
        require_case_write(user, candidate["case_id"])
    elif user["role"] == "hr_admin":
        require_case_read(user, candidate["case_id"])
    else:
        raise forbidden("FORBIDDEN_ROLE", "Candidate erasure needs the recruiter or hr_admin role.")
    _erase_candidate(cand_id, user["id"], "requested")
    return {"deleted": True, "candidate_id": cand_id}


def regenerate_dossier(user: dict, cand_id: str) -> dict:
    c = _cand(user, cand_id)
    require_case_write(user, c["case_id"])
    doc = db.one("SELECT * FROM documents WHERE candidate_id=?", (cand_id,))
    analysis = db.loads(doc["analysis_json"])
    base = documents.find_findings(analysis)
    items, extra = evidence.build(_criteria(c["case_id"]), analysis, base, doc["sha256"])
    with db.tx() as conn:
        _store_evidence(conn, cand_id, items)
        conn.execute("DELETE FROM findings WHERE document_id=? AND type IN ('UNSUPPORTED_CLAIM','MODEL_FALLBACK')", (doc["id"],))
        _store_findings(conn, doc["id"], extra)
        ledger.append(conn, user["id"], "EVIDENCE_GENERATED", c["case_id"], cand_id,
                      {"statuses": sorted(e["status"] for e in items)})
    return dossier(user, cand_id)


def _doc(user: dict, doc_id: str):
    d = db.one("SELECT * FROM documents WHERE id=?", (doc_id,))
    if not d:
        raise not_found("Document")
    require_case_read(user, d["case_id"])
    return d


def extraction(user: dict, doc_id: str) -> dict:
    d = _doc(user, doc_id)
    a = db.loads(d["analysis_json"])
    visible = documents.visible_text(a)
    hidden = documents.hidden_text(a)
    if user["role"] != "recruiter":          # same rule as page_png: only recruiters see contact details
        visible, hidden = pii.redact(visible), pii.redact(hidden)
    return {"document_id": d["id"], "sha256": d["sha256"], "visible_text": visible,
            "hidden_text": hidden,
            "pages": [{"number": p["number"], "width": p["width"], "height": p["height"]} for p in a["pages"]]}


def document_findings(user: dict, doc_id: str) -> list[dict]:
    d = _doc(user, doc_id)
    return [{"type": f["type"], "severity": f["severity"], "page": f["page"], "excerpt": pii.redact(f["excerpt"]),
             "boxes": db.loads(f["boxes_json"], [])} for f in db.q("SELECT * FROM findings WHERE document_id=?", (d["id"],))]


def page_png(user: dict, doc_id: str, page: int) -> bytes:
    d = _doc(user, doc_id)
    analysis = db.loads(d["analysis_json"])
    redactions = documents.pii_boxes(analysis) if user["role"] != "recruiter" else None
    return documents.render_page_png(Path(d["path"]).read_bytes(), page, redact_boxes=redactions)


# --- ranking ----------------------------------------------------------------
def draft_ranking(user: dict, case_id: str) -> dict:
    require_case_write(user, case_id)
    crit = _criteria(case_id)
    cands = []
    for c in db.q("SELECT * FROM candidates WHERE case_id=? ORDER BY created_at", (case_id,)):
        ev = [dict(e) for e in db.q("SELECT criterion_id, status FROM evidence_items WHERE candidate_id=?", (c["id"],))]
        doc = db.one("SELECT id FROM documents WHERE candidate_id=?", (c["id"],))
        nf = db.one("SELECT COUNT(*) AS n FROM findings WHERE document_id=? AND type NOT IN ('MODEL_FALLBACK')", (doc["id"],))["n"] if doc else 0
        cands.append({"id": c["id"], "pseudonym": c["pseudonym"], "evidence": ev, "finding_count": nf})
    if not cands:
        raise conflict("NO_CANDIDATES", "Upload at least one CV first.")
    rows = ranking.rank(crit, cands)
    v = (db.one("SELECT MAX(version) AS v FROM rankings WHERE case_id=?", (case_id,))["v"] or 0) + 1
    rid = db.new_id("RANK")
    with db.tx() as conn:
        conn.execute("INSERT INTO rankings VALUES (?,?,?,?,?,?,?,?,?)",
                     (rid, case_id, v, "DRAFT", db.dumps(rows), user["id"], None, None, db.now()))
        ledger.append(conn, "system", "RANKING_DRAFTED", case_id, rid, {"version": v, "candidates": len(rows)})
    return get_ranking(user, case_id)


def confirm_ranking(user: dict, case_id: str, version: int) -> dict:
    require_case_write(user, case_id)
    r = db.one("SELECT * FROM rankings WHERE case_id=? AND version=?", (case_id, version))
    if not r:
        raise not_found("Ranking")
    if r["status"] != "DRAFT":
        raise conflict("NOT_A_DRAFT", "Only a draft ranking can be confirmed.")
    with db.tx() as conn:
        conn.execute("UPDATE rankings SET status='SUPERSEDED' WHERE case_id=? AND status='CONFIRMED'", (case_id,))
        conn.execute("UPDATE rankings SET status='CONFIRMED', confirmed_by=?, confirmed_at=? WHERE id=?", (user["id"], db.now(), r["id"]))
        ledger.append(conn, user["id"], "SHORTLIST_CONFIRMED", case_id, r["id"], {"version": version})
    return get_ranking(user, case_id)


def shortlist(user: dict, case_id: str, version: int, body) -> dict:
    require_case_write(user, case_id)
    with db.tx() as conn:
        row = conn.execute("SELECT * FROM rankings WHERE case_id=? AND version=?", (case_id, version)).fetchone()
        if not row:
            raise not_found("Ranking")
        if row["status"] != "DRAFT":
            raise conflict("NOT_A_DRAFT", "Only a draft ranking can be shortlisted.")
        ranked_ids = {item["candidate_id"] for item in db.loads(row["payload_json"], [])}
        requested = set(body.candidate_ids)
        if not requested.issubset(ranked_ids):
            raise invalid("candidate_ids must be selected from this ranking.")
        conn.execute("UPDATE rankings SET status='SUPERSEDED' WHERE case_id=? AND status='CONFIRMED'", (case_id,))
        conn.execute("UPDATE rankings SET status='CONFIRMED', confirmed_by=?, confirmed_at=? WHERE id=?",
                     (user["id"], db.now(), row["id"]))
        conn.execute("DELETE FROM shortlisted_candidates WHERE case_id=? AND ranking_version=?", (case_id, version))
        conn.executemany("INSERT INTO shortlisted_candidates VALUES (?,?,?)",
                         [(case_id, version, candidate_id) for candidate_id in sorted(requested)])
        ledger.append(conn, user["id"], "SHORTLIST_CONFIRMED", case_id, row["id"],
                      {"version": version, "candidate_ids": sorted(requested)})
    return get_ranking(user, case_id)


def get_ranking(user: dict, case_id: str) -> dict:
    require_case_read(user, case_id)
    r = db.one("SELECT * FROM rankings WHERE case_id=? AND status IN ('DRAFT','CONFIRMED') ORDER BY version DESC LIMIT 1", (case_id,))
    if not r:
        return {"case_id": case_id, "version": None, "status": None, "rows": []}
    return {"case_id": case_id, "version": r["version"], "status": r["status"], "confirmed_by": r["confirmed_by"],
            "rows": db.loads(r["payload_json"]),
            "statement": "Ranking is an aid for the recruiter, not a decision. Nobody is rejected automatically."}
