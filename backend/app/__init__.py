import os

from flask import Flask, jsonify, send_from_directory

from . import api, auth, db
from .config import Config
from .seed import seed_if_empty


def create_app(overrides=None):
    app = Flask(__name__, static_folder=None)
    app.config.from_object(Config)
    if overrides:
        app.config.update(overrides)

    app.json.ensure_ascii = False
    app.teardown_appcontext(db.close_db)
    app.register_blueprint(auth.bp)
    app.register_blueprint(api.bp)

    static_dir = app.config["STATIC_DIR"]
    if static_dir and os.path.isdir(static_dir):
        _serve_frontend(app, os.path.abspath(static_dir))

    with app.app_context():
        db.init_db()
        if app.config["SEED_ON_START"]:
            seed_if_empty()

    return app


def _serve_frontend(app, static_dir):
    """Отдаёт собранный интерфейс. Неизвестные пути ведут на index.html (SPA)."""

    @app.get("/", defaults={"path": ""})
    @app.get("/<path:path>")
    def frontend(path):
        if path.startswith("api/"):
            return jsonify({"error": "Не найдено"}), 404
        if path and os.path.isfile(os.path.join(static_dir, path)):
            return send_from_directory(static_dir, path)
        return send_from_directory(static_dir, "index.html")
