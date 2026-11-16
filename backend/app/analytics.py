"""Имитация Clickstream: события продукта для метрик пользы.

В проде те же события уходят в Clickstream (Kafka), а дашборд строится в Grafana.
"""
import json


def track(db, user_id, name, props=None):
    db.execute(
        "INSERT INTO events (user_id, name, props) VALUES (?, ?, ?)",
        (user_id, name, json.dumps(props, ensure_ascii=False) if props else None),
    )


def counts_for_mentor(db, mentor_id):
    """События стажёров наставника и самого наставника."""
    rows = db.execute(
        "SELECT e.name, COUNT(*) AS n FROM events e JOIN users u ON u.id = e.user_id "
        "WHERE u.mentor_id = ? OR u.id = ? GROUP BY e.name ORDER BY e.name",
        (mentor_id, mentor_id),
    ).fetchall()
    return {row["name"]: row["n"] for row in rows}
