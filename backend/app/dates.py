"""Разбор дат из русского текста: «с 20 по 22 ноября», «20.11», «завтра», «в пятницу»."""
import re
from datetime import date, timedelta

MONTH_PREFIXES = (
    ("январ", 1), ("феврал", 2), ("март", 3), ("апрел", 4), ("мая", 5), ("май", 5),
    ("июн", 6), ("июл", 7), ("август", 8), ("сентябр", 9), ("октябр", 10),
    ("ноябр", 11), ("декабр", 12),
)
MONTH_NAMES_GEN = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)
WEEKDAY_PREFIXES = (
    ("понедельник", 0), ("вторник", 1), ("сред", 2), ("четверг", 3),
    ("пятниц", 4), ("суббот", 5), ("воскресень", 6),
)

_MONTH = "(?:" + "|".join(prefix for prefix, _ in MONTH_PREFIXES) + r")[а-я]*"
_WEEKDAY = "|".join(prefix + "[а-я]*" for prefix, _ in WEEKDAY_PREFIXES)

# Порядок важен: сначала более specific-шаблоны, чтобы они «съели» свои символы.
P_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
P_RANGE = re.compile(rf"(\d{{1,2}})\s*(?:по|[-–—])\s*(\d{{1,2}})\s+({_MONTH})(?:\s+(\d{{4}}))?")
P_DMY = re.compile(r"(\d{1,2})\.(\d{1,2})(?:\.(\d{4}|\d{2}))?")
P_DMONTH = re.compile(rf"(\d{{1,2}})\s+({_MONTH})(?:\s+(\d{{4}}))?")
P_REL = re.compile(r"послезавтра|завтра|сегодня")
P_WEEKDAY = re.compile(rf"(?:в|на|до)\s+({_WEEKDAY})")


def _month_number(word):
    for prefix, number in MONTH_PREFIXES:
        if word.startswith(prefix):
            return number
    return None


def _resolve(day, month, year, today):
    """Собирает дату. Без года берём ближайшую будущую."""
    explicit = year is not None
    year_value = int(year) if explicit else today.year
    if year_value < 100:
        year_value += 2000
    try:
        result = date(year_value, month, day)
    except ValueError:
        return None
    if not explicit and result < today:
        try:
            result = date(year_value + 1, month, day)
        except ValueError:
            return None
    return result


def extract_range(text, today):
    """Возвращает (начало, конец) или None, если дат в тексте нет."""
    low = (text or "").lower()
    consumed = []
    found = []

    def free(span):
        return all(span[1] <= a or span[0] >= b for a, b in consumed)

    def take(match, *dates):
        consumed.append(match.span())
        for item in dates:
            if item is not None:
                found.append((match.start(), item))

    for match in P_ISO.finditer(low):
        if free(match.span()):
            try:
                take(match, date(int(match[1]), int(match[2]), int(match[3])))
            except ValueError:
                pass

    for match in P_RANGE.finditer(low):
        if free(match.span()):
            month = _month_number(match[3])
            take(
                match,
                _resolve(int(match[1]), month, match[4], today),
                _resolve(int(match[2]), month, match[4], today),
            )

    for match in P_DMY.finditer(low):
        if free(match.span()):
            take(match, _resolve(int(match[1]), int(match[2]), match[3], today))

    for match in P_DMONTH.finditer(low):
        if free(match.span()):
            take(match, _resolve(int(match[1]), _month_number(match[2]), match[3], today))

    for match in P_REL.finditer(low):
        if free(match.span()):
            offset = {"сегодня": 0, "завтра": 1, "послезавтра": 2}[match[0]]
            take(match, today + timedelta(days=offset))

    for match in P_WEEKDAY.finditer(low):
        if free(match.span()):
            word = match[1]
            weekday = next(number for prefix, number in WEEKDAY_PREFIXES if word.startswith(prefix))
            delta = (weekday - today.weekday()) % 7 or 7
            take(match, today + timedelta(days=delta))

    found.sort(key=lambda item: item[0])
    dates = [item[1] for item in found]
    if not dates:
        return None
    if len(dates) == 1:
        return dates[0], dates[0]
    first, second = dates[0], dates[1]
    return min(first, second), max(first, second)


def format_range(start, end):
    """20–22 ноября / 30 ноября – 2 декабря / 20 ноября."""
    if start == end:
        return f"{start.day} {MONTH_NAMES_GEN[start.month - 1]}"
    if start.month == end.month and start.year == end.year:
        return f"{start.day}–{end.day} {MONTH_NAMES_GEN[end.month - 1]}"
    return (
        f"{start.day} {MONTH_NAMES_GEN[start.month - 1]} – "
        f"{end.day} {MONTH_NAMES_GEN[end.month - 1]}"
    )
