from datetime import date

import pytest

from app.dates import extract_range, format_range
from app.intents import detect

TODAY = date(2026, 11, 11)  # среда


@pytest.mark.parametrize(
    "text, expected",
    [
        ("с 20 по 22 ноября", (date(2026, 11, 20), date(2026, 11, 22))),
        ("20-22 ноября", (date(2026, 11, 20), date(2026, 11, 22))),
        ("с 20 ноября по 2 декабря", (date(2026, 11, 20), date(2026, 12, 2))),
        ("на 20 ноября", (date(2026, 11, 20), date(2026, 11, 20))),
        ("20.11", (date(2026, 11, 20), date(2026, 11, 20))),
        ("20.11.26 – 22.11.26", (date(2026, 11, 20), date(2026, 11, 22))),
        ("2026-12-01", (date(2026, 12, 1), date(2026, 12, 1))),
        ("сегодня", (TODAY, TODAY)),
        ("завтра", (date(2026, 11, 12), date(2026, 11, 12))),
        ("послезавтра", (date(2026, 11, 13), date(2026, 11, 13))),
        ("в пятницу", (date(2026, 11, 13), date(2026, 11, 13))),
        ("в среду", (date(2026, 11, 18), date(2026, 11, 18))),  # не сегодня, а через неделю
        ("5 ноября", (date(2027, 11, 5), date(2027, 11, 5))),  # прошло: берём следующий год
        ("25 ноября и 20 ноября", (date(2026, 11, 20), date(2026, 11, 25))),
    ],
)
def test_extract_range(text, expected):
    assert extract_range(text, TODAY) == expected


@pytest.mark.parametrize("text", ["", None, "без дат", "31 февраля", "32.13", "2026-13-45"])
def test_extract_range_none(text):
    assert extract_range(text, TODAY) is None


def test_invalid_date_inside_range_is_ignored():
    assert extract_range("с 30 по 31 февраля", TODAY) is None


def test_format_range():
    assert format_range(date(2026, 11, 20), date(2026, 11, 20)) == "20 ноября"
    assert format_range(date(2026, 11, 20), date(2026, 11, 22)) == "20–22 ноября"
    assert format_range(date(2026, 11, 30), date(2026, 12, 2)) == "30 ноября – 2 декабря"


def test_leave_question_is_explanation_not_action():
    result = detect("Как оформить отгул?", TODAY)
    assert result["intent"] == "leave" and result["wants_action"] is False


def test_leave_request_with_dates_and_reason():
    result = detect("Оформи отгул с 20 по 22 ноября, причина: личные дела", TODAY)
    assert result["wants_action"] is True
    assert result["dates"] == (date(2026, 11, 20), date(2026, 11, 22))
    assert result["reason"] == "личные дела"


def test_leave_want_without_dates():
    result = detect("Хочу отгул", TODAY)
    assert result["wants_action"] is True and result["dates"] is None


def test_leave_question_with_dates_is_action():
    assert detect("Как оформить отгул на 20 ноября?", TODAY)["wants_action"] is True


def test_access_intents():
    assert detect("Запроси доступ к Jira", TODAY) == {"intent": "access_request", "system": "Jira"}
    assert detect("нужен гитлаб", TODAY)["system"] == "GitLab"
    assert detect("Какие у меня доступы?", TODAY)["intent"] == "access_status"
    assert detect("что с моим доступом в Jira", TODAY)["intent"] == "access_status"
    assert detect("Как получить доступ к Jira?", TODAY)["intent"] == "kb"


def test_next_step_and_plain_question():
    assert detect("Что мне делать дальше?", TODAY)["intent"] == "next_step"
    assert detect("Покажи мой прогресс", TODAY)["intent"] == "next_step"
    assert detect("Где взять пропуск в офис?", TODAY)["intent"] == "kb"
    assert detect("", TODAY)["intent"] == "kb"
