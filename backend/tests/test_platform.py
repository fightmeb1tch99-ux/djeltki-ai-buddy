"""LLM-слой, feature flags, события, крон, токены и раздача фронтенда."""
import pytest

from app import cron, llm
from app.db import get_db

ASK = {"message": "Как настроить рабочее окружение?"}


@pytest.fixture
def llm_app(app, monkeypatch):
    app.config.update({"LLM_PROVIDER": "anthropic", "LLM_API_KEY": "test-key",
                       "LLM_MODEL": "test-model"})
    calls = []

    def fake_post(url, headers, body, timeout):
        calls.append({"url": url, "headers": headers, "body": body, "timeout": timeout})
        return {"content": [{"text": "Ответ от LLM по базе знаний."}]}

    monkeypatch.setattr(llm, "_post", fake_post)
    app.fake_llm_calls = calls
    return app


def test_llm_not_configured_by_default(app):
    assert llm.is_configured(app.config) is False
    assert llm.is_configured({"LLM_PROVIDER": "anthropic", "LLM_API_KEY": ""}) is False


def test_llm_answer_is_grounded_and_marked(llm_app, intern1):
    body = llm_app.test_client().post("/api/chat", json=ASK, headers=intern1).get_json()
    assert body["status"] == "answered"
    assert body["answer"] == "Ответ от LLM по базе знаний."
    assert body["message"]["payload"]["generated"] is True

    call = llm_app.fake_llm_calls[0]
    assert call["url"].endswith("/v1/messages")
    assert call["headers"]["x-api-key"] == "test-key"
    prompt = call["body"]["messages"][0]["content"]
    assert "<kb>" in prompt and "<question>" in prompt and "README" in prompt
    assert "NO_ANSWER" in call["body"]["system"]
    assert call["timeout"] == llm_app.config["LLM_TIMEOUT"]


def test_llm_no_answer_escalates_to_mentor(llm_app, intern1, monkeypatch):
    monkeypatch.setattr(llm, "_post", lambda *a: {"content": [{"text": "NO_ANSWER"}]})
    body = llm_app.test_client().post("/api/chat", json=ASK, headers=intern1).get_json()
    assert body["status"] == "escalated"


def test_llm_failure_falls_back_to_knowledge_base(llm_app, intern1, mentor, monkeypatch):
    def broken(*args):
        raise llm.LLMError("timeout")

    monkeypatch.setattr(llm, "_post", broken)
    client = llm_app.test_client()
    body = client.post("/api/chat", json=ASK, headers=intern1).get_json()
    assert body["status"] == "answered" and "README" in body["answer"]
    assert body["message"]["payload"]["generated"] is False
    events = client.get("/api/metrics", headers=mentor).get_json()["events"]
    assert events["llm_error"] == 1


def test_llm_flag_off_skips_llm(llm_app, intern1, mentor):
    client = llm_app.test_client()
    client.put("/api/flags/llm_answers", json={"enabled": False}, headers=mentor)
    body = client.post("/api/chat", json=ASK, headers=intern1).get_json()
    assert "README" in body["answer"] and llm_app.fake_llm_calls == []


def test_llm_not_called_when_nothing_matches(llm_app, intern1):
    body = llm_app.test_client().post(
        "/api/chat", json={"message": "расскажи про погоду на марсе"}, headers=intern1
    ).get_json()
    assert body["status"] == "escalated" and llm_app.fake_llm_calls == []


def test_openai_provider_and_bad_formats(app, intern1, monkeypatch):
    app.config.update({"LLM_PROVIDER": "openai", "LLM_API_KEY": "k",
                       "LLM_BASE_URL": "http://llm.local/v1/"})
    seen = {}

    def fake_post(url, headers, body, timeout):
        seen.update(url=url, headers=headers, body=body)
        return {"choices": [{"message": {"content": "OK из OpenAI-совместимого"}}]}

    monkeypatch.setattr(llm, "_post", fake_post)
    body = app.test_client().post("/api/chat", json=ASK, headers=intern1).get_json()
    assert body["answer"] == "OK из OpenAI-совместимого"
    assert seen["url"] == "http://llm.local/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer k"

    monkeypatch.setattr(llm, "_post", lambda *a: {"unexpected": True})
    with pytest.raises(llm.LLMError):
        llm.answer_from_context(app.config, "q", [])
    app.config["LLM_PROVIDER"] = "anthropic"
    with pytest.raises(llm.LLMError):
        llm.answer_from_context(app.config, "q", [])


def test_real_post_failure_is_wrapped(app):
    with pytest.raises(llm.LLMError):
        llm._post("http://127.0.0.1:9/", {}, {}, 0.5)


def test_flags_api(client, intern1, mentor):
    assert client.get("/api/flags", headers=intern1).get_json() == {
        "llm_answers": True, "chat_actions": True}
    after = client.put("/api/flags/llm_answers", json={"enabled": False}, headers=mentor)
    assert after.get_json()["llm_answers"] is False
    assert client.put("/api/flags/llm_answers", json={"enabled": True}, headers=mentor
                      ).get_json()["llm_answers"] is True
    assert client.put("/api/flags/llm_answers", json={"enabled": False}, headers=intern1
                      ).status_code == 403
    assert client.put("/api/flags/nope", json={"enabled": True}, headers=mentor).status_code == 404
    assert client.put("/api/flags/llm_answers", json={"enabled": "да"}, headers=mentor
                      ).status_code == 400


def test_events_are_counted_in_metrics(client, intern1, mentor):
    client.post("/api/chat", json={"message": "Как оформить отгул?"}, headers=intern1)
    client.post("/api/chat", json={"message": "Где взять пропуск?"}, headers=intern1)
    card = client.post("/api/chat", json={"message": "Запроси доступ к VPN"}, headers=intern1
                       ).get_json()["message"]["id"]
    client.post(f"/api/actions/{card}/confirm", headers=intern1)
    events = client.get("/api/metrics", headers=mentor).get_json()["events"]
    assert events["chat_question"] == 3
    assert events["answered_auto"] == 1 and events["escalated"] == 1
    assert events["action_proposed"] == 1 and events["action_confirmed"] == 1


def test_avg_minutes_to_answer_reported(client, intern1, mentor, app):
    client.post("/api/chat", json={"message": "Где взять пропуск?"}, headers=intern1)
    qid = client.get("/api/mentor/digest", headers=mentor).get_json()["items"][0]["question_id"]
    with app.app_context():
        get_db().execute("UPDATE questions SET created_at = datetime('now', '-30 minutes')")
        get_db().commit()
    client.post("/api/mentor/digest/answer", json={"question_id": qid, "answer": "ок"},
                headers=mentor)
    metrics = client.get("/api/metrics", headers=mentor).get_json()
    assert 29 <= metrics["avg_minutes_to_mentor_answer"] <= 31
    assert metrics["events"]["mentor_answered"] == 1


def test_cron_digest_creates_notification(client, app, intern1, intern2, mentor):
    with app.app_context():
        assert cron.run_digest(get_db()) == 0  # вопросов нет — уведомления нет
    client.post("/api/chat", json={"message": "Где взять пропуск?"}, headers=intern1)
    client.post("/api/chat", json={"message": "пропуск где взять"}, headers=intern2)
    with app.app_context():
        assert cron.run_digest(get_db()) == 1
    items = client.get("/api/notifications", headers=mentor).get_json()["items"]
    assert len(items) == 1 and "Ждут ответа: 1" in items[0]["text"] and "2" in items[0]["text"]
    assert items[0]["is_read"] == 0
    client.post("/api/notifications/read", headers=mentor)
    assert client.get("/api/notifications", headers=mentor).get_json()["items"][0]["is_read"] == 1
    assert client.get("/api/notifications", headers=intern1).status_code == 403


def test_cron_endpoint_needs_token(client, app, intern1):
    client.post("/api/chat", json={"message": "Где взять пропуск?"}, headers=intern1)
    assert client.post("/api/internal/cron/digest").status_code == 403  # токен не настроен
    app.config["CRON_TOKEN"] = "secret"
    assert client.post("/api/internal/cron/digest",
                       headers={"X-Cron-Token": "wrong"}).status_code == 403
    ok = client.post("/api/internal/cron/digest", headers={"X-Cron-Token": "secret"})
    assert ok.get_json() == {"notifications_created": 1}


def test_token_expires_and_logout(client, app, login):
    headers = login("intern1")
    assert client.get("/api/me", headers=headers).status_code == 200
    with app.app_context():
        get_db().execute("UPDATE tokens SET created_at = datetime('now', '-13 hours')")
        get_db().commit()
    assert client.get("/api/me", headers=headers).status_code == 401

    fresh = login("intern1")
    assert client.post("/api/logout", headers=fresh).status_code == 200
    assert client.get("/api/me", headers=fresh).status_code == 401


def test_frontend_is_served_when_built(tmp_path):
    from app import create_app

    static = tmp_path / "dist"
    static.mkdir()
    (static / "index.html").write_text("<html>SPA</html>", encoding="utf-8")
    (static / "app.js").write_text("console.log(1)", encoding="utf-8")
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "x.db"),
                      "STATIC_DIR": str(static)})
    client = app.test_client()
    assert b"SPA" in client.get("/").data
    assert b"console.log" in client.get("/app.js").data
    assert b"SPA" in client.get("/some/client/route").data
    missing = client.get("/api/unknown")
    assert missing.status_code == 404 and missing.get_json()["error"]
    assert client.get("/api/health").get_json() == {"status": "ok"}
