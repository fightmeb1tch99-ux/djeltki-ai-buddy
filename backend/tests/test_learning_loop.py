"""Главный сценарий: неизвестный вопрос -> наставник отвечает один раз ->
ответ получают все и он попадает в базу знаний."""

UNKNOWN = {"message": "Где взять пропуск в офис?"}


def test_known_question_is_answered_from_kb(client, intern1):
    data = client.post("/api/chat", json={"message": "Как оформить отгул?"}, headers=intern1)
    body = data.get_json()
    assert body["status"] == "answered"
    assert "Тестовая инструкция" in body["answer"]
    assert body["suggested_action"] == "leave_request"
    assert body["source"]["origin"] == "seed"


def test_access_question_suggests_access_action(client, intern1):
    body = client.post(
        "/api/chat", json={"message": "Как запросить доступ к сервису?"}, headers=intern1
    ).get_json()
    assert body["suggested_action"] == "access_status"


def test_chat_validation(client, intern1):
    assert client.post("/api/chat", json={"message": "  "}, headers=intern1).status_code == 400
    assert client.post("/api/chat", json={"message": "я" * 501}, headers=intern1).status_code == 400
    assert client.post("/api/chat", json={}, headers=intern1).status_code == 400


def test_unknown_question_is_escalated_not_invented(client, intern1):
    body = client.post("/api/chat", json=UNKNOWN, headers=intern1).get_json()
    assert body["status"] == "escalated"
    assert body["source"] is None
    mine = client.get("/api/questions", headers=intern1).get_json()["items"]
    assert mine[0]["status"] == "pending" and mine[0]["answer"] is None


def test_full_learning_loop(client, intern1, intern2, mentor):
    # Два стажёра спрашивают одно и то же — в дайджесте это одна группа.
    client.post("/api/chat", json=UNKNOWN, headers=intern1)
    client.post("/api/chat", json={"message": "пропуск в офис где взять"}, headers=intern2)

    digest = client.get("/api/mentor/digest", headers=mentor).get_json()["items"]
    assert len(digest) == 1
    assert digest[0]["asked_count"] == 2
    assert sorted(digest[0]["interns"]) == ["Анна Тестова", "Борис Пробников"]

    # Наставник отвечает один раз.
    reply = client.post(
        "/api/mentor/digest/answer",
        json={"question_id": digest[0]["question_id"], "answer": "Тестовый ответ: пишите в чат АХО."},
        headers=mentor,
    )
    assert reply.status_code == 200
    assert reply.get_json()["closed_questions"] == 2
    assert client.get("/api/mentor/digest", headers=mentor).get_json()["items"] == []

    # Оба стажёра видят ответ у себя.
    for headers in (intern1, intern2):
        item = client.get("/api/questions", headers=headers).get_json()["items"][0]
        assert item["status"] == "answered_by_mentor"
        assert "чат АХО" in item["answer"]

    # Следующий стажёр получает ответ мгновенно, без наставника.
    again = client.post("/api/chat", json=UNKNOWN, headers=intern1).get_json()
    assert again["status"] == "answered"
    assert again["source"]["origin"] == "mentor"

    # Метрики это отражают.
    metrics = client.get("/api/metrics", headers=mentor).get_json()
    assert metrics["total_questions"] == 3
    assert metrics["answered_by_mentor"] == 2
    assert metrics["answered_without_mentor"] == 1
    assert metrics["reused_mentor_answers"] == 1
    assert metrics["mentor_minutes_saved"] == 10
    assert metrics["auto_rate"] == 0.33


def test_answer_validation(client, intern1, mentor):
    client.post("/api/chat", json=UNKNOWN, headers=intern1)
    qid = client.get("/api/mentor/digest", headers=mentor).get_json()["items"][0]["question_id"]
    url = "/api/mentor/digest/answer"
    assert client.post(url, json={"question_id": qid}, headers=mentor).status_code == 400
    assert client.post(url, json={"answer": "ok"}, headers=mentor).status_code == 400
    bad_audience = {"question_id": qid, "answer": "ok", "audience": "everyone"}
    assert client.post(url, json=bad_audience, headers=mentor).status_code == 400
    assert client.post(url, json={"question_id": 9999, "answer": "ok"}, headers=mentor).status_code == 404


def test_cannot_answer_twice(client, intern1, mentor):
    client.post("/api/chat", json=UNKNOWN, headers=intern1)
    qid = client.get("/api/mentor/digest", headers=mentor).get_json()["items"][0]["question_id"]
    payload = {"question_id": qid, "answer": "ответ"}
    assert client.post("/api/mentor/digest/answer", json=payload, headers=mentor).status_code == 200
    assert client.post("/api/mentor/digest/answer", json=payload, headers=mentor).status_code == 404


def test_mentor_answer_can_be_mentor_only(client, intern1, intern2, mentor):
    client.post("/api/chat", json=UNKNOWN, headers=intern1)
    qid = client.get("/api/mentor/digest", headers=mentor).get_json()["items"][0]["question_id"]
    client.post(
        "/api/mentor/digest/answer",
        json={"question_id": qid, "answer": "закрытый ответ", "audience": "mentor"},
        headers=mentor,
    )
    again = client.post("/api/chat", json=UNKNOWN, headers=intern2).get_json()
    assert again["status"] == "escalated"


def test_metrics_empty(client, mentor):
    metrics = client.get("/api/metrics", headers=mentor).get_json()
    assert metrics["total_questions"] == 0 and metrics["auto_rate"] == 0.0
