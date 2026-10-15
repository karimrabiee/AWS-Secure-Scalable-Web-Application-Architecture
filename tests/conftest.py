"""Shared fixtures. The application lives next to the Terraform compute module
because that directory is what gets embedded into the EC2 user-data."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP_SRC = ROOT / "terraform" / "modules" / "compute" / "app-src"
sys.path.insert(0, str(APP_SRC))

from db import DatabaseUnavailable, ProductNotFound  # noqa: E402


class FakeDatabase:
    """In-memory stand-in with the same public surface as db.Database."""

    class _Settings:
        configured = True
        ssl_disabled = True

    def __init__(self, available=True):
        self.settings = self._Settings()
        self.available = available
        self.orders = []
        self.products = [
            {"id": 1, "sku": "A-1", "name": "Alpha Keyboard", "category": "Peripherals",
             "description": "Mechanical", "price_cents": 11900},
            {"id": 2, "sku": "B-2", "name": "Beta Headphones", "category": "Audio",
             "description": "Noise cancelling", "price_cents": 24900},
        ]

    def _check(self):
        if not self.available:
            raise DatabaseUnavailable("database connection failed")

    def list_categories(self):
        self._check()
        return [{"category": "Audio", "products": 1}, {"category": "Peripherals", "products": 1}]

    def list_products(self, category=None, search=None, limit=48):
        self._check()
        rows = [p for p in self.products if not category or p["category"] == category]
        if search:
            rows = [p for p in rows if search.lower() in p["name"].lower()]
        return rows

    def place_order(self, product_id, quantity, served_by, az):
        self._check()
        product = next((p for p in self.products if p["id"] == product_id), None)
        if product is None:
            raise ProductNotFound(str(product_id))
        order = {"id": len(self.orders) + 1, "product_id": product_id, "product": product["name"],
                 "quantity": quantity, "total_cents": product["price_cents"] * quantity,
                 "served_by": served_by, "az": az}
        self.orders.append(order)
        return dict(order)

    def recent_orders(self, limit=8):
        self._check()
        return [{**o, "created_at": "2026-01-01 00:00:00"} for o in reversed(self.orders)]

    def stats(self):
        self._check()
        return {"products": len(self.products), "orders": len(self.orders), "revenue_cents": 0}

    def ping(self):
        self._check()
        return {"version": "8.4.0", "tls_cipher": "TLS_AES_256_GCM_SHA384", "latency_ms": 1.2}


@pytest.fixture()
def fake_db():
    return FakeDatabase()


@pytest.fixture()
def make_client(tmp_path, monkeypatch):
    import app as application

    monkeypatch.setattr(application, "AZ_PATH", tmp_path / "az.txt")
    monkeypatch.setattr(application, "INSTANCE_ID_PATH", tmp_path / "instance-id.txt")
    (tmp_path / "az.txt").write_text("us-east-1a\n", encoding="utf-8")
    (tmp_path / "instance-id.txt").write_text("i-test123\n", encoding="utf-8")

    def _make(database):
        flask_app = application.create_app(database)
        flask_app.config.update(TESTING=False, PROPAGATE_EXCEPTIONS=False)
        return flask_app.test_client()

    return _make
