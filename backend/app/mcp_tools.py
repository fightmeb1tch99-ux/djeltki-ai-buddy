"""Имитация корпоративных сервисов в виде MCP-подобных инструментов.

Каждый инструмент — это имя, описание, JSON-схема входа и функции:
  prepare — проверить запрос и описать, что будет сделано (до подтверждения человеком);
  handler — выполнить действие. Здесь результат пишется в SQLite, в Авито вызов
            пойдёт в настоящий сервис через MCP.
Роль проверяется внутри инструментов: помощник не делает того, что недоступно пользователю.
"""
from datetime import date, timedelta

from flask import current_app

from .dates import format_range

ALLOWED_SYSTEMS = ["GitLab", "Jira", "VPN", "Confluence", "Grafana"]
ACCESS_STATUS_RU = {"requested": "ждёт согласования", "granted": "выдан"}


class ToolError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def today():
    fixed = current_app.config.get("TODAY")
    return date.fromisoformat(fixed) if fixed else date.today()


def _parse_date(value, field):
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ToolError(f"Поле {field}: ожидается дата в формате ГГГГ-ММ-ДД")


def _require_intern(user):
    if user["role"] != "intern":
        raise ToolError("Это действие доступно только стажёру", 403)


# --- отгул ----------------------------------------------------------------------------

def _validate_leave(db, user, args):
    _require_intern(user)
    start = _parse_date(args.get("start_date"), "start_date")
    end = _parse_date(args.get("end_date"), "end_date")
    reason = str(args.get("reason", "")).strip()

    if end < start:
        raise ToolError("Дата окончания раньше даты начала")
    if start < today():
        raise ToolError("Нельзя оформить отгул задним числом")
    max_days = current_app.config["MAX_LEAVE_DAYS"]
    if (end - start) > timedelta(days=max_days - 1):
        raise ToolError(f"Отгул не может быть длиннее {max_days} дней")
    if len(reason) > 200:
        raise ToolError("Причина слишком длинная (максимум 200 символов)")

    overlap = db.execute(
        "SELECT id FROM leave_requests WHERE intern_id = ? AND status != 'rejected' "
        "AND start_date <= ? AND end_date >= ?",
        (user["id"], end.isoformat(), start.isoformat()),
    ).fetchone()
    if overlap:
        raise ToolError("На эти даты уже есть заявка", 409)
    return start, end, reason


def prepare_leave(db, user, args):
    start, end, reason = _validate_leave(db, user, args)
    lines = [f"Даты: {format_range(start, end)}"]
    if reason:
        lines.append(f"Причина: {reason}")
    lines.append("Заявку получит руководитель, он подтвердит её в системе отсутствий.")
    return {
        "args": {"start_date": start.isoformat(), "end_date": end.isoformat(), "reason": reason},
        "title": "Заявка на отгул",
        "lines": lines,
    }


def create_leave_request(db, user, args):
    """Имитация сервиса отсутствий: создаёт заявку на отгул."""
    start, end, reason = _validate_leave(db, user, args)
    cur = db.execute(
        "INSERT INTO leave_requests (intern_id, start_date, end_date, reason) "
        "VALUES (?, ?, ?, ?)",
        (user["id"], start.isoformat(), end.isoformat(), reason),
    )
    external_id = f"ABS-{cur.lastrowid:06d}"
    db.execute(
        "UPDATE leave_requests SET external_id = ? WHERE id = ?", (external_id, cur.lastrowid)
    )
    db.commit()
    return {
        "id": cur.lastrowid,
        "external_id": external_id,
        "status": "submitted",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "reason": reason,
    }


def describe_leave(result):
    period = format_range(
        date.fromisoformat(result["start_date"]), date.fromisoformat(result["end_date"])
    )
    return (
        f"Готово! Заявка {result['external_id']} на {period} отправлена руководителю. "
        "Статус: отправлена. Я покажу решение здесь, как только оно появится."
    )


# --- доступы --------------------------------------------------------------------------

def _validate_access(db, user, args):
    _require_intern(user)
    system = str(args.get("system", ""))
    if system not in ALLOWED_SYSTEMS:
        raise ToolError("Неизвестная система. Доступно: " + ", ".join(ALLOWED_SYSTEMS))
    existing = db.execute(
        "SELECT * FROM access_requests WHERE intern_id = ? AND system = ?",
        (user["id"], system),
    ).fetchone()
    return system, existing


def prepare_access(db, user, args):
    system, existing = _validate_access(db, user, args)
    if existing:
        raise ToolError(
            f"Доступ к {system} уже запрошен: {ACCESS_STATUS_RU[existing['status']]}.", 409
        )
    return {
        "args": {"system": system},
        "title": f"Запрос доступа к {system}",
        "lines": [
            f"Система: {system}",
            "Заявка уйдёт руководителю, статус появится в разделе «Доступы».",
        ],
    }


def request_access(db, user, args):
    """Имитация сервиса доступов: создаёт заявку (повторный запрос ничего не дублирует)."""
    system, existing = _validate_access(db, user, args)
    if existing:
        return {"id": existing["id"], "system": system, "status": existing["status"],
                "created": False}
    cur = db.execute(
        "INSERT INTO access_requests (intern_id, system) VALUES (?, ?)", (user["id"], system)
    )
    db.commit()
    return {"id": cur.lastrowid, "system": system, "status": "requested", "created": True}


def describe_access(result):
    if result["created"]:
        return (
            f"Готово! Заявка на доступ к {result['system']} создана, "
            "статус: ждёт согласования. Шаг в чек-листе закроется сам, когда доступ выдадут."
        )
    return f"Доступ к {result['system']} уже запрошен: {ACCESS_STATUS_RU[result['status']]}."


def get_access_status(db, user, _args):
    _require_intern(user)
    rows = db.execute(
        "SELECT id, system, status FROM access_requests WHERE intern_id = ? ORDER BY system",
        (user["id"],),
    ).fetchall()
    return {"items": [dict(row) for row in rows], "available_systems": ALLOWED_SYSTEMS}


def describe_access_status(result):
    if not result["items"]:
        return "Пока ни одного доступа не запрошено. Напиши, например: «Запроси доступ к GitLab»."
    lines = [f"• {i['system']}: {ACCESS_STATUS_RU[i['status']]}" for i in result["items"]]
    return "Твои доступы:\n" + "\n".join(lines)


TOOLS = {
    "create_leave_request": {
        "description": "Создать заявку на отгул в системе отсутствий.",
        "input_schema": {
            "type": "object",
            "required": ["start_date", "end_date"],
            "properties": {
                "start_date": {"type": "string", "format": "date"},
                "end_date": {"type": "string", "format": "date"},
                "reason": {"type": "string", "maxLength": 200},
            },
        },
        "prepare": prepare_leave,
        "handler": create_leave_request,
        "describe": describe_leave,
    },
    "request_access": {
        "description": "Запросить доступ к системе.",
        "input_schema": {
            "type": "object",
            "required": ["system"],
            "properties": {"system": {"type": "string", "enum": ALLOWED_SYSTEMS}},
        },
        "prepare": prepare_access,
        "handler": request_access,
        "describe": describe_access,
    },
    "get_access_status": {
        "description": "Показать статусы доступов стажёра.",
        "input_schema": {"type": "object", "properties": {}},
        "handler": get_access_status,
        "describe": describe_access_status,
    },
}


def list_tools():
    return [
        {"name": name, "description": spec["description"], "input_schema": spec["input_schema"]}
        for name, spec in TOOLS.items()
    ]


def _spec(name):
    spec = TOOLS.get(name)
    if spec is None:
        raise ToolError("Неизвестный инструмент", 404)
    return spec


def prepare_tool(db, user, name, args):
    """Проверить запрос и описать действие, ничего не меняя."""
    spec = _spec(name)
    if "prepare" not in spec:
        raise ToolError("Для этого инструмента подтверждение не нужно", 400)
    return spec["prepare"](db, user, args or {})


def call_tool(db, user, name, args):
    return _spec(name)["handler"](db, user, args or {})


def describe_result(name, result):
    return _spec(name)["describe"](result)
