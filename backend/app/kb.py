"""База знаний команды: поиск и пополнение."""
from .text import stems


def visible_audiences(role):
    """Стажёр видит только общие записи, наставник — все."""
    return ("all",) if role == "intern" else ("all", "mentor")


def top_matches(db, text, role, limit=3):
    """Лучшие записи с оценкой 0..1, по убыванию. Нулевые оценки отбрасываются."""
    query = stems(text)
    if not query:
        return []

    audiences = visible_audiences(role)
    marks = ",".join("?" for _ in audiences)
    rows = db.execute(
        f"SELECT * FROM kb_entries WHERE audience IN ({marks}) ORDER BY id", audiences
    ).fetchall()

    scored = []
    for row in rows:
        entry_stems = stems(row["question"]) | stems(row["keywords"])
        score = len(query & entry_stems) / len(query)
        if score > 0:
            scored.append((row, score))
    scored.sort(key=lambda pair: -pair[1])
    return scored[:limit]


def best_match(db, text, role):
    """Возвращает (запись, оценка 0..1). Если ничего похожего — (None, 0.0)."""
    matches = top_matches(db, text, role, limit=1)
    return matches[0] if matches else (None, 0.0)


def add_entry(db, question, answer, audience="all", source="mentor"):
    cur = db.execute(
        "INSERT INTO kb_entries (question, answer, audience, source) VALUES (?, ?, ?, ?)",
        (question, answer, audience, source),
    )
    return cur.lastrowid


def mark_used(db, entry_id):
    db.execute("UPDATE kb_entries SET times_used = times_used + 1 WHERE id = ?", (entry_id,))
