"""Действия в чате: предложение -> подтверждение -> результат сервиса."""

LEAVE = "Оформи отгул с 20 по 22 ноября, причина: личные дела"
LEAVE_SHORT = "Оформи отгул с 20 по 22 ноября"


def say(client, headers, text):
    response = client.post("/api/chat", json={"message": text}, headers=headers)
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def confirm(client, headers, message_id):
    return client.post(f"/api/actions/{message_id}/confirm", headers=headers)


def cancel(client, headers, message_id):
    return client.post(f"/api/actions/{message_id}/cancel", headers=headers)


def test_leave_full_flow_from_request_to_result(client, intern1):
    proposal = say(client, intern1, LEAVE)
    assert proposal["status"] == "proposal"
    card = proposal["message"]["payload"]
    assert card["state"] == "pending"
    assert card["args"] == {"start_date": "2026-11-20", "end_date": "2026-11-22",
                            "reason": "личные дела"}
    assert "20–22 ноября" in card["lines"][0]
    # До подтверждения ничего не создано.
    assert client.get("/api/leave-requests", headers=intern1).get_json()["items"] == []

    done = confirm(client, intern1, proposal["message"]["id"]).get_json()
    assert done["state"] == "done"
    assert done["result"]["external_id"].startswith("ABS-")
    assert done["proposal"]["payload"]["state"] == "done"
    assert done["message"]["kind"] == "result"
    assert done["result"]["external_id"] in done["message"]["text"]

    saved = client.get("/api/leave-requests", headers=intern1).get_json()["items"]
    assert len(saved) == 1 and saved[0]["external_id"] == done["result"]["external_id"]

    kinds = [m["kind"] for m in client.get("/api/chat/history", headers=intern1).get_json()["items"]]
    assert kinds == ["text", "proposal", "result"]


def test_leave_without_dates_asks_for_them(client, intern1):
    reply = say(client, intern1, "Хочу отгул")
    assert reply["status"] == "needs_input"
    assert "На какие даты" in reply["answer"]


def test_leave_question_gets_explanation_and_hint(client, intern1):
    reply = say(client, intern1, "Как оформить отгул?")
    assert reply["status"] == "answered"
    assert reply["suggested_action"] == "leave_request"
    assert client.get("/api/leave-requests", headers=intern1).get_json()["items"] == []


def test_invalid_leave_is_rejected_before_card(client, intern1):
    past = say(client, intern1, "оформи отгул 1.11.2026")
    assert past["status"] == "rejected" and "задним числом" in past["answer"]
    too_long = say(client, intern1, "оформи отгул с 20 ноября по 20 декабря")
    assert too_long["status"] == "rejected" and "14 дней" in too_long["answer"]


def test_cancel_creates_nothing_and_cannot_be_confirmed_later(client, intern1):
    proposal = say(client, intern1, LEAVE)["message"]["id"]
    cancelled = cancel(client, intern1, proposal).get_json()
    assert cancelled["state"] == "cancelled"
    assert cancelled["proposal"]["payload"]["state"] == "cancelled"
    assert client.get("/api/leave-requests", headers=intern1).get_json()["items"] == []
    assert confirm(client, intern1, proposal).status_code == 409
    assert cancel(client, intern1, proposal).status_code == 409


def test_cannot_confirm_someone_elses_card(client, intern1, intern2, mentor):
    proposal = say(client, intern1, LEAVE)["message"]["id"]
    assert confirm(client, intern2, proposal).status_code == 404
    assert confirm(client, mentor, proposal).status_code == 403
    assert confirm(client, intern1, 99999).status_code == 404
    assert client.get("/api/leave-requests", headers=intern2).get_json()["items"] == []


def test_confirm_reports_failure_if_state_changed_meanwhile(client, intern1):
    proposal = say(client, intern1, LEAVE)["message"]["id"]
    client.post("/api/leave-requests", headers=intern1,
                json={"start_date": "2026-11-21", "end_date": "2026-11-21"})
    result = confirm(client, intern1, proposal).get_json()
    assert result["state"] == "failed"
    assert "уже есть заявка" in result["error"]
    assert result["proposal"]["payload"]["state"] == "failed"
    assert len(client.get("/api/leave-requests", headers=intern1).get_json()["items"]) == 1


def test_access_request_flow_moves_checklist(client, intern2):
    proposal = say(client, intern2, "Запроси доступ к VPN")
    assert proposal["status"] == "proposal"
    assert proposal["message"]["payload"]["args"] == {"system": "VPN"}

    done = confirm(client, intern2, proposal["message"]["id"]).get_json()
    assert done["state"] == "done" and done["result"]["status"] == "requested"
    assert "ждёт согласования" in done["message"]["text"]

    items = client.get("/api/access", headers=intern2).get_json()["items"]
    assert [(i["system"], i["status"]) for i in items] == [("VPN", "requested")]
    tasks = [t for s in client.get("/api/stages", headers=intern2).get_json()["stages"]
             for t in s["tasks"] if "VPN" in t["title"]]
    assert tasks[0]["status"] == "in_progress"


def test_access_already_requested_is_not_proposed_again(client, intern1):
    reply = say(client, intern1, "Запроси доступ к Jira")
    assert reply["status"] == "rejected"
    assert "уже запрошен" in reply["answer"]


def test_access_status_and_next_step_answers(client, intern1):
    status = say(client, intern1, "Какие у меня доступы?")
    assert status["status"] == "info"
    assert "GitLab: выдан" in status["answer"] and "Jira: ждёт согласования" in status["answer"]

    step = say(client, intern1, "Что мне делать дальше?")
    assert step["status"] == "info"
    assert "Прогресс: 8%" in step["answer"]
    assert step["message"]["payload"]["next_step"]["stage_title"] == "Знакомство с командой"


def test_empty_access_status_hint(client, intern2):
    reply = say(client, intern2, "Какие у меня доступы?")
    assert "Запроси доступ к GitLab" in reply["answer"]


def test_next_step_when_everything_done(client, intern1, mentor):
    client.post("/api/access", json={"system": "VPN"}, headers=intern1)
    for item in client.get("/api/access/pending", headers=mentor).get_json()["items"]:
        client.post(f"/api/access/{item['id']}/grant", headers=mentor)
    for stage in client.get("/api/stages", headers=intern1).get_json()["stages"]:
        for task in stage["tasks"]:
            if not task["auto"]:
                client.patch(f"/api/tasks/{task['id']}", json={"done": True}, headers=intern1)
    assert "пройдены" in say(client, intern1, "что дальше?")["answer"]


def test_next_step_when_waiting_for_approval(client, intern1):
    client.post("/api/access", json={"system": "VPN"}, headers=intern1)
    for stage in client.get("/api/stages", headers=intern1).get_json()["stages"]:
        for task in stage["tasks"]:
            if not task["auto"]:
                client.patch(f"/api/tasks/{task['id']}", json={"done": True}, headers=intern1)
    assert "остаётся ждать" in say(client, intern1, "что дальше?")["answer"]


def test_flag_off_disables_actions(client, intern1, mentor):
    client.put("/api/flags/chat_actions", json={"enabled": False}, headers=mentor)
    reply = say(client, intern1, LEAVE_SHORT)
    assert reply["status"] == "answered"  # обычный ответ из базы знаний, без карточки


def test_mentor_chat_has_no_actions(client, mentor):
    reply = say(client, mentor, LEAVE_SHORT)
    assert reply["status"] == "answered" and reply["message"]["kind"] == "answer"


def test_history_is_private(client, intern1, intern2):
    say(client, intern1, "Как оформить отгул?")
    assert len(client.get("/api/chat/history", headers=intern1).get_json()["items"]) == 2
    assert client.get("/api/chat/history", headers=intern2).get_json()["items"] == []


def test_mentor_reply_and_decisions_land_in_intern_chat(client, intern1, mentor):
    say(client, intern1, "Где взять пропуск в офис?")
    qid = client.get("/api/mentor/digest", headers=mentor).get_json()["items"][0]["question_id"]
    client.post("/api/mentor/digest/answer", headers=mentor,
                json={"question_id": qid, "answer": "Пишите в чат АХО."})

    leave = say(client, intern1, LEAVE)["message"]["id"]
    request_id = confirm(client, intern1, leave).get_json()["result"]["id"]
    client.post(f"/api/leave-requests/{request_id}/decision", json={"decision": "approve"},
                headers=mentor)

    history = client.get("/api/chat/history", headers=intern1).get_json()["items"]
    texts = [m["text"] for m in history if m["role"] == "assistant"]
    assert any("Пишите в чат АХО." in t for t in texts)
    assert any(m["kind"] == "mentor_reply" for m in history)
    assert any("одобрена" in t for t in texts)

    client.post("/api/leave-requests/9999/decision", json={"decision": "reject"}, headers=mentor)


def test_reject_decision_message(client, intern1, mentor):
    leave = say(client, intern1, LEAVE)["message"]["id"]
    request_id = confirm(client, intern1, leave).get_json()["result"]["id"]
    client.post(f"/api/leave-requests/{request_id}/decision", json={"decision": "reject"},
                headers=mentor)
    texts = [m["text"] for m in client.get("/api/chat/history", headers=intern1).get_json()["items"]]
    assert any("отклонена" in t for t in texts)
