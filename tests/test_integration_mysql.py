"""Integration tests against a real MySQL server (skipped unless TEST_MYSQL_HOST is set).

CI runs these against a ``mysql:8.4`` service container, which validates the real DDL, the
idempotent seed, LIKE/ESCAPE semantics and the status probe on the same engine family as RDS.
"""
import os
import unittest
from unittest import mock

import app as application
import db

HOST = os.getenv("TEST_MYSQL_HOST")


@unittest.skipUnless(HOST, "TEST_MYSQL_HOST not set; MySQL integration tests are CI-only")
class MySQLIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = {
            "DB_HOST": HOST,
            "DB_PORT": os.getenv("TEST_MYSQL_PORT", "3306"),
            "DB_NAME": os.getenv("TEST_MYSQL_DATABASE", "appdb"),
            "DB_USER": os.getenv("TEST_MYSQL_USER", "root"),
            "DB_PASSWORD": os.getenv("TEST_MYSQL_PASSWORD", ""),
        }

    def setUp(self):
        patcher = mock.patch.dict(os.environ, self.env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_schema_init_is_idempotent(self):
        first = db.init_schema()
        second = db.init_schema()
        self.assertEqual(first, len(db.SEED_PRODUCTS))
        self.assertEqual(second, first)

    def test_queries_and_search_escaping(self):
        db.init_schema()
        self.assertEqual(len(db.list_products()), len(db.SEED_PRODUCTS))
        self.assertTrue(all(p["category"] == "Audio" for p in db.list_products("Audio")))
        percent_hits = {p["sku"] for p in db.list_products(query="%")}
        self.assertEqual(percent_hits, {"DSP-220", "INP-100"})
        self.assertEqual(db.list_products(query="_"), [])
        self.assertEqual(db.get_product(1)["sku"], "AUD-100")
        self.assertIsNone(db.get_product(999999))

    def test_status_probe_and_http_endpoints(self):
        db.init_schema()
        status = db.database_status()
        self.assertTrue(status["connected"], status)
        self.assertEqual(status["products"], len(db.SEED_PRODUCTS))
        client = application.app.test_client()
        self.assertEqual(client.get("/").status_code, 200)
        self.assertEqual(client.get("/api/status").status_code, 200)

    def test_unreachable_database_degrades_cleanly(self):
        with mock.patch.dict(os.environ, {"DB_PORT": "1"}):
            self.assertFalse(db.database_status()["connected"])
            self.assertEqual(application.app.test_client().get("/").status_code, 503)


if __name__ == "__main__":
    unittest.main()
