import sys
from pathlib import Path

import pytest

APP_SRC = Path(__file__).parents[1] / "terraform" / "modules" / "compute" / "app-src"
sys.path.insert(0, str(APP_SRC))

import app as application  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(application, "AZ_PATH", tmp_path / "az.txt")
    monkeypatch.setattr(application, "INSTANCE_ID_PATH", tmp_path / "instance-id.txt")
    application.app.config.update(TESTING=True)
    return application.app.test_client()


def test_home_page_returns_expected_response(client, tmp_path):
    (tmp_path / "az.txt").write_text("us-east-1a\n", encoding="utf-8")
    (tmp_path / "instance-id.txt").write_text("i-test123\n", encoding="utf-8")

    response = client.get("/")

    assert response.status_code == 200
    assert b"Secure, Highly Available Web Platform" in response.data
    assert b"us-east-1a" in response.data
    assert b"i-test123" in response.data


def test_health_is_database_independent(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "OK"
    assert response.mimetype == "text/plain"


def test_missing_metadata_uses_safe_fallbacks(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"unknown" in response.data


def test_unexpected_filesystem_error_uses_fallback(client, monkeypatch):
    def fail_read(*args, **kwargs):
        raise PermissionError("test-only filesystem failure")

    monkeypatch.setattr(Path, "read_text", fail_read)

    response = client.get("/")

    assert response.status_code == 200
    assert response.data.count(b"unknown") == 2
