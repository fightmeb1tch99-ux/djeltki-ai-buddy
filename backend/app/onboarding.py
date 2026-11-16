"""Чек-лист адаптации: этапы, шаги, статусы и следующий шаг.

Шаг со ссылкой `access:<Система>` закрывается сам, когда доступ выдан: так действие
через корпоративный сервис двигает прогресс стажёра без ручной отметки.
"""
from . import analytics

ACCESS_STATUS_STEP = {"requested": "in_progress", "granted": "done"}


class TaskError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def _rows(db, intern_id):
    return db.execute(
        "SELECT s.id AS stage_id, s.position AS stage_pos, s.title AS stage_title, "
        "       s.description AS stage_description, "
        "       t.id AS task_id, t.title AS task_title, t.link AS link, "
        "       COALESCE(it.status, 'todo') AS manual_status, "
        "       (SELECT a.status FROM access_requests a "
        "         WHERE a.intern_id = ? AND t.link = 'access:' || a.system) AS access_status "
        "FROM stages s JOIN tasks t ON t.stage_id = s.id "
        "LEFT JOIN intern_tasks it ON it.task_id = t.id AND it.intern_id = ? "
        "ORDER BY s.position, t.position",
        (intern_id, intern_id),
    ).fetchall()


def _task_status(row):
    if row["manual_status"] == "done":
        return "done"
    if row["access_status"]:
        return ACCESS_STATUS_STEP[row["access_status"]]
    return "todo"


def list_stages(db, intern_id):
    stages = {}
    order = []
    flat = []
    for row in _rows(db, intern_id):
        stage = stages.get(row["stage_id"])
        if stage is None:
            stage = {
                "id": row["stage_id"],
                "position": row["stage_pos"],
                "title": row["stage_title"],
                "description": row["stage_description"],
                "tasks": [],
            }
            stages[row["stage_id"]] = stage
            order.append(stage)
        task = {
            "id": row["task_id"],
            "title": row["task_title"],
            "status": _task_status(row),
            "auto": row["link"] is not None,
        }
        stage["tasks"].append(task)
        flat.append((stage, task))

    for stage in order:
        done = sum(1 for t in stage["tasks"] if t["status"] == "done")
        stage["done_count"] = done
        stage["total"] = len(stage["tasks"])
        if done == stage["total"]:
            stage["status"] = "done"
        elif done or any(t["status"] == "in_progress" for t in stage["tasks"]):
            stage["status"] = "in_progress"
        else:
            stage["status"] = "todo"

    total = len(flat)
    done_total = sum(1 for _, t in flat if t["status"] == "done")
    pending = [(s, t) for s, t in flat if t["status"] != "done"]
    # Сначала то, что стажёр может сделать сам; если такого нет — то, чего он ждёт.
    pending.sort(key=lambda pair: pair[1]["status"] == "in_progress")
    next_step = None
    if pending:
        stage, task = pending[0]
        next_step = {
            "task_id": task["id"],
            "title": task["title"],
            "stage_title": stage["title"],
            "waiting": task["status"] == "in_progress",
        }
    return {
        "stages": order,
        "progress_percent": round(100 * done_total / total) if total else 0,
        "next_step": next_step,
    }


def describe_next_step(data):
    if data["next_step"] is None:
        return "Все шаги адаптации пройдены. Отличная работа!"
    step = data["next_step"]
    if step["waiting"]:
        tail = "Сейчас остаётся ждать согласования, остальные шаги уже сделаны."
    else:
        tail = ""
    text = (
        f"Прогресс: {data['progress_percent']}%. "
        f"Следующий шаг: «{step['title']}» (этап «{step['stage_title']}»)."
    )
    return f"{text} {tail}".strip()


def set_task(db, intern_id, task_id, done, user_id=None):
    row = db.execute("SELECT id, link FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise TaskError("Шаг не найден", 404)
    if row["link"]:
        raise TaskError("Этот шаг закрывается сам, когда доступ будет выдан", 409)
    db.execute(
        "INSERT INTO intern_tasks (intern_id, task_id, status, done_at) "
        "VALUES (?, ?, ?, CASE WHEN ? = 'done' THEN CURRENT_TIMESTAMP END) "
        "ON CONFLICT(intern_id, task_id) DO UPDATE SET status = excluded.status, "
        "done_at = excluded.done_at",
        (intern_id, task_id, "done" if done else "todo", "done" if done else "todo"),
    )
    analytics.track(db, user_id or intern_id, "task_done" if done else "task_reopened",
                    {"task_id": task_id})
    db.commit()
    return list_stages(db, intern_id)
