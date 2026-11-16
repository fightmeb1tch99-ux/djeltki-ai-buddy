"""Определение намерения по тексту стажёра.

Намерения: leave (отгул), access_request, access_status, next_step, kb (обычный вопрос).
Правило безопасности: действие предлагается, только если человек явно его просит.
Вопрос в стиле «Как оформить отгул?» получает объяснение, а не заявку.
"""
import re

from .dates import extract_range

INFO_STARTS = (
    "как ", "где ", "что ", "почему", "когда ", "зачем", "сколько", "кто ",
    "какой", "какая", "какие", "какое", "можно ли", "подскажи", "расскажи",
)
WANT_WORDS = (
    "хочу", "нужен", "нужна", "нужно", "оформи", "возьми", "подай", "запроси",
    "создай", "сделай", "дай ", "выдай", "отправь", "запрос",
)
NEXT_STEP_PHRASES = (
    "следующий шаг", "следующие шаги", "что дальше", "что делать дальше",
    "с чего начать", "мой прогресс", "мои этапы", "этапы адаптации",
    "чек-лист", "чеклист", "что мне делать",
)
STATUS_PHRASES = (
    "статус", "мои доступ", "мои права", "какие у меня", "что с моим доступ",
    "что с доступ", "выдан", "есть ли доступ", "получил",
)
LEAVE_WORDS = ("отгул", "отпуск", "выходной", "отсутств")

SYSTEM_ALIASES = {
    "gitlab": "GitLab", "гитлаб": "GitLab",
    "jira": "Jira", "жира": "Jira", "джира": "Jira",
    "vpn": "VPN", "впн": "VPN",
    "confluence": "Confluence", "конфлюенс": "Confluence",
    "grafana": "Grafana", "графана": "Grafana",
}

_REASON = re.compile(r"(?:причина|по причине|потому что)[:\s]+(.+)$")


def find_system(low):
    for alias, name in SYSTEM_ALIASES.items():
        if alias in low:
            return name
    return None


def detect(text, today):
    low = " ".join((text or "").lower().split())
    info = low.startswith(INFO_STARTS)
    want = any(word in low for word in WANT_WORDS)

    if any(phrase in low for phrase in NEXT_STEP_PHRASES):
        return {"intent": "next_step"}

    system = find_system(low)
    if "доступ" in low or system:
        if "доступ" in low and any(phrase in low for phrase in STATUS_PHRASES):
            return {"intent": "access_status"}
        if system and not info and (want or "доступ" in low):
            return {"intent": "access_request", "system": system}

    if any(word in low for word in LEAVE_WORDS):
        dates = extract_range(low, today)
        wants_action = (dates is not None or want) and not (info and dates is None)
        reason_match = _REASON.search(low)
        reason = reason_match.group(1).strip()[:200] if reason_match else ""
        return {"intent": "leave", "dates": dates, "wants_action": wants_action,
                "reason": reason}

    return {"intent": "kb"}
