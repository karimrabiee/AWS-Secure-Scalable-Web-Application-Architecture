"""Behavioral tests for the Flask sample application."""
from pathlib import Path
import sys

import pytest

pytest.importorskip("flask", reason="Install requirements-dev.txt to run Flask tests")

APP_SOURCE = Path(__file__).resolve().parents[1] / "terraform" / "modules" / "compute" / "app-src"
sys.path.insert(0, str(APP_SOURCE))

import app as application  # noqa: E402


@pytest.fixture()
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

    response = client.get("/")

    assert response.status_code == 200
    assert b"Secure, Highly Available Web Platform" in response.data
    assert b"us-east-1a" in response.data
    assert b"i-test-instance" in response.data


def test_health_endpoint_returns_expected_response(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "OK"
    assert response.mimetype == "text/plain"


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
