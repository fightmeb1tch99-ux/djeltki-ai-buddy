"""Работа с SQLite: подключение и схема."""
import sqlite3

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('intern', 'mentor')),
    mentor_id INTEGER REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS tokens (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS kb_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    keywords TEXT NOT NULL DEFAULT '',
    audience TEXT NOT NULL DEFAULT 'all' CHECK (audience IN ('all', 'mentor')),
    source TEXT NOT NULL DEFAULT 'seed' CHECK (source IN ('seed', 'mentor')),
    times_used INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    intern_id INTEGER NOT NULL REFERENCES users(id),
    text TEXT NOT NULL,
    signature TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('answered_auto', 'pending', 'answered_by_mentor')),
    answer TEXT,
    kb_entry_id INTEGER REFERENCES kb_entries(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    answered_at TEXT
);

-- История чата: сообщения пользователя и помощника, карточки действий.
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    kind TEXT NOT NULL DEFAULT 'text',
    text TEXT NOT NULL,
    payload TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS leave_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT,
    intern_id INTEGER NOT NULL REFERENCES users(id),
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'submitted'
        CHECK (status IN ('submitted', 'approved', 'rejected')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS access_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    intern_id INTEGER NOT NULL REFERENCES users(id),
    system TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'requested' CHECK (status IN ('requested', 'granted')),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (intern_id, system)
);

CREATE TABLE IF NOT EXISTS stages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position INTEGER NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT NOT NULL
);

-- Шаги чек-листа. link = 'access:GitLab' значит: шаг закрывается сам, когда доступ выдан.
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stage_id INTEGER NOT NULL REFERENCES stages(id),
    position INTEGER NOT NULL,
    title TEXT NOT NULL,
    link TEXT
);

CREATE TABLE IF NOT EXISTS intern_tasks (
    intern_id INTEGER NOT NULL REFERENCES users(id),
    task_id INTEGER NOT NULL REFERENCES tasks(id),
    status TEXT NOT NULL DEFAULT 'todo' CHECK (status IN ('todo', 'done')),
    done_at TEXT,
    PRIMARY KEY (intern_id, task_id)
);

-- Имитация Clickstream: события продукта для метрик пользы.
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    props TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Имитация feature flags (runtime).
CREATE TABLE IF NOT EXISTS feature_flags (
    name TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    text TEXT NOT NULL,
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(SCHEMA)
    db.commit()
