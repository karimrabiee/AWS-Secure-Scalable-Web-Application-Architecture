"""Database layer: Secrets Manager credentials + PyMySQL over verified TLS.

Failures surface as DatabaseUnavailable with messages that are safe to log and
return (no credentials, no SQL). Schema/seed creation is idempotent so several
instances can boot at once.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

import pymysql
from pymysql.cursors import DictCursor

logger = logging.getLogger(__name__)
ACCESS_DENIED = 1045


class DatabaseUnavailable(Exception):
    """Database or credentials unusable right now."""


class ProductNotFound(Exception):
    """Unknown product id."""


@dataclass(frozen=True)
class Settings:
    host: str = ""
    port: int = 3306
    name: str = ""
    secret_arn: str = ""
    region: str = "us-east-1"
    ssl_ca: str = "/opt/ecomm-app/certs/rds-global-bundle.pem"
    ssl_disabled: bool = False  # explicit opt-out for local development / CI only
    connect_timeout: int = 3
    read_timeout: int = 5
    secret_ttl_seconds: int = 900

    @property
    def configured(self) -> bool:
        return bool(self.host and self.name and self.secret_arn)

    @classmethod
    def from_env(cls, env: Optional[Dict[str, str]] = None) -> "Settings":
        e = os.environ if env is None else env
        d = cls()
        return cls(
            host=e.get("DB_HOST", ""),
            port=int(e.get("DB_PORT", d.port)),
            name=e.get("DB_NAME", ""),
            secret_arn=e.get("DB_SECRET_ARN", ""),
            region=e.get("AWS_REGION", e.get("AWS_DEFAULT_REGION", d.region)),
            ssl_ca=e.get("DB_SSL_CA", d.ssl_ca),
            ssl_disabled=e.get("DB_SSL_DISABLED", "").lower() in {"1", "true", "yes"},
        )


class SecretsManagerCredentials:
    """Cached (username, password) from Secrets Manager."""

    def __init__(self, secret_id: str, region: str, ttl_seconds: int = 900, client: Any = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._id, self._region, self._ttl = secret_id, region, ttl_seconds
        self._client, self._clock = client, clock
        self._lock = threading.Lock()
        self._value: Optional[Tuple[str, str]] = None
        self._at = 0.0

    def _sm(self) -> Any:
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "secretsmanager", region_name=self._region,
                config=Config(connect_timeout=3, read_timeout=5, retries={"max_attempts": 3, "mode": "standard"}))
        return self._client

    def get(self, force_refresh: bool = False) -> Tuple[str, str]:
        with self._lock:
            if self._value and not force_refresh and self._clock() - self._at < self._ttl:
                return self._value
            try:
                secret = json.loads(self._sm().get_secret_value(SecretId=self._id)["SecretString"])
                self._value = (secret["username"], secret["password"])
            except Exception as error:  # noqa: BLE001 - log the type only; messages can echo details
                logger.error("Unable to read database secret: %s", type(error).__name__)
                raise DatabaseUnavailable("database credentials unavailable") from error
            self._at = self._clock()
            return self._value


SCHEMA: Tuple[str, ...] = (
    "CREATE TABLE IF NOT EXISTS products (id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY, "
    "sku VARCHAR(32) NOT NULL, name VARCHAR(120) NOT NULL, category VARCHAR(48) NOT NULL, "
    "description VARCHAR(400) NOT NULL, price_cents INT UNSIGNED NOT NULL, "
    "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "
    "UNIQUE KEY uq_products_sku (sku), KEY idx_products_category (category)) "
    "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",
    "CREATE TABLE IF NOT EXISTS orders (id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY, "
    "product_id INT UNSIGNED NOT NULL, quantity SMALLINT UNSIGNED NOT NULL, "
    "total_cents BIGINT UNSIGNED NOT NULL, served_by VARCHAR(32) NOT NULL, served_in_az VARCHAR(16) NOT NULL, "
    "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, KEY idx_orders_created (created_at), "
    "CONSTRAINT fk_orders_product FOREIGN KEY (product_id) REFERENCES products (id)) "
    "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",
)

SEED_PRODUCTS: Tuple[Tuple[str, str, str, str, int], ...] = (
    ("KB-MECH-75", "Aero 75 Mechanical Keyboard", "Peripherals", "Hot-swappable 75% layout, PBT keycaps.", 11900),
    ("MS-ERGO-01", "Vertex Ergonomic Mouse", "Peripherals", "Vertical grip, 4000 DPI sensor.", 5900),
    ("HP-ANC-300", "Calm ANC Headphones", "Audio", "Adaptive noise cancelling, 40 h battery.", 24900),
    ("SP-BAR-20", "Pulse Desk Speaker", "Audio", "Compact stereo speaker, Bluetooth 5.3.", 7900),
    ("SK-FIDO-2", "Shield FIDO2 Security Key", "Security", "Phishing-resistant hardware MFA key.", 4900),
    ("MN-27-4K", "Prism 27-inch 4K Monitor", "Workspace", "IPS panel, 99% sRGB, USB-C 90 W.", 42900),
    ("DK-USBC-12", "Hub 12-in-1 USB-C Dock", "Workspace", "Dual HDMI, Ethernet, SD reader, 100 W.", 13900),
    ("ST-ALU-01", "Elevate Laptop Stand", "Workspace", "Foldable aluminium, six heights.", 4500),
    ("SD-1TB-X", "Rapid 1 TB Portable SSD", "Storage", "NVMe speeds up to 2,000 MB/s.", 9900),
    ("SD-2TB-X", "Rapid 2 TB Portable SSD", "Storage", "Double capacity, hardware AES-256.", 17900),
)
INSERT_PRODUCT = ("INSERT IGNORE INTO products (sku, name, category, description, price_cents) "
                  "VALUES (%s, %s, %s, %s, %s)")
PRODUCT_COLUMNS = "id, sku, name, category, description, price_cents"


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class Database:
    """Explicit data access (no ORM, parameterised SQL only)."""

    def __init__(self, settings: Settings, credentials: Optional[SecretsManagerCredentials] = None,
                 connect: Callable[..., Any] = pymysql.connect) -> None:
        self.settings = settings
        self._connect = connect
        self._credentials = credentials or SecretsManagerCredentials(
            settings.secret_arn, settings.region, settings.secret_ttl_seconds)
        self._schema_ready = False
        self._schema_lock = threading.Lock()

    def _connect_kwargs(self, user: str, password: str) -> Dict[str, Any]:
        s = self.settings
        kwargs: Dict[str, Any] = dict(
            host=s.host, port=s.port, user=user, password=password, database=s.name, charset="utf8mb4",
            cursorclass=DictCursor, connect_timeout=s.connect_timeout, read_timeout=s.read_timeout,
            write_timeout=s.read_timeout, autocommit=False)
        if not s.ssl_disabled:
            if not os.path.isfile(s.ssl_ca):
                logger.error("RDS CA bundle not found at %s", s.ssl_ca)
                raise DatabaseUnavailable("TLS certificate bundle missing")
            kwargs.update(ssl_ca=s.ssl_ca, ssl_verify_cert=True, ssl_verify_identity=True)
        return kwargs

    def _open(self) -> Any:
        if not self.settings.configured:
            raise DatabaseUnavailable("database is not configured")
        user, password = self._credentials.get()
        try:
            return self._connect(**self._connect_kwargs(user, password))
        except pymysql.err.OperationalError as error:
            if not (error.args and error.args[0] == ACCESS_DENIED):
                logger.error("Database connection failed: %s", type(error).__name__)
                raise DatabaseUnavailable("database connection failed") from error
            # Password rotated by RDS: re-read the secret once and retry.
            logger.warning("Database rejected cached credentials; refreshing secret")
            user, password = self._credentials.get(force_refresh=True)
            try:
                return self._connect(**self._connect_kwargs(user, password))
            except pymysql.MySQLError as retry_error:
                logger.error("Database login failed after refresh: %s", type(retry_error).__name__)
                raise DatabaseUnavailable("database login failed") from retry_error
        except pymysql.MySQLError as error:
            logger.error("Database connection failed: %s", type(error).__name__)
            raise DatabaseUnavailable("database connection failed") from error

    @contextmanager
    def connection(self) -> Iterator[Any]:
        conn = self._open()
        try:
            yield conn
        except pymysql.MySQLError as error:
            logger.error("Database query failed: %s", type(error).__name__)
            raise DatabaseUnavailable("database query failed") from error
        finally:
            conn.close()  # closing an uncommitted connection rolls it back

    def _rows(self, sql: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
        self.ensure_schema()
        with self.connection() as conn, conn.cursor() as cursor:
            cursor.execute(sql, params)
            return list(cursor.fetchall())

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            with self.connection() as conn:
                with conn.cursor() as cursor:
                    # Cross-process lock: several Gunicorn workers / instances may start together.
                    cursor.execute("SELECT GET_LOCK('nimbus_schema_init', 15) AS got")
                    if cursor.fetchone()["got"] != 1:
                        raise DatabaseUnavailable("schema initialisation busy")
                    try:
                        for statement in SCHEMA:
                            cursor.execute(statement)
                        cursor.executemany(INSERT_PRODUCT, SEED_PRODUCTS)
                        conn.commit()
                    finally:
                        cursor.execute("SELECT RELEASE_LOCK('nimbus_schema_init')")
            self._schema_ready = True

    def list_products(self, category: Optional[str] = None, search: Optional[str] = None,
                      limit: int = 48) -> List[Dict[str, Any]]:
        clauses: List[str] = []
        params: List[Any] = []
        if category:
            clauses.append("category = %s")
            params.append(category)
        if search:
            clauses.append("(name LIKE %s OR description LIKE %s)")
            params += ["%" + _escape_like(search) + "%"] * 2
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(max(1, min(limit, 100)))
        return self._rows(f"SELECT {PRODUCT_COLUMNS} FROM products {where} ORDER BY category, name LIMIT %s",
                          tuple(params))

    def list_categories(self) -> List[Dict[str, Any]]:
        return self._rows("SELECT category, COUNT(*) AS products FROM products GROUP BY category ORDER BY category")

    def place_order(self, product_id: int, quantity: int, served_by: str, az: str) -> Dict[str, Any]:
        """Insert an order; total comes from the stored price, never client input."""
        self.ensure_schema()
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id, name, price_cents FROM products WHERE id = %s", (product_id,))
                product = cursor.fetchone()
                if product is None:
                    conn.rollback()
                    raise ProductNotFound(str(product_id))
                total = int(product["price_cents"]) * quantity
                cursor.execute(
                    "INSERT INTO orders (product_id, quantity, total_cents, served_by, served_in_az) "
                    "VALUES (%s, %s, %s, %s, %s)", (product_id, quantity, total, served_by[:32], az[:16]))
                order_id = cursor.lastrowid
            conn.commit()
        return {"id": order_id, "product_id": product_id, "product": product["name"], "quantity": quantity,
                "total_cents": total, "served_by": served_by, "az": az}

    def recent_orders(self, limit: int = 8) -> List[Dict[str, Any]]:
        return self._rows(
            "SELECT o.id, p.name AS product, o.quantity, o.total_cents, o.served_by, o.served_in_az AS az, "
            "o.created_at FROM orders o JOIN products p ON p.id = o.product_id ORDER BY o.id DESC LIMIT %s",
            (max(1, min(limit, 50)),))

    def stats(self) -> Dict[str, int]:
        row = self._rows("SELECT (SELECT COUNT(*) FROM products) AS products, COUNT(*) AS orders FROM orders")[0]
        return {k: int(v) for k, v in row.items()}

    def ping(self) -> Dict[str, Any]:
        """Connectivity probe for /ready and the status page."""
        started = time.perf_counter()
        with self.connection() as conn, conn.cursor() as cursor:
            cursor.execute("SELECT VERSION() AS version")
            version = cursor.fetchone()["version"]
            cursor.execute("SHOW SESSION STATUS LIKE 'Ssl_cipher'")
            cipher = (cursor.fetchone() or {}).get("Value") or ("disabled" if self.settings.ssl_disabled else "unknown")
        return {"version": version, "tls_cipher": cipher, "latency_ms": round((time.perf_counter() - started) * 1000, 1)}
