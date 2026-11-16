"""Настройки приложения. Всё берётся из переменных окружения (см. .env.example)."""
import os


class Config:
    # Путь к файлу SQLite. В проде заменяется на PostgreSQL (см. docs/architecture.md).
    DATABASE = os.environ.get("DATABASE_PATH", "ai_buddy.db")

    # Заполнять БД тестовыми данными при первом запуске.
    SEED_ON_START = os.environ.get("SEED_ON_START", "1") == "1"

    # Минимальная уверенность поиска по базе знаний (0..1), чтобы ответить самому.
    # Ниже порога вопрос уходит наставнику.
    KB_MIN_SCORE = float(os.environ.get("KB_MIN_SCORE", "0.5"))

    # Сколько минут наставника экономит один ответ без его участия (для метрик).
    MINUTES_SAVED_PER_ANSWER = int(os.environ.get("MINUTES_SAVED_PER_ANSWER", "10"))

    # Максимальная длительность отгула по тестовой инструкции, дней.
    MAX_LEAVE_DAYS = int(os.environ.get("MAX_LEAVE_DAYS", "14"))

    # Для тестов: зафиксировать «сегодня» (формат YYYY-MM-DD). Пусто = настоящая дата.
    TODAY = os.environ.get("TODAY", "")

    # Сколько часов живёт токен входа.
    TOKEN_TTL_HOURS = int(os.environ.get("TOKEN_TTL_HOURS", "12"))

    # Папка с собранным фронтендом. Если существует, Flask отдаёт её сам.
    STATIC_DIR = os.environ.get("STATIC_DIR", "")

    # Токен для вызова крон-задач (имитация ИИ-крона). Пусто = вызов по HTTP выключен.
    CRON_TOKEN = os.environ.get("CRON_TOKEN", "")

    # Необязательный LLM. none = ответы только из базы знаний, ключ не нужен.
    # anthropic | openai (любой OpenAI-совместимый сервер через LLM_BASE_URL)
    LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "none")
    LLM_MODEL = os.environ.get("LLM_MODEL", "")
    LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
    LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")
    # Таймаут вызова LLM, секунд. По истечении ответ берётся из базы знаний.
    LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "8"))
