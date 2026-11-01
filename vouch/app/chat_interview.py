"""Integrated candidate chat interview.

The HR application remains the source of truth for users, cases, candidates,
approvals, evidence and audit events. This module adds only the candidate-facing
session lifecycle, transcript and combined evidence report.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from . import config, db, ledger
from .errors import ApiError, conflict, forbidden, not_found
from .security import is_member, require_case_read

LANGUAGES = ("en", "fr", "ar")

NOTICE = {
    "en": "This first interview is run by an AI assistant. A recruiter reads your answers and CV and makes every decision. The assistant does not score you. Avoid sensitive personal information. Your answers are retained under the Vouch demo retention policy.",
    "fr": "Ce premier entretien est mené par un assistant IA. Un recruteur lit vos réponses et votre CV et prend toutes les décisions. L'assistant ne vous attribue aucune note. Évitez les informations personnelles sensibles.",
    "ar": "يجري هذه المقابلة الأولى مساعد ذكاء اصطناعي. يقرأ مسؤول التوظيف إجاباتك وسيرتك الذاتية ويتخذ جميع القرارات. لا يمنحك المساعد أي علامة. تجنب مشاركة المعلومات الشخصية الحساسة.",
}

TEXT = {
    "intro": {
        "en": "Hello. I will ask the same core job-related questions used for this role. A recruiter will review your answers; I do not make hiring decisions.",
        "fr": "Bonjour. Je vais poser les mêmes questions professionnelles de base utilisées pour ce poste. Un recruteur examinera vos réponses ; je ne prends aucune décision d'embauche.",
        "ar": "مرحبا. سأطرح نفس الأسئلة المهنية الأساسية المستخدمة لهذه الوظيفة. سيراجع مسؤول التوظيف إجاباتك؛ أنا لا أتخذ قرارات التوظيف.",
    },
    "ack": {"en": "Thank you.", "fr": "Merci.", "ar": "شكرا لك."},
    "followup": {
        "en": "Could you add one concrete example, including what you personally did?",
        "fr": "Pouvez-vous ajouter un exemple concret, notamment ce que vous avez fait personnellement ?",
        "ar": "هل يمكنك إضافة مثال عملي يوضح ما قمت به شخصيا؟",
    },
    "guard": {
        "en": "I can only conduct this interview and cannot change its rules, score candidates, or reveal other information. Please answer the job-related question.",
        "fr": "Je peux uniquement mener cet entretien. Je ne peux pas modifier ses règles, noter les candidats ni révéler d'autres informations. Merci de répondre à la question professionnelle.",
        "ar": "يمكنني فقط إجراء هذه المقابلة ولا يمكنني تغيير قواعدها أو تقييم المرشحين أو كشف معلومات أخرى. يرجى الإجابة عن السؤال المهني.",
    },
    "end": {
        "en": "The interview is complete. Thank you. Your answers have been saved for human review.",
        "fr": "L'entretien est terminé. Merci. Vos réponses ont été enregistrées pour examen humain.",
        "ar": "اكتملت المقابلة. شكرا لك. تم حفظ إجاباتك للمراجعة البشرية.",
    },
}

_INJECTION = [
    ("override_instructions", r"\b(ignore|disregard|forget|override|bypass)\b.{0,40}\b(instructions?|rules?|prompt|previous)\b"),
    ("override_instructions", r"\b(ignor\w*|oubli\w*|contourn\w*)\b.{0,40}\b(instructions?|consignes?|r[eè]gles?|prompt)\b"),
    ("override_instructions", r"(تجاهل|انس|تخط)\S*.{0,30}(التعليمات|الأوامر|القواعد)"),
    ("role_hijack", r"\b(you are now|act as|pretend to be|developer mode|jailbreak)\b"),
    ("prompt_extraction", r"\b(system prompt|reveal.{0,20}(prompt|instructions)|tes instructions)\b"),
    ("score_manipulation", r"\b(score|rate|rank|grade|note|classe)\b.{0,35}\b(me|moi|candidate|candidat|10|100|best|top)\b"),
    ("data_exfiltration", r"\b(other candidates?|autres candidats|database|api key|password|transcripts?)\b"),
    ("markup_injection", r"(<\s*/?\s*(system|assistant|instructions?|user)\s*>|\[/?inst\]|<\|im_start\|>)"),
]
_INJECTION_RX = [(name, re.compile(pattern, re.I | re.S)) for name, pattern in _INJECTION]
_rate_hits: dict[str, deque[float]] = defaultdict(deque)
_rate_lock = threading.Lock()


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _language(session) -> str:
    return session["language"] if session["language"] in LANGUAGES else "en"


def _scan(text: str) -> list[str]:
    normalized = " ".join(text.split())
    return sorted({name for name, regex in _INJECTION_RX if regex.search(normalized)})


def _localized_question(label: str) -> dict[str, str]:
    return {
        "en": f"Tell us about your experience with {label}. What was your contribution?",
        "fr": f"Parlez-nous de votre expérience avec {label}. Quelle a été votre contribution ?",
        "ar": f"حدثنا عن خبرتك في {label}. ما هي مساهمتك؟",
    }


def _gap_question(label: str) -> dict[str, str]:
    return {
        "en": f"Your CV did not show clear evidence for {label}. Is there relevant experience you would like to explain?",
        "fr": f"Votre CV ne montrait pas de preuve claire pour {label}. Souhaitez-vous expliquer une expérience pertinente ?",
        "ar": f"لم تظهر سيرتك الذاتية دليلا واضحا على {label}. هل تود شرح خبرة ذات صلة؟",
    }


def build_plan(candidate_id: str) -> list[dict]:
    candidate = db.one("SELECT case_id FROM candidates WHERE id=?", (candidate_id,))
    if not candidate:
        raise not_found("Candidate")
    criteria = db.q("SELECT id,label FROM criteria WHERE case_id=? ORDER BY rowid", (candidate["case_id"],))
    plan = [{"id": row["id"], "criterion_id": row["id"], "kind": "core",
             "text": _localized_question(row["label"]), "followup_done": False} for row in criteria[:8]]
    missing = db.q(
        "SELECT e.criterion_id,c.label FROM evidence_items e JOIN criteria c ON c.id=e.criterion_id "
        "WHERE e.candidate_id=? AND e.status='NOT_FOUND' ORDER BY c.rowid LIMIT 2", (candidate_id,))
    for row in missing:
        plan.append({"id": f"gap:{row['criterion_id']}", "criterion_id": row["criterion_id"], "kind": "gap",
                     "text": _gap_question(row["label"]), "followup_done": False})
    if not plan:
        plan.append({"id": "motivation", "criterion_id": None, "kind": "core", "followup_done": False,
                     "text": {"en": "What interests you about this role, and what relevant experience would you bring?",
                              "fr": "Qu'est-ce qui vous intéresse dans ce poste et quelle expérience pertinente apporteriez-vous ?",
                              "ar": "ما الذي يثير اهتمامك في هذه الوظيفة وما الخبرة ذات الصلة التي ستقدمها؟"}})
    return plan


def pending_credentials() -> tuple[str, str]:
    """Return a new session ID and raw one-time token."""
    return db.new_id("CHAT"), secrets.token_urlsafe(32)


def store_pending_session(conn, case_id: str, candidate_id: str, proposal_id: str,
                          session_id: str, token: str, time_limit_minutes: int) -> None:
    """Create a disabled session after its proposal row exists.

    The proposal contains the candidate link so the approver sees its exact
    message. Only a hash is stored in the session table; the session is unusable
    until the approved proposal is executed.
    """
    expires = (db.utcnow() + timedelta(hours=config.INTERVIEW_INVITE_HOURS)).replace(microsecond=0)
    conn.execute(
        "INSERT INTO chat_interview_sessions (id,case_id,candidate_id,proposal_id,token_hash,expires_at,time_limit_minutes,state,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (session_id, case_id, candidate_id, proposal_id, _token_hash(token),
         expires.isoformat().replace("+00:00", "Z"), time_limit_minutes, "pending_approval", db.now()),
    )


def activate_session(conn, proposal_id: str) -> str | None:
    row = conn.execute("SELECT id FROM chat_interview_sessions WHERE proposal_id=?", (proposal_id,)).fetchone()
    if not row:
        return None
    conn.execute("UPDATE chat_interview_sessions SET state='invited' WHERE id=? AND state='pending_approval'", (row["id"],))
    return row["id"]


def revoke_pending_session(conn, proposal_id: str) -> None:
    conn.execute("UPDATE chat_interview_sessions SET state='revoked' WHERE proposal_id=? AND state='pending_approval'",
                 (proposal_id,))


def _session_for_token(token: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,100}", token or ""):
        raise not_found("Interview")
    token_hash = _token_hash(token)
    now = time.monotonic()
    with _rate_lock:
        hits = _rate_hits[token_hash]
        while hits and now - hits[0] > 60:
            hits.popleft()
        if len(hits) >= config.INTERVIEW_RATE_PER_MINUTE:
            raise ApiError(429, "INTERVIEW_RATE_LIMIT", "Too many interview requests. Wait a minute and retry.")
        hits.append(now)
    session = db.one("SELECT * FROM chat_interview_sessions WHERE token_hash=?", (token_hash,))
    if not session or session["state"] in ("pending_approval", "revoked"):
        raise not_found("Interview")
    if session["state"] == "invited" and _parse(session["expires_at"]) <= db.utcnow():
        with db.tx() as conn:
            conn.execute("UPDATE chat_interview_sessions SET state='expired',ended_at=? WHERE id=?", (db.now(), session["id"]))
            ledger.append(conn, "candidate", "CHAT_INTERVIEW_EXPIRED", session["case_id"], session["id"], {})
        raise ApiError(410, "INTERVIEW_EXPIRED", "This interview link has expired. Contact the recruiter.")
    return db.one("SELECT * FROM chat_interview_sessions WHERE id=?", (session["id"],))


def _remaining(session) -> int | None:
    if not session["started_at"] or session["time_limit_minutes"] <= 0:
        return None
    deadline = _parse(session["started_at"]) + timedelta(minutes=session["time_limit_minutes"])
    return max(0, int((deadline - db.utcnow()).total_seconds()))


def _history(session_id: str) -> list[dict]:
    return [{"sender": row["sender"], "text": row["text"], "question_id": row["question_id"],
             "response_seconds": row["response_seconds"], "ts": row["created_at"]}
            for row in db.q("SELECT * FROM chat_interview_messages WHERE session_id=? ORDER BY rowid", (session_id,))]


def candidate_info(token: str) -> dict:
    session = _session_for_token(token)
    case = db.one("SELECT title FROM cases WHERE id=?", (session["case_id"],))
    remaining = _remaining(session)
    if session["state"] == "in_progress" and remaining == 0:
        _complete(session, "time_limit")
        session = db.one("SELECT * FROM chat_interview_sessions WHERE id=?", (session["id"],))
    return {"job_title": case["title"], "state": session["state"], "language": session["language"],
            "notice": NOTICE, "history": _history(session["id"]),
            "timer": {"limit_s": session["time_limit_minutes"] * 60, "remaining_s": _remaining(session)}}


def start(token: str, language: str, consent: bool) -> dict:
    session = _session_for_token(token)
    if not consent:
        raise ApiError(422, "CONSENT_REQUIRED", "Consent is required to start the interview.")
    if language not in LANGUAGES:
        raise ApiError(422, "LANGUAGE_INVALID", "Choose English, French, or Arabic.")
    if session["state"] != "invited":
        raise conflict("INTERVIEW_ALREADY_STARTED", "This interview has already been started.")
    plan = build_plan(session["candidate_id"])
    intro = TEXT["intro"][language]
    first = plan[0]["text"][language]
    with db.tx() as conn:
        now = db.now()
        changed = conn.execute(
            "UPDATE chat_interview_sessions SET language=?,consent_at=?,state='in_progress',plan_json=?,started_at=? "
            "WHERE id=? AND state='invited'", (language, now, db.dumps(plan), now, session["id"])).rowcount
        if changed != 1:
            raise conflict("INTERVIEW_ALREADY_STARTED", "This interview has already been started.")
        for question_id, text in ((None, intro), (plan[0]["id"], first)):
            conn.execute("INSERT INTO chat_interview_messages VALUES (?,?,?,?,?,?,?,?)",
                         (db.new_id("MSG"), session["id"], "assistant", question_id, text, "{}", None, db.now()))
        ledger.append(conn, "candidate", "CHAT_INTERVIEW_STARTED", session["case_id"], session["id"],
                      {"candidate_id": session["candidate_id"], "language": language, "consent": True})
    return {"history": _history(session["id"]),
            "timer": {"limit_s": session["time_limit_minutes"] * 60,
                      "remaining_s": session["time_limit_minutes"] * 60}}


def _complete(session, reason: str) -> None:
    fresh = db.one("SELECT * FROM chat_interview_sessions WHERE id=?", (session["id"],))
    if not fresh or fresh["state"] == "completed":
        return
    language = _language(fresh)
    with db.tx() as conn:
        conn.execute("INSERT INTO chat_interview_messages VALUES (?,?,?,?,?,?,?,?)",
                     (db.new_id("MSG"), fresh["id"], "assistant", None, TEXT["end"][language], "{}", None, db.now()))
        conn.execute("UPDATE chat_interview_sessions SET state='completed',ended_at=? WHERE id=?",
                     (db.now(), fresh["id"]))
        ledger.append(conn, "candidate", "CHAT_INTERVIEW_COMPLETED", fresh["case_id"], fresh["id"],
                      {"candidate_id": fresh["candidate_id"], "reason": reason})
    generate_report(fresh["candidate_id"], fresh["id"])


def answer(token: str, text: str) -> dict:
    session = _session_for_token(token)
    if session["state"] != "in_progress":
        raise conflict("INTERVIEW_NOT_ACTIVE", "This interview is not active.")
    text = text.strip()
    if not text or len(text) > config.INTERVIEW_MAX_ANSWER_CHARS:
        raise ApiError(422, "ANSWER_INVALID", f"Answers must be 1 to {config.INTERVIEW_MAX_ANSWER_CHARS} characters.")
    remaining = _remaining(session)
    if remaining == 0:
        deadline = _parse(session["started_at"]) + timedelta(minutes=session["time_limit_minutes"])
        if db.utcnow() > deadline + timedelta(seconds=30):
            _complete(session, "time_limit")
            raise ApiError(409, "INTERVIEW_TIME_LIMIT", "The server-side interview time limit has elapsed.")
    plan = db.loads(session["plan_json"], [])
    if session["q_index"] >= len(plan):
        _complete(session, "plan_complete")
        return {"assistant": [TEXT["end"][_language(session)]], "completed": True}
    entry = plan[session["q_index"]]
    flags = _scan(text)
    words = len(text.split())
    previous = db.one("SELECT created_at FROM chat_interview_messages WHERE session_id=? AND sender='assistant' "
                      "ORDER BY rowid DESC LIMIT 1", (session["id"],))
    seconds = max(0, int((db.utcnow() - _parse(previous["created_at"])).total_seconds())) if previous else 0
    language = _language(session)
    replies: list[str] = []
    completed = False
    with db.tx() as conn:
        current = conn.execute("SELECT q_index,state FROM chat_interview_sessions WHERE id=?", (session["id"],)).fetchone()
        if not current or current["state"] != "in_progress" or current["q_index"] != session["q_index"]:
            raise conflict("INTERVIEW_STATE_CHANGED", "The interview state changed; reload the page.")
        conn.execute("INSERT INTO chat_interview_messages VALUES (?,?,?,?,?,?,?,?)",
                     (db.new_id("MSG"), session["id"], "candidate", entry["id"], text,
                      db.dumps({"injection": flags, "short": words < 8}), seconds, db.now()))
        if flags:
            reply = TEXT["guard"][language] + "\n\n" + entry["text"][language]
            replies.append(reply)
            ledger.append(conn, "candidate", "CHAT_MANIPULATION_FLAGGED", session["case_id"], session["id"],
                          {"candidate_id": session["candidate_id"], "categories": flags})
        elif words < 8 and not entry["followup_done"]:
            entry["followup_done"] = True
            plan[session["q_index"]] = entry
            reply = TEXT["followup"][language]
            replies.append(reply)
            conn.execute("UPDATE chat_interview_sessions SET plan_json=? WHERE id=?", (db.dumps(plan), session["id"]))
        else:
            next_index = session["q_index"] + 1
            if next_index >= len(plan):
                reply = TEXT["end"][language]
                replies.append(reply)
                completed = True
                conn.execute("UPDATE chat_interview_sessions SET q_index=?,state='completed',ended_at=? WHERE id=?",
                             (next_index, db.now(), session["id"]))
                ledger.append(conn, "candidate", "CHAT_INTERVIEW_COMPLETED", session["case_id"], session["id"],
                              {"candidate_id": session["candidate_id"], "reason": "plan_complete"})
            else:
                reply = TEXT["ack"][language] + " " + plan[next_index]["text"][language]
                replies.append(reply)
                conn.execute("UPDATE chat_interview_sessions SET q_index=? WHERE id=?", (next_index, session["id"]))
        for reply in replies:
            question_id = None if completed else plan[min(session["q_index"] + (0 if flags or (words < 8 and entry["followup_done"]) else 1), len(plan)-1)]["id"]
            conn.execute("INSERT INTO chat_interview_messages VALUES (?,?,?,?,?,?,?,?)",
                         (db.new_id("MSG"), session["id"], "assistant", question_id, reply, "{}", None, db.now()))
    if completed:
        generate_report(session["candidate_id"], session["id"])
    return {"assistant": replies, "completed": completed}


def finish(token: str) -> dict:
    session = _session_for_token(token)
    if session["state"] == "in_progress":
        _complete(session, "candidate_ended")
    elif session["state"] != "completed":
        raise conflict("INTERVIEW_NOT_ACTIVE", "This interview is not active.")
    return {"completed": True, "history": _history(session["id"])}


def generate_report(candidate_id: str, session_id: str) -> dict:
    candidate = db.one("SELECT * FROM candidates WHERE id=?", (candidate_id,))
    criteria = db.q("SELECT id,label,weight FROM criteria WHERE case_id=? ORDER BY rowid", (candidate["case_id"],))
    transcript = _history(session_id)
    answers = [m for m in transcript if m["sender"] == "candidate"]
    evidence_rows = db.q("SELECT * FROM evidence_items WHERE candidate_id=?", (candidate_id,))
    by_criterion = {row["id"]: {"criterion_id": row["id"], "criterion": row["label"], "weight": row["weight"],
                                    "cv_evidence": [], "interview_evidence": []} for row in criteria}
    for row in evidence_rows:
        if row["criterion_id"] in by_criterion:
            by_criterion[row["criterion_id"]]["cv_evidence"].append(
                {"status": row["status"], "quote": row["quote"], "page": row["page"], "note": row["note"]})
    flags = []
    plan = db.loads(db.one("SELECT plan_json FROM chat_interview_sessions WHERE id=?", (session_id,))["plan_json"], [])
    criterion_for_question = {item["id"]: item.get("criterion_id") for item in plan}
    for message in db.q("SELECT * FROM chat_interview_messages WHERE session_id=? AND sender='candidate' ORDER BY rowid", (session_id,)):
        meta = db.loads(message["flags_json"], {})
        if meta.get("injection"):
            flags.append({"type": "manipulation_attempt", "question_id": message["question_id"],
                          "categories": meta["injection"]})
            continue
        criterion_id = criterion_for_question.get(message["question_id"])
        if criterion_id in by_criterion:
            by_criterion[criterion_id]["interview_evidence"].append(
                {"answer": message["text"], "response_seconds": message["response_seconds"],
                 "short_answer": bool(meta.get("short"))})
    report = {"candidate_id": candidate_id, "session_id": session_id,
              "statement": "AI organized candidate-provided evidence. A human must verify it and make the decision.",
              "requirements": list(by_criterion.values()), "review_flags": flags,
              "answered_questions": len(answers), "generated_at": db.now()}
    with db.tx() as conn:
        conn.execute("INSERT INTO chat_interview_reports VALUES (?,?,?,?,?)",
                     (db.new_id("REPORT"), candidate_id, session_id, db.dumps(report), db.now()))
        ledger.append(conn, "system", "CHAT_EVIDENCE_REPORT_GENERATED", candidate["case_id"], candidate_id,
                      {"session_id": session_id, "answered_questions": len(answers), "flags": len(flags)})
    return report


def staff_view(user: dict, candidate_id: str, *, mark_report_opened: bool = False) -> dict:
    candidate = db.one("SELECT * FROM candidates WHERE id=?", (candidate_id,))
    if not candidate:
        raise not_found("Candidate")
    require_case_read(user, candidate["case_id"])
    session = db.one("SELECT * FROM chat_interview_sessions WHERE candidate_id=? ORDER BY created_at DESC LIMIT 1",
                     (candidate_id,))
    report_row = db.one("SELECT report_json FROM chat_interview_reports WHERE candidate_id=? ORDER BY created_at DESC LIMIT 1",
                        (candidate_id,))
    if mark_report_opened and report_row:
        with db.tx() as conn:
            conn.execute("INSERT OR REPLACE INTO chat_report_views VALUES (?,?,?)", (user["id"], candidate_id, db.now()))
            ledger.append(conn, user["id"], "CHAT_EVIDENCE_REPORT_OPENED", candidate["case_id"], candidate_id, {})
    decisions = [dict(row) for row in db.q(
        "SELECT d.decision,d.reason,d.created_at,u.name decided_by_name FROM candidate_decisions d "
        "JOIN users u ON u.id=d.decided_by WHERE d.candidate_id=? ORDER BY d.created_at", (candidate_id,))]
    return {"session": ({"id": session["id"], "state": session["state"], "language": session["language"],
                         "expires_at": session["expires_at"], "started_at": session["started_at"],
                         "ended_at": session["ended_at"]} if session else None),
            "transcript": _history(session["id"]) if session else [],
            "report": db.loads(report_row["report_json"]) if report_row else None,
            "decisions": decisions}


def decide(user: dict, candidate_id: str, decision: str, reason: str) -> dict:
    candidate = db.one("SELECT * FROM candidates WHERE id=?", (candidate_id,))
    if not candidate:
        raise not_found("Candidate")
    require_case_read(user, candidate["case_id"])
    if user["role"] not in ("recruiter", "hiring_manager") or not is_member(user, candidate["case_id"]):
        raise forbidden("FORBIDDEN_ROLE", "Only a recruiter or hiring manager on this case can decide.")
    if not db.one("SELECT 1 FROM chat_report_views WHERE user_id=? AND candidate_id=?", (user["id"], candidate_id)):
        raise conflict("REPORT_NOT_OPENED", "Open the combined evidence report before recording a decision.")
    reason = reason.strip()
    if len(reason) < 15:
        raise ApiError(422, "REASON_REQUIRED", "Write a job-related reason of at least 15 characters.")
    decision_id = db.new_id("DEC")
    with db.tx() as conn:
        conn.execute("INSERT INTO candidate_decisions VALUES (?,?,?,?,?,?,?)",
                     (decision_id, candidate_id, candidate["case_id"], decision, reason, user["id"], db.now()))
        ledger.append(conn, user["id"], "HUMAN_CANDIDATE_DECISION", candidate["case_id"], candidate_id,
                      {"decision": decision, "reason_recorded": True, "human_authority": True})
    return {"id": decision_id, "candidate_id": candidate_id, "decision": decision, "reason": reason,
            "decided_by": user["id"]}
