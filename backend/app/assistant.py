"""Ядро помощника.

Три правила (см. specs/):
1. Не выдумывать: нет уверенного ответа в базе знаний — вопрос уходит наставнику.
2. Не действовать молча: действие (отгул, доступ) сначала предлагается карточкой,
   выполняется только после подтверждения стажёра, параметры хранятся на сервере.
3. Показывать и сохранять результат: ответ сервиса попадает в чат и в историю.
"""
import json

from . import analytics, flags, intents, kb, llm, mcp_tools, onboarding
from .mcp_tools import ToolError
from .text import signature, stems

# Основа слова в вопросе -> действие, которое можно предложить в интерфейсе.
ACTION_HINTS = {
    "отгул": "leave_request",
    "досту": "access_status",
}

ESCALATION_MESSAGE = (
    "В базе знаний нет уверенного ответа, поэтому я не буду гадать. "
    "Передал вопрос наставнику, ответ появится здесь, как только он ответит."
)
ASK_DATES_MESSAGE = (
    "На какие даты оформить отгул? Напиши, например: «с 20 по 22 ноября» или «завтра»."
)


class ActionError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


# --- сообщения чата ---------------------------------------------------------------------

def _serialize(row):
    return {
        "id": row["id"],
        "role": row["role"],
        "kind": row["kind"],
        "text": row["text"],
        "payload": json.loads(row["payload"]) if row["payload"] else None,
        "created_at": row["created_at"],
    }


def save_message(db, user_id, role, text, kind="text", payload=None):
    cur = db.execute(
        "INSERT INTO messages (user_id, role, kind, text, payload) VALUES (?, ?, ?, ?, ?)",
        (user_id, role, kind, text,
         json.dumps(payload, ensure_ascii=False) if payload is not None else None),
    )
    return _serialize(db.execute("SELECT * FROM messages WHERE id = ?", (cur.lastrowid,)).fetchone())


def history(db, user_id, limit=200):
    rows = db.execute(
        "SELECT * FROM (SELECT * FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT ?) "
        "ORDER BY id",
        (user_id, limit),
    ).fetchall()
    return [_serialize(row) for row in rows]


def _reply(db, user, status, text, kind="text", payload=None, **extra):
    message = save_message(db, user["id"], "assistant", text, kind, payload)
    db.commit()
    result = {"status": status, "answer": text, "message": message}
    result.update(extra)
    return result


def _action_hint(text):
    found = stems(text)
    for stem, action in ACTION_HINTS.items():
        if stem in found:
            return action
    return None


# --- вопрос стажёра ----------------------------------------------------------------------

def ask(db, user, text, cfg):
    """Обработать сообщение. Возвращает словарь для JSON-ответа."""
    save_message(db, user["id"], "user", text)
    analytics.track(db, user["id"], "chat_question")

    if user["role"] == "intern" and flags.is_enabled(db, "chat_actions"):
        reply = _try_action(db, user, text)
        if reply is not None:
            return reply
    return _answer_from_kb(db, user, text, cfg)


def _try_action(db, user, text):
    intent = intents.detect(text, mcp_tools.today())
    kind = intent["intent"]

    if kind == "leave" and intent["wants_action"]:
        if intent["dates"] is None:
            return _reply(db, user, "needs_input", ASK_DATES_MESSAGE)
        start, end = intent["dates"]
        args = {"start_date": start.isoformat(), "end_date": end.isoformat(),
                "reason": intent["reason"]}
        return _propose(db, user, "create_leave_request", args)

    if kind == "access_request":
        return _propose(db, user, "request_access", {"system": intent["system"]})

    if kind == "access_status":
        result = mcp_tools.call_tool(db, user, "get_access_status", {})
        return _reply(db, user, "info", mcp_tools.describe_result("get_access_status", result),
                      kind="info", payload={"items": result["items"]})

    if kind == "next_step":
        data = onboarding.list_stages(db, user["id"])
        return _reply(
            db, user, "info", onboarding.describe_next_step(data), kind="info",
            payload={"next_step": data["next_step"], "progress_percent": data["progress_percent"]},
        )
    return None


def _propose(db, user, tool, args):
    try:
        prepared = mcp_tools.prepare_tool(db, user, tool, args)
    except ToolError as exc:
        return _reply(db, user, "rejected", exc.message)
    payload = {
        "tool": tool,
        "args": prepared["args"],
        "title": prepared["title"],
        "lines": prepared["lines"],
        "state": "pending",
    }
    analytics.track(db, user["id"], "action_proposed", {"tool": tool})
    return _reply(db, user, "proposal", "Проверь, всё ли верно, и подтверди.",
                  kind="proposal", payload=payload)


def _answer_from_kb(db, user, text, cfg):
    matches = kb.top_matches(db, text, user["role"], limit=3)
    entry, score = matches[0] if matches else (None, 0.0)

    answer, generated, use_rules = None, False, True
    if matches and llm.is_configured(cfg) and flags.is_enabled(db, "llm_answers"):
        try:
            llm_text = llm.answer_from_context(cfg, text, [row for row, _ in matches])
            use_rules = False
            answer, generated = llm_text, llm_text is not None
        except llm.LLMError:
            # Сбой LLM не должен ломать чат: отвечаем по базе знаний как обычно.
            analytics.track(db, user["id"], "llm_error")
    if use_rules and entry is not None and score >= cfg["KB_MIN_SCORE"]:
        answer = entry["answer"]

    if user["role"] != "intern":
        if answer is not None:
            return _reply(db, user, "answered", answer, kind="answer", score=round(score, 2))
        return _reply(db, user, "not_found", "В базе знаний ничего не нашлось.",
                      score=round(score, 2))

    sig = signature(text)
    if answer is not None:
        kb.mark_used(db, entry["id"])
        cur = db.execute(
            "INSERT INTO questions (intern_id, text, signature, status, answer, kb_entry_id, "
            "answered_at) VALUES (?, ?, ?, 'answered_auto', ?, ?, CURRENT_TIMESTAMP)",
            (user["id"], text, sig, answer, entry["id"]),
        )
        analytics.track(db, user["id"], "answered_auto", {"generated": generated})
        source = {"kb_entry_id": entry["id"], "origin": entry["source"]}
        hint = _action_hint(text)
        return _reply(
            db, user, "answered", answer, kind="answer",
            payload={"source": source, "generated": generated, "suggested_action": hint},
            question_id=cur.lastrowid, source=source, score=round(score, 2),
            suggested_action=hint,
        )

    cur = db.execute(
        "INSERT INTO questions (intern_id, text, signature, status) "
        "VALUES (?, ?, ?, 'pending')",
        (user["id"], text, sig),
    )
    analytics.track(db, user["id"], "escalated")
    return _reply(
        db, user, "escalated", ESCALATION_MESSAGE, kind="escalated",
        payload={"question_id": cur.lastrowid},
        question_id=cur.lastrowid, source=None, score=round(score, 2), suggested_action=None,
    )


# --- подтверждение действий ------------------------------------------------------------

def _update_payload(db, message_id, payload):
    db.execute(
        "UPDATE messages SET payload = ? WHERE id = ?",
        (json.dumps(payload, ensure_ascii=False), message_id),
    )
    return _serialize(db.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone())


def resolve_action(db, user, message_id, confirm):
    """Подтвердить или отменить карточку действия. Параметры берутся из сохранённой
    на сервере карточки, а не из запроса, поэтому подменить их нельзя."""
    row = db.execute(
        "SELECT * FROM messages WHERE id = ? AND user_id = ? AND kind = 'proposal'",
        (message_id, user["id"]),
    ).fetchone()
    if row is None:
        raise ActionError("Действие не найдено", 404)
    payload = json.loads(row["payload"])
    if payload["state"] != "pending":
        raise ActionError("Это действие уже обработано", 409)

    if not confirm:
        payload["state"] = "cancelled"
        proposal = _update_payload(db, message_id, payload)
        analytics.track(db, user["id"], "action_cancelled", {"tool": payload["tool"]})
        reply = save_message(db, user["id"], "assistant", "Хорошо, ничего не отправляю.")
        db.commit()
        return {"state": "cancelled", "proposal": proposal, "message": reply}

    try:
        result = mcp_tools.call_tool(db, user, payload["tool"], payload["args"])
    except ToolError as exc:
        payload["state"] = "failed"
        payload["error"] = exc.message
        proposal = _update_payload(db, message_id, payload)
        reply = save_message(db, user["id"], "assistant", f"Не получилось: {exc.message}")
        db.commit()
        return {"state": "failed", "error": exc.message, "proposal": proposal, "message": reply}

    payload["state"] = "done"
    payload["result"] = result
    proposal = _update_payload(db, message_id, payload)
    reply = save_message(
        db, user["id"], "assistant", mcp_tools.describe_result(payload["tool"], result),
        kind="result", payload={"tool": payload["tool"], "result": result},
    )
    analytics.track(db, user["id"], "action_confirmed", {"tool": payload["tool"]})
    db.commit()
    return {"state": "done", "result": result, "proposal": proposal, "message": reply}


# --- кабинет наставника ----------------------------------------------------------------

def pending_digest(db, mentor_id):
    """Неотвеченные вопросы стажёров наставника, сгруппированные по смыслу."""
    rows = db.execute(
        "SELECT q.id, q.text, q.signature, q.created_at, u.full_name "
        "FROM questions q JOIN users u ON u.id = q.intern_id "
        "WHERE q.status = 'pending' AND u.mentor_id = ? ORDER BY q.id",
        (mentor_id,),
    ).fetchall()

    groups = {}
    for row in rows:
        group = groups.setdefault(
            row["signature"],
            {
                "question_id": row["id"],
                "text": row["text"],
                "asked_count": 0,
                "interns": [],
                "first_asked": row["created_at"],
            },
        )
        group["asked_count"] += 1
        if row["full_name"] not in group["interns"]:
            group["interns"].append(row["full_name"])
    return list(groups.values())


def answer_group(db, mentor_id, question_id, answer, audience="all"):
    """Ответить наставником один раз: ответ получают все, кто спрашивал то же самое,
    и он сохраняется в базу знаний. Возвращает число закрытых вопросов или None."""
    question = db.execute(
        "SELECT q.* FROM questions q JOIN users u ON u.id = q.intern_id "
        "WHERE q.id = ? AND q.status = 'pending' AND u.mentor_id = ?",
        (question_id, mentor_id),
    ).fetchone()
    if question is None:
        return None

    group = db.execute(
        "SELECT id, intern_id, text FROM questions "
        "WHERE status = 'pending' AND signature = ? AND intern_id IN "
        "(SELECT id FROM users WHERE mentor_id = ?)",
        (question["signature"], mentor_id),
    ).fetchall()

    entry_id = kb.add_entry(db, question["text"], answer, audience=audience, source="mentor")
    db.execute(
        "UPDATE questions SET status = 'answered_by_mentor', answer = ?, kb_entry_id = ?, "
        "answered_at = CURRENT_TIMESTAMP "
        "WHERE status = 'pending' AND signature = ? AND intern_id IN "
        "(SELECT id FROM users WHERE mentor_id = ?)",
        (answer, entry_id, question["signature"], mentor_id),
    )
    # Каждый стажёр видит ответ прямо в своём чате.
    for row in group:
        save_message(
            db, row["intern_id"], "assistant",
            f"Наставник ответил на твой вопрос «{row['text']}»:\n{answer}",
            kind="mentor_reply", payload={"question_id": row["id"]},
        )
    analytics.track(db, mentor_id, "mentor_answered", {"closed": len(group)})
    db.commit()
    return len(group)


def metrics(db, mentor_id, minutes_per_answer):
    def count(extra=""):
        return db.execute(
            "SELECT COUNT(*) FROM questions q JOIN users u ON u.id = q.intern_id "
            "WHERE u.mentor_id = ? " + extra,
            (mentor_id,),
        ).fetchone()[0]

    total = count()
    auto = count("AND q.status = 'answered_auto'")
    pending = count("AND q.status = 'pending'")
    by_mentor = count("AND q.status = 'answered_by_mentor'")
    reused = db.execute(
        "SELECT COUNT(*) FROM questions q JOIN users u ON u.id = q.intern_id "
        "JOIN kb_entries k ON k.id = q.kb_entry_id "
        "WHERE u.mentor_id = ? AND q.status = 'answered_auto' AND k.source = 'mentor'",
        (mentor_id,),
    ).fetchone()[0]
    wait = db.execute(
        "SELECT AVG((julianday(q.answered_at) - julianday(q.created_at)) * 24 * 60) "
        "FROM questions q JOIN users u ON u.id = q.intern_id "
        "WHERE u.mentor_id = ? AND q.status = 'answered_by_mentor'",
        (mentor_id,),
    ).fetchone()[0]
    return {
        "total_questions": total,
        "answered_without_mentor": auto,
        "pending": pending,
        "answered_by_mentor": by_mentor,
        "auto_rate": round(auto / total, 2) if total else 0.0,
        "reused_mentor_answers": reused,
        "mentor_minutes_saved": auto * minutes_per_answer,
        "avg_minutes_to_mentor_answer": round(wait, 1) if wait is not None else None,
        "events": analytics.counts_for_mentor(db, mentor_id),
    }
