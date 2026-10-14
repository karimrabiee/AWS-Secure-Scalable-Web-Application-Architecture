<<<<<<< HEAD
"""Behavioral tests for the Flask sample application."""
from pathlib import Path
import sys

import pytest

pytest.importorskip("flask", reason="Install requirements-dev.txt to run Flask tests")

APP_SOURCE = Path(__file__).resolve().parents[1] / "terraform" / "modules" / "compute" / "app-src"
sys.path.insert(0, str(APP_SOURCE))
=======
import sys
from pathlib import Path

import pytest

APP_SRC = Path(__file__).parents[1] / "terraform" / "modules" / "compute" / "app-src"
sys.path.insert(0, str(APP_SRC))
>>>>>>> 71250862fd348fd167e0e034b6f505b43e8e9250

import app as application  # noqa: E402


@pytest.fixture()
<<<<<<< HEAD
def client():
    application.app.config.update(TESTING=True)
    with application.app.test_client() as test_client:
        yield test_client


def test_home_page_returns_success_and_displays_metadata(client, monkeypatch):
    metadata = {
        "/var/lib/app/az.txt": "us-east-1a",
        "/var/lib/app/instance-id.txt": "i-test-instance",
    }
    monkeypatch.setattr(application, "read_text", lambda path, fallback="unknown": metadata.get(str(path), fallback))
=======
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(application, "AZ_PATH", tmp_path / "az.txt")
    monkeypatch.setattr(application, "INSTANCE_ID_PATH", tmp_path / "instance-id.txt")
    application.app.config.update(TESTING=True)
    return application.app.test_client()


def test_home_page_returns_expected_response(client, tmp_path):
    (tmp_path / "az.txt").write_text("us-east-1a\n", encoding="utf-8")
    (tmp_path / "instance-id.txt").write_text("i-test123\n", encoding="utf-8")
>>>>>>> 71250862fd348fd167e0e034b6f505b43e8e9250

    response = client.get("/")

    assert response.status_code == 200
    assert b"Secure, Highly Available Web Platform" in response.data
    assert b"us-east-1a" in response.data
<<<<<<< HEAD
    assert b"i-test-instance" in response.data


def test_health_endpoint_returns_expected_response(client):
=======
    assert b"i-test123" in response.data


def test_health_is_database_independent(client):
>>>>>>> 71250862fd348fd167e0e034b6f505b43e8e9250
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "OK"
    assert response.mimetype == "text/plain"


<<<<<<< HEAD
def test_missing_metadata_file_uses_fallback_and_logs_warning(tmp_path, caplog):
    missing_file = tmp_path / "not-created.txt"

    assert application.read_text(missing_file) == "unknown"
    assert "Unable to read application metadata file" in caplog.text


def test_blank_metadata_file_uses_fallback(tmp_path):
    empty_file = tmp_path / "empty.txt"
    empty_file.write_text("  \n", encoding="utf-8")

    assert application.read_text(empty_file, fallback="n/a") == "n/a"


def test_filesystem_error_is_non_fatal_and_logged(monkeypatch, caplog, tmp_path):
    def deny_read(self, *args, **kwargs):
        raise PermissionError("simulated permission denial")

    monkeypatch.setattr(Path, "read_text", deny_read)

    assert application.read_text(tmp_path / "protected.txt", fallback="safe") == "safe"
    assert "simulated permission denial" in caplog.text
=======
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
>>>>>>> 71250862fd348fd167e0e034b6f505b43e8e9250
