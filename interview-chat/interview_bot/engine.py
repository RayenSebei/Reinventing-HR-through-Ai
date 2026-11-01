"""The interview engine.

The conversation follows a fixed plan (same core questions for every candidate
for a job, plus up to N questions on that candidate's CV gaps). The LLM is only
asked one narrow thing: "is one follow-up question useful, and what is it?".
Its output must pass the output guard, otherwise the plan simply continues.

So the interviewer cannot be talked into scoring, promising, revealing the plan
or reading other candidates: it has no access to any of that, and the only text
it can produce is a single follow-up question that our code re-checks.
"""
from . import db, guard, llm, prompts
from .config import settings

LANGS = ("en", "fr", "ar")

TEXT = {
    "intro": {
        "en": "Hello! I am an AI assistant running the first-round interview for the role \"{title}\". "
              "I will ask you about {n} questions about your experience. Answer in English, French or Arabic, "
              "whichever is easiest for you. A recruiter will read the whole conversation: I do not make any decision.",
        "fr": "Bonjour ! Je suis un assistant IA qui mène le premier entretien pour le poste « {title} ». "
              "Je vais vous poser environ {n} questions sur votre expérience. Répondez en français, en anglais "
              "ou en arabe, comme vous préférez. Un recruteur lira toute la conversation : je ne prends aucune décision.",
        "ar": "مرحبا! أنا مساعد ذكاء اصطناعي أجري المقابلة الأولى لوظيفة \"{title}\". "
              "سأطرح عليك حوالي {n} أسئلة عن خبرتك. يمكنك الإجابة بالعربية أو الفرنسية أو الإنجليزية. "
              "سيقرأ أحد المسؤولين عن التوظيف المحادثة كاملة: أنا لا أتخذ أي قرار.",
    },
    "ack": {"en": "Thank you.", "fr": "Merci.", "ar": "شكرا لك."},
    "injection_notice": {
        "en": "I can only run this interview and I cannot change how it works or share other information. Let's continue.",
        "fr": "Je peux seulement mener cet entretien ; je ne peux ni modifier son fonctionnement ni partager d'autres informations. Continuons.",
        "ar": "يمكنني فقط إجراء هذه المقابلة، ولا يمكنني تغيير طريقة عملها أو مشاركة معلومات أخرى. لنواصل.",
    },
    "followup_default": {
        "en": "Could you give one concrete example: what did you do yourself, which tools did you use, and what was the result?",
        "fr": "Pouvez-vous donner un exemple concret : qu'avez-vous fait vous-même, avec quels outils, et quel a été le résultat ?",
        "ar": "هل يمكنك إعطاء مثال ملموس: ماذا فعلت بنفسك، وما الأدوات التي استخدمتها، وما كانت النتيجة؟",
    },
    "gap_default": {
        "en": "Your CV does not mention {label}. Do you have any experience with it, even in studies or personal projects?",
        "fr": "Votre CV ne mentionne pas : {label}. Avez-vous une expérience à ce sujet, même en études ou en projet personnel ?",
        "ar": "سيرتك الذاتية لا تذكر: {label}. هل لديك أي خبرة في ذلك، حتى خلال الدراسة أو في مشاريع شخصية؟",
    },
    "closing": {
        "en": "Last question: do you have a question about the role or the process? A recruiter will answer it. (You can write \"no\".)",
        "fr": "Dernière question : avez-vous une question sur le poste ou le processus ? Un recruteur y répondra. (Vous pouvez écrire « non ».)",
        "ar": "سؤال أخير: هل لديك سؤال عن الوظيفة أو عن مراحل التوظيف؟ سيجيبك أحد المسؤولين. (يمكنك كتابة \"لا\".)",
    },
    "time_up": {
        "en": "The time for this interview is over.",
        "fr": "Le temps prévu pour cet entretien est écoulé.",
        "ar": "انتهى الوقت المخصص لهذه المقابلة.",
    },
    "end": {
        "en": "Thank you for your time. The interview is finished. A recruiter will review your answers and contact you. No decision is made automatically.",
        "fr": "Merci pour votre temps. L'entretien est terminé. Un recruteur examinera vos réponses et vous contactera. Aucune décision n'est prise automatiquement.",
        "ar": "شكرا على وقتك. انتهت المقابلة. سيراجع أحد المسؤولين إجاباتك ويتواصل معك. لا يتم اتخاذ أي قرار بشكل آلي.",
    },
}

SHORT_ANSWER_WORDS = 8
GRACE_S = 30          # an answer sent up to 30 s after the time limit is still accepted


def time_left(session: dict) -> int | None:
    """Seconds left, or None when there is no limit or the interview has not started."""
    limit = settings.interview_time_limit_min * 60
    if not limit or not session.get("started_at"):
        return None
    return max(0, int(session["started_at"] + limit - db.now()))


def timer(session: dict) -> dict:
    limit = settings.interview_time_limit_min * 60
    left = time_left(session)
    return {"limit_s": limit, "remaining_s": limit if left is None else left}


def expire_if_time_up(session: dict) -> bool:
    """Close an in-progress interview whose time (plus grace) is over. Returns True if closed."""
    limit = settings.interview_time_limit_min * 60
    if not limit or session.get("state") != "in_progress" or not session.get("started_at"):
        return False
    if db.now() <= session["started_at"] + limit + GRACE_S:
        return False
    lang = session.get("language") or "en"
    with db.tx() as conn:
        cur = conn.execute("UPDATE interview_sessions SET state='completed', ended_at=? WHERE id=? AND state='in_progress'",
                           (db.now(), session["id"]))
        if cur.rowcount:
            _insert_bot(conn, session["id"], None, t("time_up", lang) + " " + t("end", lang))
    return True


class EngineError(ValueError):
    pass


def t(key: str, lang: str, **kw) -> str:
    return TEXT[key].get(lang, TEXT[key]["en"]).format(**kw)


def _localized(value, lang: str) -> str:
    if isinstance(value, dict):
        return value.get(lang) or value.get("en") or next(iter(value.values()))
    return str(value)


def build_plan(job_spec: dict, gap_requirements: list) -> list:
    plan = []
    for q in job_spec["core_questions"]:
        plan.append({"id": q["id"], "kind": "core", "requirement_ids": q.get("requirement_ids", []),
                     "text": q["text"], "followup_done": False})
    template = job_spec.get("gap_question_template") or TEXT["gap_default"]
    covered = {rid for q in job_spec["core_questions"] for rid in q.get("requirement_ids", [])}
    max_gap = int(job_spec.get("max_gap_questions", 2))
    # Gap questions only for requirements the core questions do not already ask about.
    for i, req in enumerate([r for r in gap_requirements if r["id"] not in covered][:max_gap], start=1):
        labels = req.get("label_i18n", {})
        text = {lang: _localized(template, lang).format(label=labels.get(lang, req["label"])) for lang in LANGS}
        plan.append({"id": f"G{i}", "kind": "gap", "requirement_ids": [req["id"]], "text": text, "followup_done": False})
    plan.append({"id": "CLOSE", "kind": "closing", "requirement_ids": [], "text": TEXT["closing"], "followup_done": True})
    return plan


def _insert_bot(conn, session_id: int, qid, text: str):
    conn.execute("INSERT INTO messages (session_id, sender, question_id, text, flags_json, created_at) VALUES (?,?,?,?,?,?)",
                 (session_id, "bot", qid, text, None, db.now()))


def start(session: dict, job: dict, language: str) -> None:
    """Called once, after consent. Writes the intro and the first question."""
    if language not in LANGS:
        raise EngineError("Unsupported language")
    plan = db.loads(session["plan_json"])
    job_spec = db.loads(job["spec_json"])
    with db.tx() as conn:
        row = conn.execute("SELECT state FROM interview_sessions WHERE id = ?", (session["id"],)).fetchone()
        if row["state"] != "invited":
            raise EngineError("Interview already started")
        conn.execute("UPDATE interview_sessions SET state='in_progress', language=?, consent_at=?, started_at=? WHERE id=?",
                     (language, db.now(), db.now(), session["id"]))
        n = len([p for p in plan if p["kind"] != "closing"])
        _insert_bot(conn, session["id"], None, t("intro", language, title=job_spec.get("title", job["title"]), n=n))
        _insert_bot(conn, session["id"], plan[0]["id"], _localized(plan[0]["text"], language))


def _llm_followup(entry: dict, job_spec: dict, answer: str, lang: str) -> str | None:
    labels = [r["label"] for r in job_spec["requirements"] if r["id"] in entry["requirement_ids"]]
    question = _localized(entry["text"], lang)

    def mock():
        if len(answer.split()) < SHORT_ANSWER_WORDS * 2:
            return {"follow_up": True, "text": t("followup_default", lang)}
        return {"follow_up": False, "text": ""}

    out = llm.complete_json("followup", prompts.FOLLOWUP_SYSTEM,
                            prompts.followup_user(question, labels, answer, lang), mock=mock, max_tokens=200)
    if not out.get("follow_up"):
        return None
    text = str(out.get("text", "")).strip()
    # Output contract: one question, short, nothing forbidden. Otherwise use the safe default.
    if not text.endswith(("?", "؟")) or not guard.output_ok(text, max_chars=300) or text.count("?") > 2:
        return t("followup_default", lang)
    return text


def handle_answer(session_id: int, text: str) -> dict:
    """Store the candidate's answer and produce the next bot message(s).

    Returns {"bot": [texts], "completed": bool, "flagged": bool}.
    """
    text = (text or "").strip()
    if not text:
        raise EngineError("Empty answer")
    if len(text) > settings.max_answer_chars:
        raise EngineError(f"Answer too long (max {settings.max_answer_chars} characters)")

    session = db.one("SELECT * FROM interview_sessions WHERE id = ?", (session_id,))
    if session is None or session["state"] != "in_progress":
        raise EngineError("Interview is not in progress")
    count = db.one("SELECT COUNT(*) AS n FROM messages WHERE session_id=? AND sender='candidate'", (session_id,))["n"]
    if count >= settings.max_candidate_messages:
        raise EngineError("Message limit reached")

    if expire_if_time_up(session):
        # Too late (time limit + grace): the answer is not stored; the interview is closed.
        return {"bot": [t("time_up", session["language"] or "en") + " " + t("end", session["language"] or "en")],
                "completed": True, "flagged": False}

    plan = db.loads(session["plan_json"])
    q_index = session["q_index"]
    entry = plan[q_index]
    lang = session["language"] or "en"
    scan = guard.scan(text)
    flags = {"injection": scan["matches"]} if scan["injection"] else None
    short = len(text.split()) < SHORT_ANSWER_WORDS and entry["kind"] != "closing"

    last_bot = db.one("SELECT created_at FROM messages WHERE session_id=? AND sender='bot' ORDER BY id DESC LIMIT 1",
                      (session_id,))
    seconds = int(db.now() - last_bot["created_at"]) if last_bot else None   # time taken to answer
    with db.tx() as conn:
        conn.execute("INSERT INTO messages (session_id, sender, question_id, text, flags_json, created_at) VALUES (?,?,?,?,?,?)",
                     (session_id, "candidate", entry["id"], text,
                      db.dumps({**(flags or {}), "short": short, "seconds": seconds}), db.now()))

    # Time is up (answer sent within the grace period): keep the answer, close the interview.
    if time_left(session) == 0:
        msg = t("time_up", lang) + " " + t("end", lang)
        with db.tx() as conn:
            _insert_bot(conn, session_id, None, msg)
            conn.execute("UPDATE interview_sessions SET state='completed', ended_at=? WHERE id=? AND state='in_progress'",
                         (db.now(), session_id))
        return {"bot": [msg], "completed": True, "flagged": bool(flags)}

    # Decide follow-up outside the transaction (LLM call can be slow).
    followup = None
    if not flags and entry["kind"] != "closing" and not entry["followup_done"]:
        job = db.one("SELECT j.* FROM jobs j JOIN candidates c ON c.job_id=j.id WHERE c.id=?", (session["candidate_id"],))
        followup = _llm_followup(entry, db.loads(job["spec_json"]), text, lang)

    bot, completed = [], False
    with db.tx() as conn:
        current = conn.execute("SELECT q_index, state FROM interview_sessions WHERE id=?", (session_id,)).fetchone()
        if current["q_index"] != q_index or current["state"] != "in_progress":
            return {"bot": [], "completed": current["state"] == "completed", "flagged": bool(flags)}
        if flags:
            # Not treated as an answer: explain once and ask the same question again.
            again = t("injection_notice", lang) + "\n\n" + _localized(entry["text"], lang)
            bot.append(again)
            _insert_bot(conn, session_id, entry["id"], again)
        elif followup:
            plan[q_index]["followup_done"] = True
            bot.append(followup)
            conn.execute("UPDATE interview_sessions SET plan_json=?, followups_used=followups_used+1 WHERE id=?",
                         (db.dumps(plan), session_id))
            _insert_bot(conn, session_id, entry["id"], followup)
        else:
            nxt = q_index + 1
            if nxt >= len(plan):
                completed = True
                bot.append(t("end", lang))
                _insert_bot(conn, session_id, None, t("end", lang))
                conn.execute("UPDATE interview_sessions SET q_index=?, state='completed', ended_at=? WHERE id=?",
                             (nxt, db.now(), session_id))
            else:
                question = _localized(plan[nxt]["text"], lang)
                lead = "" if flags else t("ack", lang) + " "
                bot.append(lead + question)
                _insert_bot(conn, session_id, plan[nxt]["id"], lead + question)
                conn.execute("UPDATE interview_sessions SET q_index=? WHERE id=?", (nxt, session_id))
    return {"bot": bot, "completed": completed, "flagged": bool(flags)}


def finish_early(session_id: int) -> None:
    session = db.one("SELECT * FROM interview_sessions WHERE id = ?", (session_id,))
    if session is None or session["state"] != "in_progress":
        raise EngineError("Interview is not in progress")
    lang = session["language"] or "en"
    with db.tx() as conn:
        _insert_bot(conn, session_id, None, t("end", lang))
        conn.execute("UPDATE interview_sessions SET state='completed', ended_at=? WHERE id=?", (db.now(), session_id))


def history(session_id: int) -> list:
    rows = db.many("SELECT sender, text, created_at FROM messages WHERE session_id=? ORDER BY id", (session_id,))
    return [{"sender": r["sender"], "text": r["text"], "ts": r["created_at"]} for r in rows]


def candidate_lines(session_id: int) -> tuple[list, list, int]:
    """Candidate messages for evaluation (closing question excluded), flagged ones, short count."""
    rows = db.many("SELECT question_id, text, flags_json FROM messages WHERE session_id=? AND sender='candidate' ORDER BY id",
                   (session_id,))
    lines, flagged, short = [], [], 0
    for r in rows:
        flags = db.loads(r["flags_json"]) or {}
        if flags.get("injection"):
            # Shown to HR in the transcript, but never used as evidence.
            flagged.append({"question_id": r["question_id"], "text": r["text"], "matches": flags["injection"]})
            continue
        if flags.get("short"):
            short += 1
        if r["question_id"] != "CLOSE":
            lines.append({"question_id": r["question_id"], "text": r["text"]})
    return lines, flagged, short

