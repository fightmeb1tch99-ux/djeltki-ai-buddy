"""Имитация feature flags (runtime). В Авито используются корпоративные флаги."""

DEFAULTS = {
    "llm_answers": True,   # использовать LLM для ответа по базе знаний (если он настроен)
    "chat_actions": True,  # предлагать действия в чате (отгул, доступы)
}


def is_enabled(db, name):
    row = db.execute("SELECT enabled FROM feature_flags WHERE name = ?", (name,)).fetchone()
    if row is None:
        return DEFAULTS[name]
    return bool(row["enabled"])


def all_flags(db):
    return {name: is_enabled(db, name) for name in DEFAULTS}


def set_flag(db, name, enabled):
    db.execute(
        "INSERT INTO feature_flags (name, enabled) VALUES (?, ?) "
        "ON CONFLICT(name) DO UPDATE SET enabled = excluded.enabled",
        (name, 1 if enabled else 0),
    )
    db.commit()
