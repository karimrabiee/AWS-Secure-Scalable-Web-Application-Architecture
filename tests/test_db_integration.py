"""Integration tests against a REAL MySQL-compatible server.

Skipped unless TEST_DB_HOST is set. CI runs them against a mysql:8.4 service
container; locally point them at any disposable server (needs a user that can
CREATE DATABASE / CREATE USER).
"""
import json
import os
import threading

import pymysql
import pytest
from db import Database, DatabaseUnavailable, ProductNotFound, SecretsManagerCredentials, Settings

pytestmark = pytest.mark.skipif(not os.getenv("TEST_DB_HOST"), reason="TEST_DB_HOST not set")

HOST = os.getenv("TEST_DB_HOST", "127.0.0.1")
PORT = int(os.getenv("TEST_DB_PORT", "3306"))
ADMIN_USER = os.getenv("TEST_DB_USER", "root")
ADMIN_PASSWORD = os.getenv("TEST_DB_PASSWORD", "")
SCHEMA_NAME = "nimbus_it"
EXPECTED_PRODUCTS = 10
APP_USER = "nimbus_app"


class MutableSecret:
    def __init__(self, password):
        self.password = password
        self.calls = 0

    def get_secret_value(self, SecretId):
        self.calls += 1
        return {"SecretString": json.dumps({"username": APP_USER, "password": self.password})}


def admin():
    return pymysql.connect(host=HOST, port=PORT, user=ADMIN_USER, password=ADMIN_PASSWORD, autocommit=True)


@pytest.fixture()
def server():
    with admin() as conn, conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {SCHEMA_NAME}")
        cur.execute(f"CREATE DATABASE {SCHEMA_NAME}")
        cur.execute(f"DROP USER IF EXISTS '{APP_USER}'@'%'")
        cur.execute(f"CREATE USER '{APP_USER}'@'%' IDENTIFIED BY 'first-password'")
        cur.execute(f"GRANT ALL ON {SCHEMA_NAME}.* TO '{APP_USER}'@'%'")
    yield
    with admin() as conn, conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {SCHEMA_NAME}")
        cur.execute(f"DROP USER IF EXISTS '{APP_USER}'@'%'")


@pytest.fixture()
def secret(server):
    return MutableSecret("first-password")


@pytest.fixture()
def database(secret):
    settings = Settings(host=HOST, port=PORT, name=SCHEMA_NAME, secret_arn="arn:test", ssl_disabled=True)
    return Database(settings, credentials=SecretsManagerCredentials("arn:test", "us-east-1", client=secret))


def test_schema_and_seed_are_created_and_idempotent(database, secret):
    assert len(database.list_products()) == EXPECTED_PRODUCTS
    second = Database(database.settings, credentials=SecretsManagerCredentials("arn:test", "r", client=secret))
    second.ensure_schema()  # a second instance booting later must not duplicate anything
    assert database.stats()["products"] == EXPECTED_PRODUCTS


def test_concurrent_schema_initialisation_is_safe(secret):
    settings = Settings(host=HOST, port=PORT, name=SCHEMA_NAME, secret_arn="arn:test", ssl_disabled=True)
    instances = [Database(settings, credentials=SecretsManagerCredentials("a", "r", client=secret)) for _ in range(4)]
    errors = []

    def run(instance):
        try:
            instance.ensure_schema()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(i,)) for i in instances]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert instances[0].stats()["products"] == EXPECTED_PRODUCTS


def test_filtering_and_categories(database):
    assert {p["category"] for p in database.list_products(category="Audio")} == {"Audio"}
    assert [c["category"] for c in database.list_categories()] == ["Audio", "Peripherals", "Security", "Storage", "Workspace"]
    assert all("ssd" in (p["name"] + p["description"]).lower() for p in database.list_products(search="ssd"))


def test_sql_injection_attempts_are_inert(database):
    for payload in ("' OR '1'='1", "'; DROP TABLE products; --", "%", "_"):
        database.list_products(search=payload)
        database.list_products(category=payload)
    assert database.stats()["products"] == EXPECTED_PRODUCTS  # table still intact
    # "%" must match only rows that literally contain a percent sign (a few rows), not act as a wildcard.
    literal = database.list_products(search="%")
    assert 0 < len(literal) < EXPECTED_PRODUCTS
    assert all("%" in (p["name"] + p["description"]) for p in literal)


def test_place_order_persists_and_uses_stored_price(database):
    price = next(p for p in database.list_products() if p["id"] == 1)["price_cents"]
    order = database.place_order(1, 3, "i-abc", "us-east-1b")
    assert order["total_cents"] == price * 3
    recent = database.recent_orders()
    assert recent[0]["id"] == order["id"] and recent[0]["az"] == "us-east-1b"
    assert database.stats()["orders"] == 1


def test_unknown_product_is_rejected_without_side_effects(database):
    with pytest.raises(ProductNotFound):
        database.place_order(9999, 1, "i-abc", "az")
    assert database.stats()["orders"] == 0


def test_ping_reports_version_and_latency(database):
    info = database.ping()
    assert info["version"] and info["latency_ms"] >= 0


def test_credential_rotation_is_recovered_automatically(database, secret):
    assert database.stats()["products"] == EXPECTED_PRODUCTS  # connects with 'first-password' and caches it
    calls_before = secret.calls
    with admin() as conn, conn.cursor() as cur:  # simulate RDS/Secrets Manager rotation
        cur.execute(f"ALTER USER '{APP_USER}'@'%' IDENTIFIED BY 'rotated-password'")
    secret.password = "rotated-password"
    assert database.stats()["products"] == EXPECTED_PRODUCTS  # 1045 -> refresh -> retry succeeds
    assert secret.calls == calls_before + 1


def test_wrong_credentials_fail_closed_with_generic_error(database, secret):
    secret.password = "wrong"
    with pytest.raises(DatabaseUnavailable) as info:
        database.stats()
    assert "wrong" not in str(info.value) and NIMBUS_USER not in str(info.value)


NIMBUS_USER = APP_USER
