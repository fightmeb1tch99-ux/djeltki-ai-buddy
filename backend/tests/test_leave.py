GOOD = {"start_date": "2026-11-20", "end_date": "2026-11-21", "reason": "Личные дела"}


def create(client, headers, **overrides):
    return client.post("/api/leave-requests", json={**GOOD, **overrides}, headers=headers)


def test_leave_created_and_saved(client, intern1):
    response = create(client, intern1)
    assert response.status_code == 201
    body = response.get_json()
    assert body["status"] == "submitted"
    assert body["external_id"].startswith("ABS-")

    items = client.get("/api/leave-requests", headers=intern1).get_json()["items"]
    assert len(items) == 1 and items[0]["external_id"] == body["external_id"]


def test_leave_validation(client, intern1):
    assert create(client, intern1, start_date="вчера").status_code == 400
    assert create(client, intern1, end_date="2026-11-19").status_code == 400
    assert create(client, intern1, start_date="2026-11-01", end_date="2026-11-02").status_code == 400
    assert create(client, intern1, end_date="2026-12-31").status_code == 400
    assert create(client, intern1, reason="я" * 201).status_code == 400
    assert client.post("/api/leave-requests", headers=intern1).status_code == 400


def test_leave_overlap_is_conflict_but_rejected_frees_dates(client, intern1, mentor):
    first = create(client, intern1).get_json()
    assert create(client, intern1, start_date="2026-11-21", end_date="2026-11-22").status_code == 409

    client.post(
        f"/api/leave-requests/{first['id']}/decision", json={"decision": "reject"}, headers=mentor
    )
    assert create(client, intern1).status_code == 201


def test_mentor_cannot_create_leave(client, mentor):
    assert create(client, mentor).status_code == 403


def test_mentor_sees_and_decides_own_interns_leave(client, intern1, mentor):
    created = create(client, intern1).get_json()
    listed = client.get("/api/leave-requests", headers=mentor).get_json()["items"]
    assert listed[0]["full_name"] == "Анна Тестова"

    url = f"/api/leave-requests/{created['id']}/decision"
    assert client.post(url, json={"decision": "maybe"}, headers=mentor).status_code == 400
    approved = client.post(url, json={"decision": "approve"}, headers=mentor)
    assert approved.get_json()["status"] == "approved"
    assert client.post(url, json={"decision": "reject"}, headers=mentor).status_code == 409


def test_decision_unknown_request_and_intern_forbidden(client, intern1, mentor):
    assert client.post(
        "/api/leave-requests/999/decision", json={"decision": "approve"}, headers=mentor
    ).status_code == 404
    assert client.post(
        "/api/leave-requests/1/decision", json={"decision": "approve"}, headers=intern1
    ).status_code == 403


def test_interns_do_not_see_each_others_leave(client, intern1, intern2):
    create(client, intern1)
    assert client.get("/api/leave-requests", headers=intern2).get_json()["items"] == []


def test_leave_uses_real_today_when_not_fixed(app, intern1, client):
    app.config["TODAY"] = ""
    response = client.post(
        "/api/leave-requests",
        json={"start_date": "2000-01-01", "end_date": "2000-01-02"},
        headers=intern1,
    )
    assert response.status_code == 400
