"""Имитация корпоративной авторизации и ролевой модели.

В Авито авторизация и роли уже есть (см. условия кейса), поэтому здесь только
минимальная заглушка: логин -> токен -> роль intern / mentor.
"""
import secrets
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request
from werkzeug.security import check_password_hash

from .db import get_db

bp = Blueprint("auth", __name__)


def error(message, status=400):
    return jsonify({"error": message}), status


def public_user(row):
    return {
        "id": row["id"],
        "username": row["username"],
        "full_name": row["full_name"],
        "role": row["role"],
    }


def _token():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    return header[len("Bearer "):].strip()


def _current_user():
    token = _token()
    if token is None:
        return None
    ttl = current_app.config["TOKEN_TTL_HOURS"]
    return get_db().execute(
        "SELECT u.* FROM tokens t JOIN users u ON u.id = t.user_id "
        "WHERE t.token = ? AND t.created_at > datetime('now', ?)",
        (token, f"-{ttl} hours"),
    ).fetchone()


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = _current_user()
        if user is None:
            return error("Требуется авторизация", 401)
        g.user = user
        return fn(*args, **kwargs)

    return wrapper


def role_required(role):
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            if g.user["role"] != role:
                return error("Недостаточно прав", 403)
            return fn(*args, **kwargs)

        return wrapper

    return decorator


@bp.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE username = ?", (str(data.get("username", "")),)
    ).fetchone()
    if user is None or not check_password_hash(
        user["password_hash"], str(data.get("password", ""))
    ):
        return error("Неверный логин или пароль", 401)

    token = secrets.token_hex(16)
    db.execute("INSERT INTO tokens (token, user_id) VALUES (?, ?)", (token, user["id"]))
    db.commit()
    return jsonify({"token": token, "user": public_user(user)})


@bp.post("/api/logout")
@login_required
def logout():
    db = get_db()
    db.execute("DELETE FROM tokens WHERE token = ?", (_token(),))
    db.commit()
    return jsonify({"status": "ok"})


@bp.get("/api/me")
@login_required
def me():
    return jsonify(public_user(g.user))
