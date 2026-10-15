"""Behavioural tests for the Flask application (no AWS, no real database)."""
import logging
from pathlib import Path

import app as application
from conftest import FakeDatabase


def test_home_lists_products_read_from_the_database(make_client, fake_db):
    response = make_client(fake_db).get("/")
    assert response.status_code == 200
    assert b"Secure, Highly Available Web Platform" in response.data
    assert b"Alpha Keyboard" in response.data and b"$119.00" in response.data
    assert b"us-east-1a" in response.data and b"i-test123" in response.data


def test_home_filters_by_category_and_search(make_client, fake_db):
    client = make_client(fake_db)
    assert b"Beta Headphones" not in client.get("/?category=Peripherals").data
    assert b"Alpha Keyboard" not in client.get("/?q=headphones").data


def test_health_is_database_independent(make_client):
    client = make_client(FakeDatabase(available=False))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_data(as_text=True) == "OK"
    assert response.mimetype == "text/plain"


def test_ready_reports_503_when_database_is_down(make_client):
    response = make_client(FakeDatabase(available=False)).get("/ready")
    assert response.status_code == 503
    assert response.get_json()["status"] == "degraded"


def test_ready_reports_200_when_database_is_up(make_client, fake_db):
    response = make_client(fake_db).get("/ready")
    assert response.status_code == 200
    assert response.get_json()["database"]["state"] == "connected"


def test_home_degrades_gracefully_without_database(make_client):
    response = make_client(FakeDatabase(available=False)).get("/")
    assert response.status_code == 200
    assert b"temporarily unavailable" in response.data


def test_api_returns_503_json_without_database(make_client):
    client = make_client(FakeDatabase(available=False))
    response = client.get("/api/products")
    assert response.status_code == 503
    assert response.get_json() == {"error": "database_unavailable"}


def test_status_page(make_client, fake_db):
    client = make_client(fake_db)
    page = client.get("/status")
    assert page.status_code == 200
    assert b"us-east-1a" in page.data and b"Connected" in page.data and b"TLS_AES_256_GCM_SHA384" in page.data


def test_create_order_computes_total_server_side(make_client, fake_db):
    client = make_client(fake_db)
    response = client.post("/api/orders", json={"product_id": 1, "quantity": 2, "total_cents": 1})
    assert response.status_code == 201
    assert response.get_json()["total_cents"] == 23800  # client-supplied total ignored
    assert fake_db.orders[0]["served_by"] == "i-test123"


def test_create_order_validation(make_client, fake_db):
    client = make_client(fake_db)
    assert client.post("/api/orders", data="product_id=1").status_code == 400
    assert client.post("/api/orders", json=[1]).status_code == 400
    assert client.post("/api/orders", json={"product_id": "1", "quantity": 1}).status_code == 400
    assert client.post("/api/orders", json={"product_id": True, "quantity": 1}).status_code == 400
    assert client.post("/api/orders", json={"product_id": 1, "quantity": 0}).status_code == 400
    assert client.post("/api/orders", json={"product_id": 1, "quantity": 99}).status_code == 400
    assert client.post("/api/orders", json={"product_id": 999, "quantity": 1}).status_code == 404
    assert fake_db.orders == []


def test_security_headers_present(make_client, fake_db):
    headers = make_client(fake_db).get("/").headers
    assert "default-src 'self'" in headers["Content-Security-Policy"]
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"


def test_unknown_routes_and_methods(make_client, fake_db):
    client = make_client(fake_db)
    assert client.get("/missing").status_code == 404
    assert client.get("/api/missing").get_json() == {"error": "not_found"}
    assert client.delete("/api/orders").status_code == 405


def test_unexpected_error_hides_stack_trace(make_client, fake_db, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("secret-internal-detail")

    monkeypatch.setattr(fake_db, "list_categories", boom)
    response = make_client(fake_db).get("/")
    assert response.status_code == 500
    assert b"secret-internal-detail" not in response.data
    assert b"Traceback" not in response.data


def test_missing_metadata_files_use_fallback_and_log(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        assert application.read_text(tmp_path / "missing.txt") == "unknown"
    assert "Unable to read application metadata file" in caplog.text


def test_blank_metadata_file_uses_fallback(tmp_path):
    blank = tmp_path / "blank.txt"
    blank.write_text("  \n", encoding="utf-8")
    assert application.read_text(blank, fallback="n/a") == "n/a"


def test_filesystem_error_is_non_fatal(monkeypatch, tmp_path):
    def deny(self, *args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "read_text", deny)
    assert application.read_text(tmp_path / "x.txt", fallback="safe") == "safe"


def test_module_import_does_not_touch_the_database():
    # gunicorn imports `app:app`; a database outage must never stop workers booting.
    assert application.app.extensions["nimbus_db"].settings is not None
