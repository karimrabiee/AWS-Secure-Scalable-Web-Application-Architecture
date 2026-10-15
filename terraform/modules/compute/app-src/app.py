"""Nimbus Store - sample storefront for the AWS three-tier reference architecture.

Request path: ALB -> Nginx -> Gunicorn -> Flask -> Amazon RDS for MySQL.

Design notes:
* ``/health`` is deliberately independent of the database so a database incident cannot
  make the ALB drain every instance at once; ``/ready`` reports the database state.
* The storefront degrades to a clear 503 page when the database is unreachable.
"""
from __future__ import annotations

import logging
import os
import platform
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, Union

from flask import Flask, jsonify, render_template, request

import db

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

METADATA_DIR = Path(os.getenv("APP_METADATA_DIR", "/var/lib/app"))
AZ_PATH = METADATA_DIR / "az.txt"
INSTANCE_ID_PATH = METADATA_DIR / "instance-id.txt"

app = Flask(__name__)
app.json.sort_keys = False
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = timedelta(hours=1)

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
    "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)


def read_text(path: Union[str, Path], fallback: str = "unknown") -> str:
    """Read optional instance metadata; a missing or unreadable file is never fatal."""
    try:
        return Path(path).read_text(encoding="utf-8").strip() or fallback
    except OSError as error:
        logger.warning("Unable to read application metadata file %s: %s", path, error)
        return fallback


def instance_meta() -> Dict[str, str]:
    return {"az": read_text(AZ_PATH), "instance_id": read_text(INSTANCE_ID_PATH)}


@app.template_filter("money")
def money(cents: Any) -> str:
    return "${:,.2f}".format(int(cents) / 100)


@app.context_processor
def inject_globals() -> Dict[str, Any]:
    return {"meta": instance_meta()}


@app.after_request
def set_security_headers(response):
    response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.path.startswith(("/api/", "/status", "/ready")):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
def index():
    query = request.args.get("q", "").strip()[: db.MAX_QUERY_LENGTH]
    category = request.args.get("category", "").strip()[:40]
    try:
        categories = db.list_categories()
        products = db.list_products(category or None, query or None)
    except db.DatabaseError:
        return render_template("index.html", unavailable=True, products=[], categories=[],
                               query=query, category=category), 503
    return render_template("index.html", unavailable=False, products=products,
                           categories=categories, query=query, category=category)


@app.get("/products/<int:product_id>")
def product_detail(product_id: int):
    try:
        product = db.get_product(product_id)
    except db.DatabaseError:
        return render_template("error.html", code=503, title="Catalog unavailable",
                               message="The product catalog cannot be reached right now. "
                                       "Please try again in a moment."), 503
    if product is None:
        return render_template("error.html", code=404, title="Product not found",
                               message="That product does not exist or was removed."), 404
    return render_template("product.html", product=product)


@app.get("/status")
def status_page():
    return render_template("status.html", status=build_status())


@app.get("/api/products")
def api_products():
    query = request.args.get("q", "").strip()[: db.MAX_QUERY_LENGTH]
    category = request.args.get("category", "").strip()[:40]
    try:
        products = db.list_products(category or None, query or None)
    except db.DatabaseError:
        return jsonify(error="database_unavailable"), 503
    return jsonify(count=len(products), products=products)


@app.get("/api/status")
def api_status():
    payload = build_status()
    return jsonify(payload), 200 if payload["database"]["connected"] else 503


def build_status() -> Dict[str, Any]:
    database = db.database_status()
    return {
        "status": "ok" if database["connected"] else "degraded",
        "application": {
            **instance_meta(),
            "runtime": "Python " + platform.python_version(),
            "path": "ALB \u2192 Nginx \u2192 Gunicorn \u2192 Flask \u2192 RDS",
        },
        "database": database,
    }


@app.get("/health")
def health():
    # Liveness only. Keep the ALB health check independent from the database.
    return "OK", 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.get("/ready")
def ready():
    database = db.database_status()
    return jsonify(ready=database["connected"]), 200 if database["connected"] else 503


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", code=404, title="Page not found",
                           message="The page you are looking for does not exist."), 404


@app.errorhandler(500)
def server_error(_error):
    return render_template("error.html", code=500, title="Something went wrong",
                           message="An unexpected error occurred. It has been logged."), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000)
