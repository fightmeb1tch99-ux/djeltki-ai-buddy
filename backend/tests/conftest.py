import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app  # noqa: E402


@pytest.fixture
def app(tmp_path):
    return create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "test.db"),
            "SEED_ON_START": True,
            "TODAY": "2026-11-11",
        }
    )


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def login(client):
    """login('intern1') -> заголовки с токеном."""

    def _login(username, password="demo"):
        response = client.post("/api/login", json={"username": username, "password": password})
        assert response.status_code == 200, response.get_json()
        return {"Authorization": "Bearer " + response.get_json()["token"]}

    return _login


@pytest.fixture
def intern1(login):
    return login("intern1")


@pytest.fixture
def intern2(login):
    return login("intern2")


@pytest.fixture
def mentor(login):
    return login("mentor1")
