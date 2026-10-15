"""Unit tests for credentials handling, TLS options and schema/seed definitions."""
import os
import re
import unittest
from pathlib import Path
from unittest import mock

import db
from fakes import RecordingConnection, ensure_pymysql

pymysql = ensure_pymysql()
APP_SRC = Path(db.__file__).resolve().parent


def secret(password):
    return {"username": "appadmin", "password": password}


class CredentialTests(unittest.TestCase):
    ENV = {"DB_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:111122223333:secret:rds!db-x"}

    def setUp(self):
        db._credential_cache.update(value=None, fetched_at=0.0)
        patcher = mock.patch.dict(os.environ, self.ENV, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_secret_is_cached_between_calls(self):
        with mock.patch.object(db, "_fetch_secret", return_value=secret("pw1")) as fetch:
            self.assertEqual(db.get_credentials()["password"], "pw1")
            self.assertEqual(db.get_credentials()["password"], "pw1")
        fetch.assert_called_once()

    def test_secret_is_refreshed_after_the_ttl(self):
        with mock.patch.object(db, "_fetch_secret", side_effect=[secret("old"), secret("new")]):
            expired = 1000.0 + db.SECRET_TTL_SECONDS + 1
            with mock.patch.object(db.time, "monotonic", side_effect=[1000.0, 1000.0, expired] * 2):
                self.assertEqual(db.get_credentials()["password"], "old")
                self.assertEqual(db.get_credentials()["password"], "new")

    def test_force_refresh_bypasses_the_cache(self):
        with mock.patch.object(db, "_fetch_secret", side_effect=[secret("a"), secret("b")]):
            db.get_credentials()
            self.assertEqual(db.get_credentials(force_refresh=True)["password"], "b")

    def test_returned_credentials_cannot_mutate_the_cache(self):
        with mock.patch.object(db, "_fetch_secret", return_value=secret("pw")):
            db.get_credentials()["password"] = "tampered"
            self.assertEqual(db.get_credentials()["password"], "pw")

    def test_missing_configuration_raises_database_error(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(db.DatabaseError):
                db.get_credentials()

    def test_env_credentials_are_only_a_local_fallback(self):
        with mock.patch.dict(os.environ, {"DB_USER": "u", "DB_PASSWORD": "p"}, clear=True):
            self.assertEqual(db.get_credentials(), {"username": "u", "password": "p"})
        with mock.patch.dict(os.environ, {**self.ENV, "DB_USER": "u", "DB_PASSWORD": "p"}, clear=True):
            with mock.patch.object(db, "_fetch_secret", return_value=secret("from-secrets-manager")):
                self.assertEqual(db.get_credentials()["password"], "from-secrets-manager")


class ConnectTests(unittest.TestCase):
    ENV = {
        "DB_HOST": "dev-db.example.us-east-1.rds.amazonaws.com",
        "DB_NAME": "appdb",
        "DB_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:111122223333:secret:rds!db-x",
        "DB_SSL_CA": "/etc/ecomm-app/rds-global-bundle.pem",
    }

    def setUp(self):
        db._credential_cache.update(value=None, fetched_at=0.0)

    def test_tls_is_verified_against_the_rds_ca_bundle_including_hostname(self):
        with mock.patch.dict(os.environ, self.ENV, clear=True), \
                mock.patch.object(db, "_fetch_secret", return_value=secret("pw")), \
                mock.patch.object(pymysql, "connect", return_value="conn") as connect:
            self.assertEqual(db.connect(), "conn")
        kwargs = connect.call_args.kwargs
        self.assertEqual(kwargs["host"], self.ENV["DB_HOST"])
        self.assertEqual(kwargs["ssl_ca"], self.ENV["DB_SSL_CA"])
        self.assertIs(kwargs["ssl_verify_cert"], True)
        self.assertIs(kwargs["ssl_verify_identity"], True)
        self.assertLessEqual(kwargs["connect_timeout"], 5)

    def test_access_denied_triggers_one_retry_with_refreshed_credentials(self):
        denied = pymysql.err.OperationalError(db.MYSQL_ACCESS_DENIED, "Access denied")
        with mock.patch.dict(os.environ, self.ENV, clear=True), \
                mock.patch.object(db, "_fetch_secret", side_effect=[secret("rotated-out"), secret("rotated-in")]), \
                mock.patch.object(pymysql, "connect", side_effect=[denied, "conn"]) as connect:
            self.assertEqual(db.connect(), "conn")
        self.assertEqual([c.kwargs["password"] for c in connect.call_args_list],
                         ["rotated-out", "rotated-in"])

    def test_other_connection_errors_are_not_retried(self):
        down = pymysql.err.OperationalError(2003, "Can't connect")
        with mock.patch.dict(os.environ, self.ENV, clear=True), \
                mock.patch.object(db, "_fetch_secret", return_value=secret("pw")), \
                mock.patch.object(pymysql, "connect", side_effect=down) as connect:
            with self.assertRaises(pymysql.err.OperationalError):
                db.connect()
        self.assertEqual(connect.call_count, 1)

    def test_unconfigured_host_is_a_clean_error(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(db.DatabaseError):
                db.connect()


class SchemaTests(unittest.TestCase):
    def test_init_schema_is_idempotent_by_construction(self):
        conn = RecordingConnection()
        with mock.patch.object(db, "connect", return_value=conn):
            total = db.init_schema()
        self.assertEqual(total, len(db.SEED_PRODUCTS))
        self.assertTrue(all("IF NOT EXISTS" in s for s in db.SCHEMA_SQL if "CREATE TABLE" in s))
        self.assertTrue(any(s.startswith("INSERT IGNORE INTO products") for s in conn.statements))

    def test_seed_data_is_unique_and_valid(self):
        skus = [row[0] for row in db.SEED_PRODUCTS]
        self.assertEqual(len(skus), len(set(skus)))
        for sku, name, category, description, price, stock, _icon in db.SEED_PRODUCTS:
            self.assertLessEqual(len(sku), 32)
            self.assertLessEqual(len(name), 120)
            self.assertLessEqual(len(category), 40)
            self.assertGreater(price, 0)
            self.assertGreaterEqual(stock, 0)
            self.assertTrue(description)

    def test_seed_icons_and_categories_exist_in_the_ui(self):
        base = (APP_SRC / "templates" / "base.html").read_text(encoding="utf-8")
        css = (APP_SRC / "static" / "style.css").read_text(encoding="utf-8")
        sprite = set(re.findall(r'<symbol id="i-([a-z]+)"', base))
        for row in db.SEED_PRODUCTS:
            self.assertIn(row[6], sprite, row[0])
            self.assertIn(".tone-" + row[2].lower() + " ", css, row[2])

    def test_failures_become_database_error_without_details(self):
        with mock.patch.object(db, "connect", side_effect=OSError("secret path /x")):
            with self.assertRaises(db.DatabaseError) as ctx:
                db.list_products()
        self.assertNotIn("secret path", str(ctx.exception))

    def test_cli_requires_the_init_argument(self):
        self.assertEqual(db.main(["db.py"]), 2)
        with mock.patch.object(db, "init_schema", side_effect=db.DatabaseError("x")):
            self.assertEqual(db.main(["db.py", "init"]), 1)
        with mock.patch.object(db, "init_schema", return_value=12):
            self.assertEqual(db.main(["db.py", "init"]), 0)


if __name__ == "__main__":
    unittest.main()
