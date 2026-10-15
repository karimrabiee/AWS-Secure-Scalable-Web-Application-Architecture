"""Nimbus Store: storefront for the application tier.

Internet -> WAF -> ALB -> Nginx -> Gunicorn -> Flask -> RDS MySQL.
/health = liveness for the ALB (never touches the database);
/ready  = readiness incl. database (503 when down).
"""
from __future__ import annotations

import logging
import os
import platform
import time
from pathlib import Path
from typing import Any, Dict, Optional, Union

from db import Database, DatabaseUnavailable, ProductNotFound, Settings
from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

AZ_PATH = Path("/var/lib/app/az.txt")
INSTANCE_ID_PATH = Path("/var/lib/app/instance-id.txt")
STARTED_AT = time.time()
MAX_ORDER_QUANTITY = 5
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; base-uri 'none'; "
                               "form-action 'self'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


def read_text(path: Union[str, Path], fallback: str = "unknown") -> str:
    """Read optional instance metadata; missing/unreadable files are non-fatal."""
    try:
        return Path(path).read_text(encoding="utf-8").strip() or fallback
    except OSError as error:
        logger.warning("Unable to read application metadata file %s: %s", path, error)
        return fallback


def format_price(cents: Union[int, float]) -> str:
    return "${:,.2f}".format(int(cents) / 100)


def create_app(database: Optional[Database] = None) -> Flask:
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=16 * 1024, SEND_FILE_MAX_AGE_DEFAULT=3600)
    app.json.sort_keys = False  # type: ignore[attr-defined]
    db = database or Database(Settings.from_env())
    app.extensions["nimbus_db"] = db
    app.jinja_env.filters["price"] = format_price

    def info() -> Dict[str, str]:
        return {"instance_id": read_text(INSTANCE_ID_PATH), "az": read_text(AZ_PATH)}

    def present(row: Dict[str, Any]) -> Dict[str, Any]:
        return {**row, "price_cents": int(row["price_cents"]), "price": format_price(row["price_cents"])}

    def database_status() -> Dict[str, Any]:
        if not db.settings.configured:
            return {"state": "not-configured", "detail": "DB_HOST / DB_NAME / DB_SECRET_ARN not set"}
        try:
            return {"state": "connected", **db.ping(), **db.stats()}
        except DatabaseUnavailable as error:
            return {"state": "unavailable", "detail": str(error)}

    def build_status() -> Dict[str, Any]:
        data = info()
        database = database_status()
        orders = []
        if database["state"] == "connected":
            try:
                orders = [{**o, "total": format_price(o["total_cents"]), "created_at": str(o["created_at"])}
                          for o in db.recent_orders()]
            except DatabaseUnavailable:
                pass
        return {"web": {**data, "uptime_seconds": int(time.time() - STARTED_AT)},
                "app": {"python": platform.python_version()}, "database": database, "orders": orders, **data}

    @app.after_request
    def add_headers(response):
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if request.path.startswith(("/api/", "/health", "/ready", "/status")):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(Exception)
    def on_error(error: Exception):
        is_http = isinstance(error, HTTPException)
        code = error.code if is_http else 500
        if not is_http:
            logger.exception("Unhandled error: %s", type(error).__name__)
        if request.path.startswith("/api/"):
            name = error.name.lower().replace(" ", "_") if is_http else "internal_error"
            return jsonify(error=name), code
        title, text = ("Page not found", "The page you requested does not exist.") if code == 404 else (
            "Something went wrong", "An unexpected error occurred. Please try again.")
        return render_template("error.html", code=code, title=title, message=text, **info()), code

    @app.get("/health")
    def health():
        return "OK", 200, {"Content-Type": "text/plain; charset=utf-8"}

    @app.get("/ready")
    def ready():
        status = database_status()
        healthy = status["state"] == "connected"
        return jsonify(status="ready" if healthy else "degraded",
                       database={k: status[k] for k in ("state", "latency_ms") if k in status}), 200 if healthy else 503

    @app.get("/")
    def index():
        category = (request.args.get("category") or "").strip()[:48] or None
        query = (request.args.get("q") or "").strip()[:64] or None
        products, categories, error = [], [], None
        try:
            categories = db.list_categories()
            products = [present(p) for p in db.list_products(category, query)]
        except DatabaseUnavailable as exc:
            error = str(exc)
        return render_template("index.html", products=products, categories=categories, active_category=category,
                               query=query or "", db_error=error, **info())

    @app.get("/status")
    def status_page():
        return render_template("status.html", **build_status())

    @app.get("/api/products")
    def api_products():
        category = (request.args.get("category") or "").strip()[:48] or None
        query = (request.args.get("q") or "").strip()[:64] or None
        try:
            items = [present(p) for p in db.list_products(category, query)]
        except DatabaseUnavailable:
            return jsonify(error="database_unavailable"), 503
        return jsonify(count=len(items), products=items)

    @app.post("/api/orders")
    def api_create_order():
        # JSON-only: a cross-site HTML form cannot send it without a CORS pre-flight.
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="json_body_required"), 400
        product_id, quantity = payload.get("product_id"), payload.get("quantity", 1)
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in (product_id, quantity)) \
                or product_id < 1 or not 1 <= quantity <= MAX_ORDER_QUANTITY:
            return jsonify(error="invalid_order", detail="quantity must be 1-%d" % MAX_ORDER_QUANTITY), 400
        data = info()
        try:
            order = db.place_order(product_id, quantity, data["instance_id"], data["az"])
        except ProductNotFound:
            return jsonify(error="product_not_found"), 404
        except DatabaseUnavailable:
            return jsonify(error="database_unavailable"), 503
        return jsonify({**order, "total": format_price(order["total_cents"])}), 201

    return app


# Gunicorn entry point (app:app). Creating the object opens no database connection,
# so a database outage can never stop the workers from booting.
app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000)
