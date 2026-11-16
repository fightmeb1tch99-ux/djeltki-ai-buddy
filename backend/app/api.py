"""REST API прототипа."""
import hmac

from flask import Blueprint, current_app, g, jsonify, request

from . import assistant, cron, flags, mcp_tools, onboarding
from .auth import error, login_required, role_required
from .db import get_db

bp = Blueprint("api", __name__)


def _json():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


@bp.get("/api/health")
def health():
    return jsonify({"status": "ok"})


# --- чат --------------------------------------------------------------------------------

@bp.post("/api/chat")
@login_required
def chat():
    text = str(_json().get("message", "")).strip()
    if not text:
        return error("Напиши вопрос")
    if len(text) > 500:
        return error("Вопрос слишком длинный (максимум 500 символов)")
    return jsonify(assistant.ask(get_db(), g.user, text, current_app.config))


@bp.get("/api/chat/history")
@login_required
def chat_history():
    return jsonify({"items": assistant.history(get_db(), g.user["id"])})


def _resolve(message_id, confirm):
    try:
        return jsonify(assistant.resolve_action(get_db(), g.user, message_id, confirm))
    except assistant.ActionError as exc:
        return error(exc.message, exc.status)


@bp.post("/api/actions/<int:message_id>/confirm")
@role_required("intern")
def confirm_action(message_id):
    return _resolve(message_id, True)


@bp.post("/api/actions/<int:message_id>/cancel")
@role_required("intern")
def cancel_action(message_id):
    return _resolve(message_id, False)


@bp.get("/api/questions")
@role_required("intern")
def my_questions():
    rows = get_db().execute(
        "SELECT id, text, status, answer, created_at, answered_at FROM questions "
        "WHERE intern_id = ? ORDER BY id DESC",
        (g.user["id"],),
    ).fetchall()
    return jsonify({"items": [dict(row) for row in rows]})


# --- чек-лист адаптации ------------------------------------------------------------------

@bp.get("/api/stages")
@role_required("intern")
def stages():
    return jsonify(onboarding.list_stages(get_db(), g.user["id"]))


@bp.patch("/api/tasks/<int:task_id>")
@role_required("intern")
def update_task(task_id):
    done = _json().get("done")
    if not isinstance(done, bool):
        return error("done: true или false")
    try:
        result = onboarding.set_task(get_db(), g.user["id"], task_id, done)
    except onboarding.TaskError as exc:
        return error(exc.message, exc.status)
    return jsonify(result)


# --- инструменты (имитация корпоративных сервисов) ---------------------------------------

@bp.get("/api/tools")
@login_required
def tools():
    return jsonify({"items": mcp_tools.list_tools()})


def _call(name, args):
    try:
        return jsonify(mcp_tools.call_tool(get_db(), g.user, name, args))
    except mcp_tools.ToolError as exc:
        return error(exc.message, exc.status)


@bp.post("/api/leave-requests")
@login_required
def create_leave():
    response = _call("create_leave_request", _json())
    if isinstance(response, tuple):
        return response
    return response, 201


@bp.get("/api/leave-requests")
@login_required
def list_leave():
    db = get_db()
    if g.user["role"] == "intern":
        rows = db.execute(
            "SELECT * FROM leave_requests WHERE intern_id = ? ORDER BY id DESC",
            (g.user["id"],),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT l.*, u.full_name FROM leave_requests l "
            "JOIN users u ON u.id = l.intern_id WHERE u.mentor_id = ? ORDER BY l.id DESC",
            (g.user["id"],),
        ).fetchall()
    return jsonify({"items": [dict(row) for row in rows]})


@bp.post("/api/leave-requests/<int:request_id>/decision")
@role_required("mentor")
def decide_leave(request_id):
    decision = str(_json().get("decision", ""))
    if decision not in ("approve", "reject"):
        return error("decision: approve или reject")
    db = get_db()
    row = db.execute(
        "SELECT l.* FROM leave_requests l JOIN users u ON u.id = l.intern_id "
        "WHERE l.id = ? AND u.mentor_id = ?",
        (request_id, g.user["id"]),
    ).fetchone()
    if row is None:
        return error("Заявка не найдена", 404)
    if row["status"] != "submitted":
        return error("Решение по заявке уже принято", 409)
    status = "approved" if decision == "approve" else "rejected"
    db.execute("UPDATE leave_requests SET status = ? WHERE id = ?", (status, request_id))
    assistant.save_message(
        db, row["intern_id"], "assistant",
        f"Заявка {row['external_id']} {'одобрена' if status == 'approved' else 'отклонена'} "
        "руководителем.",
        kind="info",
    )
    db.commit()
    return jsonify({"id": request_id, "status": status})


@bp.get("/api/access")
@role_required("intern")
def access_status():
    return _call("get_access_status", {})


@bp.post("/api/access")
@role_required("intern")
def access_request():
    return _call("request_access", _json())


@bp.get("/api/access/pending")
@role_required("mentor")
def access_pending():
    rows = get_db().execute(
        "SELECT a.id, a.system, a.status, u.full_name FROM access_requests a "
        "JOIN users u ON u.id = a.intern_id WHERE u.mentor_id = ? AND a.status = 'requested' "
        "ORDER BY a.id",
        (g.user["id"],),
    ).fetchall()
    return jsonify({"items": [dict(row) for row in rows]})


@bp.post("/api/access/<int:access_id>/grant")
@role_required("mentor")
def grant_access(access_id):
    db = get_db()
    row = db.execute(
        "SELECT a.* FROM access_requests a JOIN users u ON u.id = a.intern_id "
        "WHERE a.id = ? AND u.mentor_id = ?",
        (access_id, g.user["id"]),
    ).fetchone()
    if row is None:
        return error("Заявка не найдена", 404)
    db.execute(
        "UPDATE access_requests SET status = 'granted', updated_at = CURRENT_TIMESTAMP "
        "WHERE id = ?",
        (access_id,),
    )
    assistant.save_message(
        db, row["intern_id"], "assistant", f"Доступ к {row['system']} выдан.", kind="info"
    )
    db.commit()
    return jsonify({"id": access_id, "status": "granted"})


# --- кабинет наставника ------------------------------------------------------------------

@bp.get("/api/mentor/interns")
@role_required("mentor")
def mentor_interns():
    db = get_db()
    rows = db.execute(
        "SELECT id, full_name FROM users WHERE mentor_id = ? ORDER BY id", (g.user["id"],)
    ).fetchall()
    items = []
    for row in rows:
        progress = onboarding.list_stages(db, row["id"])
        items.append(
            {
                "id": row["id"],
                "full_name": row["full_name"],
                "progress_percent": progress["progress_percent"],
                "next_step": progress["next_step"],
            }
        )
    return jsonify({"items": items})


@bp.get("/api/mentor/digest")
@role_required("mentor")
def digest():
    return jsonify({"items": assistant.pending_digest(get_db(), g.user["id"])})


@bp.post("/api/mentor/digest/answer")
@role_required("mentor")
def digest_answer():
    data = _json()
    answer = str(data.get("answer", "")).strip()
    audience = str(data.get("audience", "all"))
    if not answer:
        return error("Напиши ответ")
    if audience not in ("all", "mentor"):
        return error("audience: all или mentor")
    try:
        question_id = int(data.get("question_id"))
    except (TypeError, ValueError):
        return error("Нужен question_id")

    closed = assistant.answer_group(get_db(), g.user["id"], question_id, answer, audience)
    if closed is None:
        return error("Вопрос не найден или уже отвечен", 404)
    return jsonify({"closed_questions": closed})


@bp.get("/api/metrics")
@role_required("mentor")
def metrics():
    return jsonify(
        assistant.metrics(
            get_db(), g.user["id"], current_app.config["MINUTES_SAVED_PER_ANSWER"]
        )
    )


@bp.get("/api/notifications")
@role_required("mentor")
def notifications():
    rows = get_db().execute(
        "SELECT id, text, is_read, created_at FROM notifications WHERE user_id = ? "
        "ORDER BY id DESC LIMIT 20",
        (g.user["id"],),
    ).fetchall()
    return jsonify({"items": [dict(row) for row in rows]})


@bp.post("/api/notifications/read")
@role_required("mentor")
def notifications_read():
    db = get_db()
    db.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (g.user["id"],))
    db.commit()
    return jsonify({"status": "ok"})


# --- feature flags -----------------------------------------------------------------------

@bp.get("/api/flags")
@login_required
def get_flags():
    return jsonify(flags.all_flags(get_db()))


@bp.put("/api/flags/<name>")
@role_required("mentor")
def put_flag(name):
    if name not in flags.DEFAULTS:
        return error("Неизвестный флаг", 404)
    enabled = _json().get("enabled")
    if not isinstance(enabled, bool):
        return error("enabled: true или false")
    flags.set_flag(get_db(), name, enabled)
    return jsonify(flags.all_flags(get_db()))


# --- крон (имитация ИИ-крона) ------------------------------------------------------------

@bp.post("/api/internal/cron/digest")
def cron_digest():
    expected = current_app.config["CRON_TOKEN"]
    given = request.headers.get("X-Cron-Token", "")
    if not expected or not hmac.compare_digest(expected, given):
        return error("Недостаточно прав", 403)
    return jsonify({"notifications_created": cron.run_digest(get_db())})
