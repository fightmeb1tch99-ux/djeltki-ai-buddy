def stage_task(client, headers, title_part):
    stages = client.get("/api/stages", headers=headers).get_json()["stages"]
    for stage in stages:
        for task in stage["tasks"]:
            if title_part in task["title"]:
                return task
    raise AssertionError(title_part)


def manual_task_ids(client, headers):
    stages = client.get("/api/stages", headers=headers).get_json()["stages"]
    return [t["id"] for s in stages for t in s["tasks"] if not t["auto"]]


def test_access_status_seeded(client, intern1):
    body = client.get("/api/access", headers=intern1).get_json()
    statuses = {item["system"]: item["status"] for item in body["items"]}
    assert statuses == {"GitLab": "granted", "Jira": "requested"}
    assert "VPN" in body["available_systems"]


def test_request_access_creates_once(client, intern1):
    first = client.post("/api/access", json={"system": "VPN"}, headers=intern1).get_json()
    assert first["created"] is True and first["status"] == "requested"
    second = client.post("/api/access", json={"system": "VPN"}, headers=intern1).get_json()
    assert second["created"] is False and second["id"] == first["id"]


def test_request_access_unknown_system(client, intern1):
    assert client.post("/api/access", json={"system": "Mars"}, headers=intern1).status_code == 400
    assert client.post("/api/access", headers=intern1).status_code == 400


def test_mentor_sees_pending_and_grants_access(client, intern1, mentor):
    pending = client.get("/api/access/pending", headers=mentor).get_json()["items"]
    assert [(p["system"], p["full_name"]) for p in pending] == [("Jira", "Анна Тестова")]

    jira_id = pending[0]["id"]
    granted = client.post(f"/api/access/{jira_id}/grant", headers=mentor)
    assert granted.get_json()["status"] == "granted"
    after = client.get("/api/access", headers=intern1).get_json()["items"]
    assert all(item["status"] == "granted" for item in after)
    assert client.get("/api/access/pending", headers=mentor).get_json()["items"] == []

    history = client.get("/api/chat/history", headers=intern1).get_json()["items"]
    assert history[-1]["text"] == "Доступ к Jira выдан."

    assert client.post("/api/access/9999/grant", headers=mentor).status_code == 404
    assert client.post(f"/api/access/{jira_id}/grant", headers=intern1).status_code == 403
    assert client.get("/api/access/pending", headers=intern1).status_code == 403


def test_stages_initial_state(client, intern1):
    body = client.get("/api/stages", headers=intern1).get_json()
    assert len(body["stages"]) == 4
    # GitLab уже выдан, поэтому его шаг закрыт сам: 1 из 12.
    assert body["progress_percent"] == 8
    stage2 = body["stages"][1]
    assert [t["status"] for t in stage2["tasks"]] == ["done", "in_progress", "todo", "todo"]
    assert stage2["status"] == "in_progress" and stage2["done_count"] == 1
    assert body["stages"][0]["status"] == "todo"
    assert body["next_step"]["stage_title"] == "Знакомство с командой"
    assert body["next_step"]["waiting"] is False


def test_other_intern_starts_from_zero(client, intern2):
    body = client.get("/api/stages", headers=intern2).get_json()
    assert body["progress_percent"] == 0
    assert all(t["status"] == "todo" for s in body["stages"] for t in s["tasks"])


def test_mark_task_done_and_reopen(client, intern2):
    task = stage_task(client, intern2, "Познакомиться с наставником")
    done = client.patch(f"/api/tasks/{task['id']}", json={"done": True}, headers=intern2)
    assert done.status_code == 200
    assert done.get_json()["progress_percent"] == 8
    assert done.get_json()["stages"][0]["status"] == "in_progress"
    assert done.get_json()["next_step"]["title"] != task["title"]

    reopened = client.patch(f"/api/tasks/{task['id']}", json={"done": False}, headers=intern2)
    assert reopened.get_json()["progress_percent"] == 0


def test_task_validation(client, intern1):
    auto_task = stage_task(client, intern1, "Запросить доступ к Jira")
    assert auto_task["auto"] is True
    assert client.patch(f"/api/tasks/{auto_task['id']}", json={"done": True},
                        headers=intern1).status_code == 409
    manual = stage_task(client, intern1, "Настроить рабочее окружение")
    assert client.patch(f"/api/tasks/{manual['id']}", json={"done": "да"},
                        headers=intern1).status_code == 400
    assert client.patch("/api/tasks/999", json={"done": True}, headers=intern1).status_code == 404


def test_requesting_access_moves_linked_task(client, intern2):
    assert stage_task(client, intern2, "доступ к VPN")["status"] == "todo"
    client.post("/api/access", json={"system": "VPN"}, headers=intern2)
    assert stage_task(client, intern2, "доступ к VPN")["status"] == "in_progress"


def test_next_step_waits_when_only_approvals_remain(client, intern1):
    client.post("/api/access", json={"system": "VPN"}, headers=intern1)
    for task_id in manual_task_ids(client, intern1):
        client.patch(f"/api/tasks/{task_id}", json={"done": True}, headers=intern1)
    body = client.get("/api/stages", headers=intern1).get_json()
    assert body["next_step"]["waiting"] is True
    assert body["progress_percent"] == 83  # 10 из 12


def test_all_done_has_no_next_step(client, intern1, mentor):
    client.post("/api/access", json={"system": "VPN"}, headers=intern1)
    for item in client.get("/api/access/pending", headers=mentor).get_json()["items"]:
        client.post(f"/api/access/{item['id']}/grant", headers=mentor)
    for task_id in manual_task_ids(client, intern1):
        client.patch(f"/api/tasks/{task_id}", json={"done": True}, headers=intern1)
    body = client.get("/api/stages", headers=intern1).get_json()
    assert body["progress_percent"] == 100 and body["next_step"] is None
    assert all(s["status"] == "done" for s in body["stages"])


def test_mentor_sees_intern_progress(client, intern2, mentor):
    task = stage_task(client, intern2, "Познакомиться с наставником")
    client.patch(f"/api/tasks/{task['id']}", json={"done": True}, headers=intern2)
    items = client.get("/api/mentor/interns", headers=mentor).get_json()["items"]
    by_name = {i["full_name"]: i for i in items}
    assert by_name["Анна Тестова"]["progress_percent"] == 8
    assert by_name["Борис Пробников"]["progress_percent"] == 8
    assert by_name["Борис Пробников"]["next_step"]["title"]
