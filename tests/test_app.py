"""HTTP-level tests for the storefront using an in-memory database double."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app as application
import db
from fakes import CIPHER, FakeStore


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()
        patcher = mock.patch.object(db, "connect", self.store.connect)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        meta = Path(self.tmp.name)
        (meta / "az.txt").write_text("us-east-1a\n", encoding="utf-8")
        (meta / "instance-id.txt").write_text("i-0abc123\n", encoding="utf-8")
        for name, target in (("AZ_PATH", "az.txt"), ("INSTANCE_ID_PATH", "instance-id.txt")):
            p = mock.patch.object(application, name, meta / target)
            p.start()
            self.addCleanup(p.stop)
        application.app.config.update(TESTING=True)
        self.client = application.app.test_client()


class StorefrontTests(StoreTestCase):
    def test_home_lists_every_seeded_product_from_the_database(self):
        response = self.client.get("/")
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Premium gear for focused work", body)
        for product in db.SEED_PRODUCTS:
            self.assertIn(product[1], body)
        self.assertIn("$249.00", body)

    def test_footer_shows_serving_az_and_instance(self):
        body = self.client.get("/").get_data(as_text=True)
        self.assertIn("us-east-1a", body)
        self.assertIn("i-0abc123", body)

    def test_category_filter(self):
        body = self.client.get("/?category=Displays").get_data(as_text=True)
        self.assertIn("Vista 27 Monitor", body)
        self.assertNotIn("Aero ANC Headphones", body)

    def test_search_is_case_insensitive_and_matches_description(self):
        self.assertIn("Forge Mechanical Keyboard", self.client.get("/?q=KEYBOARD").get_data(as_text=True))
        self.assertIn("Vault 1TB Portable SSD", self.client.get("/?q=aes-256").get_data(as_text=True))

    def test_search_treats_wildcards_literally(self):
        # A bare "%" must match only descriptions containing a literal percent sign (two seed
        # products), not behave as "match everything".
        body = self.client.get("/", query_string={"q": "%"}).get_data(as_text=True)
        self.assertIn("Vista 32 Ultra", body)
        self.assertIn("Forge Mechanical Keyboard", body)
        self.assertNotIn("Aero ANC Headphones", body)
        for term in ("_", "!"):
            body = self.client.get("/", query_string={"q": term}).get_data(as_text=True)
            self.assertIn("No products found", body, term)

    def test_search_is_parameterised_against_sql_injection(self):
        response = self.client.get("/", query_string={"q": "' OR '1'='1"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("No products found", response.get_data(as_text=True))
        self.assertEqual(self.store.raw.execute("SELECT COUNT(*) FROM products").fetchone()[0], 12)

    def test_product_names_are_html_escaped(self):
        self.store.add("XSS-1", "<script>alert(1)</script>")
        body = self.client.get("/").get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", body)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", body)

    def test_product_detail_and_missing_product(self):
        ok = self.client.get("/products/1")
        self.assertEqual(ok.status_code, 200)
        self.assertIn("Aero ANC Headphones", ok.get_data(as_text=True))
        self.assertEqual(self.client.get("/products/9999").status_code, 404)
        self.assertEqual(self.client.get("/products/abc").status_code, 404)

    def test_unknown_route_renders_branded_404(self):
        response = self.client.get("/nope")
        self.assertEqual(response.status_code, 404)
        self.assertIn("Page not found", response.get_data(as_text=True))

    def test_api_products_returns_json(self):
        data = self.client.get("/api/products?category=Audio").get_json()
        self.assertEqual(data["count"], 3)
        self.assertTrue(all(p["category"] == "Audio" for p in data["products"]))


class StatusAndHealthTests(StoreTestCase):
    def test_health_is_plain_text_ok(self):
        response = self.client.get("/health")
        self.assertEqual((response.status_code, response.get_data(as_text=True)), (200, "OK"))
        self.assertEqual(response.mimetype, "text/plain")

    def test_api_status_reports_live_database_details(self):
        response = self.client.get("/api/status")
        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["database"]["connected"])
        self.assertEqual(data["database"]["products"], 12)
        self.assertEqual(data["database"]["cipher"], CIPHER)
        self.assertEqual(data["application"]["az"], "us-east-1a")
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_status_page_renders_connected_state(self):
        body = self.client.get("/status").get_data(as_text=True)
        self.assertIn("Connected", body)
        self.assertIn(CIPHER, body)
        self.assertIn("12 products", body)

    def test_ready_reflects_database(self):
        self.assertEqual(self.client.get("/ready").status_code, 200)


class DatabaseOutageTests(StoreTestCase):
    SENSITIVE = "super-secret-password"

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(db, "connect", side_effect=RuntimeError(self.SENSITIVE))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_health_stays_green_so_the_alb_does_not_drain_the_fleet(self):
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_storefront_degrades_to_a_clear_503_without_leaking_details(self):
        response = self.client.get("/")
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 503)
        self.assertIn("temporarily unavailable", body)
        self.assertNotIn(self.SENSITIVE, body)

    def test_ready_and_api_report_unavailable(self):
        self.assertEqual(self.client.get("/ready").status_code, 503)
        api = self.client.get("/api/status")
        self.assertEqual(api.status_code, 503)
        self.assertEqual(api.get_json()["database"], {"connected": False, "error": "unavailable"})
        self.assertNotIn(self.SENSITIVE, api.get_data(as_text=True))

    def test_product_endpoints_report_503(self):
        self.assertEqual(self.client.get("/products/1").status_code, 503)
        self.assertEqual(self.client.get("/api/products").status_code, 503)
        self.assertEqual(json.loads(self.client.get("/api/products").data)["error"], "database_unavailable")


class SecurityAndMetadataTests(StoreTestCase):
    def test_security_headers_are_set(self):
        headers = self.client.get("/").headers
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertIn("Referrer-Policy", headers)

    def test_static_assets_are_served(self):
        for path, expected in (("/static/style.css", "css"), ("/static/app.js", "javascript")):
            with self.client.get(path) as response:
                self.assertEqual(response.status_code, 200, path)
                self.assertIn(expected, response.mimetype)

    def test_missing_metadata_uses_fallback_and_is_logged(self):
        missing = Path(self.tmp.name) / "absent.txt"
        with self.assertLogs(application.logger, level="WARNING") as logs:
            self.assertEqual(application.read_text(missing), "unknown")
        self.assertIn("Unable to read application metadata file", logs.output[0])

    def test_blank_metadata_uses_fallback(self):
        blank = Path(self.tmp.name) / "blank.txt"
        blank.write_text("  \n", encoding="utf-8")
        self.assertEqual(application.read_text(blank, fallback="n/a"), "n/a")

    def test_unreadable_metadata_is_not_fatal(self):
        with mock.patch.object(Path, "read_text", side_effect=PermissionError("denied")):
            self.assertEqual(self.client.get("/").status_code, 200)


if __name__ == "__main__":
    unittest.main()
