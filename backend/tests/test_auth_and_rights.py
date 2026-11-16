from app import create_app


def test_health_is_public(client):
    assert client.get("/api/health").get_json() == {"status": "ok"}


def test_login_ok_and_me(client, intern1):
    response = client.get("/api/me", headers=intern1)
    assert response.status_code == 200
    assert response.get_json()["role"] == "intern"


def test_login_wrong_password(client):
    response = client.post("/api/login", json={"username": "intern1", "password": "nope"})
    assert response.status_code == 401


def test_login_unknown_user_and_empty_body(client):
    assert client.post("/api/login", json={"username": "ghost", "password": "x"}).status_code == 401
    assert client.post("/api/login").status_code == 401


def test_requires_token(client):
    assert client.get("/api/stages").status_code == 401
    assert client.get("/api/me", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/api/me", headers={"Authorization": "Basic abc"}).status_code == 401


def test_intern_cannot_use_mentor_endpoints(client, intern1):
    for url in ("/api/mentor/digest", "/api/mentor/interns", "/api/metrics"):
        assert client.get(url, headers=intern1).status_code == 403


def test_mentor_cannot_use_intern_endpoints(client, mentor):
    assert client.get("/api/stages", headers=mentor).status_code == 403
    assert client.get("/api/access", headers=mentor).status_code == 403
    assert client.get("/api/questions", headers=mentor).status_code == 403


def test_intern_does_not_see_mentor_only_knowledge(client, intern1, mentor):
    question = {"message": "Как провести встречу 1:1 со стажёром?"}
    intern_answer = client.post("/api/chat", json=question, headers=intern1).get_json()
    assert intern_answer["status"] == "escalated"
    assert "начни с вопроса" not in intern_answer["answer"]

    mentor_answer = client.post("/api/chat", json=question, headers=mentor).get_json()
    assert mentor_answer["status"] == "answered"
    assert "начни с вопроса" in mentor_answer["answer"]


def test_mentor_chat_not_found_is_not_stored(client, mentor):
    answer = client.post("/api/chat", json={"message": "расскажи про погоду"}, headers=mentor)
    assert answer.get_json()["status"] == "not_found"
    assert client.get("/api/mentor/digest", headers=mentor).get_json()["items"] == []


def test_tools_list(client, intern1):
    names = {t["name"] for t in client.get("/api/tools", headers=intern1).get_json()["items"]}
    assert {"create_leave_request", "request_access", "get_access_status"} <= names


def test_seed_is_idempotent_and_can_be_disabled(tmp_path):
    path = str(tmp_path / "twice.db")
    create_app({"DATABASE": path, "SEED_ON_START": True})
    second = create_app({"DATABASE": path, "SEED_ON_START": True})
    with second.app_context():
        from app.db import get_db

        assert get_db().execute("SELECT COUNT(*) FROM users").fetchone()[0] == 3

    empty = create_app({"DATABASE": str(tmp_path / "empty.db"), "SEED_ON_START": False})
    with empty.app_context():
        from app.db import get_db

        assert get_db().execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
