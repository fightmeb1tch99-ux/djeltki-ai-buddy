from app import kb
from app.text import signature, stems


def test_stems_drop_stop_words_and_short_words():
    assert stems("Как оформить отгул?") == {"оформ", "отгул"}
    assert stems("") == set()
    assert stems(None) == set()


def test_stems_match_different_word_forms():
    assert stems("отгулы") == stems("отгулом")


def test_signature_is_order_independent():
    assert signature("оформить отгул") == signature("отгул оформить")


def test_signature_fallback_when_no_stems():
    assert signature("ы ъ") == "ы ъ"
    assert signature("") == ""


def test_best_match_found(app):
    with app.app_context():
        from app.db import get_db

        entry, score = kb.best_match(get_db(), "как оформить отгул", "intern")
        assert entry is not None and score == 1.0


def test_best_match_nothing(app):
    with app.app_context():
        from app.db import get_db

        entry, score = kb.best_match(get_db(), "погода на марсе", "intern")
        assert entry is None and score == 0.0
        assert kb.best_match(get_db(), "?!", "intern") == (None, 0.0)


def test_add_entry_and_mark_used(app):
    with app.app_context():
        from app.db import get_db

        db = get_db()
        entry_id = kb.add_entry(db, "Где кофемашина?", "На третьем этаже.")
        kb.mark_used(db, entry_id)
        row = db.execute("SELECT * FROM kb_entries WHERE id = ?", (entry_id,)).fetchone()
        assert row["times_used"] == 1 and row["source"] == "mentor"
