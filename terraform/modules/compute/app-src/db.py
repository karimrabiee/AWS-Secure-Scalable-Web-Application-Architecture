"""Database access layer for the Nimbus Store sample application.

Credentials never touch disk or Terraform state: they are read at runtime from the
AWS Secrets Manager secret that RDS manages (``manage_master_user_password``), cached
briefly in memory, and refreshed automatically after a rotation. The connection uses
TLS with certificate *and* hostname verification against the Amazon RDS CA bundle.

Run ``python db.py init`` once per instance bootstrap to create and seed the schema.
"""
from __future__ import annotations

import functools
import json
import logging
import os
import sys
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)

SECRET_TTL_SECONDS = 300
CONNECT_TIMEOUT_SECONDS = 3
IO_TIMEOUT_SECONDS = 5
MYSQL_ACCESS_DENIED = 1045
MAX_QUERY_LENGTH = 80

SCHEMA_SQL = (
    """
    CREATE TABLE IF NOT EXISTS products (
        id INT UNSIGNED NOT NULL AUTO_INCREMENT,
        sku VARCHAR(32) NOT NULL,
        name VARCHAR(120) NOT NULL,
        category VARCHAR(40) NOT NULL,
        description TEXT NOT NULL,
        price_cents INT UNSIGNED NOT NULL,
        stock INT UNSIGNED NOT NULL DEFAULT 0,
        icon VARCHAR(24) NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        UNIQUE KEY uq_products_sku (sku),
        KEY idx_products_category (category)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
)

# (sku, name, category, description, price_cents, stock, icon)
SEED_PRODUCTS: List[Tuple[str, str, str, str, int, int, str]] = [
    ("AUD-100", "Aero ANC Headphones", "Audio",
     "Over-ear wireless headphones with adaptive noise cancelling and 40-hour battery.",
     24900, 38, "audio"),
    ("AUD-210", "Pulse Studio Earbuds", "Audio",
     "Low-latency earbuds with a charging case, multipoint pairing and IPX4 protection.",
     12900, 64, "audio"),
    ("AUD-320", "Orbit Desk Speaker", "Audio",
     "Compact stereo speaker with room correction and USB-C audio input.",
     8900, 27, "audio"),
    ("INP-100", "Forge Mechanical Keyboard", "Input",
     "75% hot-swappable keyboard with gasket mount, PBT keycaps and tri-mode wireless.",
     15900, 41, "keyboard"),
    ("INP-210", "Glide Ergonomic Mouse", "Input",
     "Vertical wireless mouse with 8K optical sensor and silent switches.",
     7900, 82, "mouse"),
    ("INP-330", "Lumen Webcam 4K", "Input",
     "4K webcam with HDR, auto-framing and a physical privacy shutter.",
     11900, 19, "camera"),
    ("DSP-100", "Vista 27 Monitor", "Displays",
     "27-inch QHD IPS display, 165 Hz, factory calibrated with USB-C 90 W power delivery.",
     39900, 14, "display"),
    ("DSP-220", "Vista 32 Ultra", "Displays",
     "32-inch 4K display with 99% DCI-P3 coverage and a built-in KVM switch.",
     64900, 9, "display"),
    ("WRK-100", "Atlas USB-C Dock", "Workspace",
     "12-in-1 dock: dual HDMI, 2.5 GbE, SD reader and 100 W pass-through charging.",
     18900, 52, "hub"),
    ("WRK-210", "Vault 1TB Portable SSD", "Workspace",
     "Rugged NVMe SSD with 1,050 MB/s reads and hardware AES-256 encryption.",
     10900, 71, "storage"),
    ("WRK-320", "Volt 140W GaN Charger", "Workspace",
     "Four-port GaN charger that powers a laptop, tablet and phone at once.",
     6900, 96, "power"),
    ("WRK-430", "Stratus Laptop Stand", "Workspace",
     "Foldable aluminium stand with six height positions and passive cooling.",
     4900, 110, "hub"),
]


class DatabaseError(RuntimeError):
    """Any database or credential failure. Messages are safe to log or display."""


def settings() -> Dict[str, Any]:
    """Read connection settings from the environment at call time (testable)."""
    return {
        "host": os.getenv("DB_HOST", ""),
        "port": int(os.getenv("DB_PORT", "3306")),
        "name": os.getenv("DB_NAME", "appdb"),
        "secret_arn": os.getenv("DB_SECRET_ARN", ""),
        "region": os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1",
        "ssl_ca": os.getenv("DB_SSL_CA", ""),
    }


_credential_lock = threading.Lock()
_credential_cache: Dict[str, Any] = {"value": None, "fetched_at": 0.0}


def _fetch_secret(secret_arn: str, region: str) -> Dict[str, str]:
    import boto3  # imported lazily so unit tests and tooling do not require AWS libraries
    from botocore.config import Config

    client = boto3.client(
        "secretsmanager",
        region_name=region,
        config=Config(
            connect_timeout=3,
            read_timeout=5,
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )
    payload = json.loads(client.get_secret_value(SecretId=secret_arn)["SecretString"])
    return {"username": payload["username"], "password": payload["password"]}


def get_credentials(force_refresh: bool = False) -> Dict[str, str]:
    """Return ``{"username", "password"}`` from Secrets Manager, cached for a few minutes.

    ``DB_USER``/``DB_PASSWORD`` are honoured only when no secret ARN is configured; this is
    intended for local development and the CI integration job, never for AWS deployments.
    """
    cfg = settings()
    if not cfg["secret_arn"]:
        user, password = os.getenv("DB_USER"), os.getenv("DB_PASSWORD")
        if user and password:
            return {"username": user, "password": password}
        raise DatabaseError("Database credentials are not configured")

    with _credential_lock:
        cached = _credential_cache["value"]
        age = time.monotonic() - _credential_cache["fetched_at"]
        if force_refresh or cached is None or age > SECRET_TTL_SECONDS:
            _credential_cache["value"] = _fetch_secret(cfg["secret_arn"], cfg["region"])
            _credential_cache["fetched_at"] = time.monotonic()
        return dict(_credential_cache["value"])


def _guard(func: Callable[..., Any]) -> Callable[..., Any]:
    """Translate any low-level failure into DatabaseError without leaking details."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except DatabaseError:
            raise
        except Exception as exc:
            logger.error("Database operation %s failed: %s: %s",
                         func.__name__, exc.__class__.__name__, exc)
            raise DatabaseError("The database is currently unavailable") from exc

    return wrapper


def connect() -> Any:
    """Open one verified-TLS connection. Retries once with fresh credentials after rotation."""
    import pymysql
    from pymysql.cursors import DictCursor

    cfg = settings()
    if not cfg["host"]:
        raise DatabaseError("Database host is not configured")

    def _open(creds: Dict[str, str]) -> Any:
        options: Dict[str, Any] = {
            "host": cfg["host"],
            "port": cfg["port"],
            "user": creds["username"],
            "password": creds["password"],
            "database": cfg["name"],
            "charset": "utf8mb4",
            "cursorclass": DictCursor,
            "connect_timeout": CONNECT_TIMEOUT_SECONDS,
            "read_timeout": IO_TIMEOUT_SECONDS,
            "write_timeout": IO_TIMEOUT_SECONDS,
            "autocommit": True,
        }
        if cfg["ssl_ca"]:
            options.update(ssl_ca=cfg["ssl_ca"], ssl_verify_cert=True, ssl_verify_identity=True)
        return pymysql.connect(**options)

    try:
        return _open(get_credentials())
    except pymysql.err.OperationalError as exc:
        if not (exc.args and exc.args[0] == MYSQL_ACCESS_DENIED and cfg["secret_arn"]):
            raise
        logger.warning("Access denied; refreshing credentials in case the secret was rotated")
        return _open(get_credentials(force_refresh=True))


@contextmanager
def connection() -> Iterator[Any]:
    conn = connect()
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:  # closing a broken connection must never mask the real error
            logger.debug("Ignoring error while closing database connection", exc_info=True)


def _like(term: str) -> str:
    escaped = term.replace("!", "!!").replace("%", "!%").replace("_", "!_")
    return "%" + escaped + "%"


_PRODUCT_COLUMNS = "id, sku, name, category, description, price_cents, stock, icon"


@_guard
def list_products(category: Optional[str] = None, query: Optional[str] = None,
                  limit: int = 60) -> List[Dict[str, Any]]:
    sql = "SELECT " + _PRODUCT_COLUMNS + " FROM products"
    clauses: List[str] = []
    params: List[Any] = []
    if category:
        clauses.append("category = %s")
        params.append(category)
    if query:
        term = _like(query[:MAX_QUERY_LENGTH])
        clauses.append("(name LIKE %s ESCAPE '!' OR description LIKE %s ESCAPE '!')")
        params.extend([term, term])
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY category, name LIMIT %s"
    params.append(int(limit))
    with connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


@_guard
def get_product(product_id: int) -> Optional[Dict[str, Any]]:
    sql = "SELECT " + _PRODUCT_COLUMNS + " FROM products WHERE id = %s"
    with connection() as conn, conn.cursor() as cur:
        cur.execute(sql, (int(product_id),))
        return cur.fetchone()


@_guard
def list_categories() -> List[Dict[str, Any]]:
    sql = "SELECT category, COUNT(*) AS total FROM products GROUP BY category ORDER BY category"
    with connection() as conn, conn.cursor() as cur:
        cur.execute(sql)
        return list(cur.fetchall())


def database_status() -> Dict[str, Any]:
    """Live connectivity probe used by /status and /ready. Never raises, never leaks details."""
    started = time.perf_counter()
    try:
        with connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT VERSION() AS version")
            version = str(cur.fetchone()["version"])
            cur.execute("SHOW SESSION STATUS LIKE 'Ssl_cipher'")
            row = cur.fetchone()
            cipher = (row or {}).get("Value") or ""
            cur.execute("SELECT COUNT(*) AS total FROM products")
            products = int(cur.fetchone()["total"])
    except Exception as exc:
        logger.warning("Database status probe failed: %s: %s", exc.__class__.__name__, exc)
        return {"connected": False, "error": "unavailable"}
    return {
        "connected": True,
        "engine": "MySQL",
        "version": version,
        "tls": bool(cipher),
        "cipher": cipher,
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "products": products,
    }


@_guard
def init_schema(seed: bool = True) -> int:
    """Create tables and seed the catalog. Idempotent and safe if several instances race."""
    with connection() as conn, conn.cursor() as cur:
        for statement in SCHEMA_SQL:
            cur.execute(statement)
        if seed:
            cur.executemany(
                "INSERT IGNORE INTO products "
                "(sku, name, category, description, price_cents, stock, icon) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                SEED_PRODUCTS,
            )
        cur.execute("SELECT COUNT(*) AS total FROM products")
        return int(cur.fetchone()["total"])


def main(argv: List[str]) -> int:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if argv[1:] != ["init"]:
        print("usage: python db.py init", file=sys.stderr)
        return 2
    try:
        total = init_schema()
    except DatabaseError as exc:
        logger.error("Schema initialisation failed: %s", exc)
        return 1
    logger.info("Schema ready; catalog contains %d products", total)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
