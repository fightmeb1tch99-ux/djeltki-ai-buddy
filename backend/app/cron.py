"""Задача по расписанию: дайджест неотвеченных вопросов для наставников.

Имитация ИИ-крона Авито. Запуск вручную: `python -m app.cron`.
По HTTP: POST /api/internal/cron/digest с заголовком X-Cron-Token.
"""
from . import assistant
from .db import get_db


def run_digest(db):
    """Создаёт уведомление каждому наставнику, у которого есть вопросы без ответа."""
    created = 0
    for mentor in db.execute("SELECT id FROM users WHERE role = 'mentor'").fetchall():
        groups = assistant.pending_digest(db, mentor["id"])
        if not groups:
            continue
        total = sum(group["asked_count"] for group in groups)
        text = (
            f"Ждут ответа: {len(groups)} (обращений стажёров: {total}). "
            "Ответьте один раз, и ответ получат все."
        )
        db.execute(
            "INSERT INTO notifications (user_id, text) VALUES (?, ?)", (mentor["id"], text)
        )
        created += 1
    db.commit()
    return created


if __name__ == "__main__":  # pragma: no cover
    from . import create_app

    application = create_app()
    with application.app_context():
        print("Уведомлений создано:", run_digest(get_db()))
