"""Test doubles: an in-memory SQLite stand-in for PyMySQL and a stub ``pymysql`` module.

SQLite is only used to exercise the application's real query paths (filters, search escaping,
JSON/HTML rendering) without a server. MySQL-specific behaviour (DDL, TLS, auth) is covered by
``test_integration_mysql.py`` in CI against a real MySQL 8.4 service container.
"""
from __future__ import annotations

import sqlite3
import sys
import types
from typing import Any, Dict, List, Optional

import db

CIPHER = "TLS_AES_256_GCM_SHA384"
SQLITE_PRODUCTS_DDL = """
CREATE TABLE products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    price_cents INTEGER NOT NULL,
    stock INTEGER NOT NULL DEFAULT 0,
    icon TEXT NOT NULL
)
"""


def translate(sql: str) -> str:
    sql = " ".join(sql.split())
    if sql.upper().startswith("SHOW SESSION STATUS"):
        return "SELECT 'Ssl_cipher' AS Variable_name, '{}' AS Value".format(CIPHER)
    return (sql.replace("%s", "?")
               .replace("INSERT IGNORE", "INSERT OR IGNORE")
               .replace("VERSION()", "sqlite_version()"))


class FakeCursor:
    def __init__(self, raw: sqlite3.Connection) -> None:
        self._cursor = raw.cursor()

    def execute(self, sql: str, params: Any = None) -> None:
        self._cursor.execute(translate(sql), tuple(params or ()))

    def executemany(self, sql: str, rows: Any) -> None:
        self._cursor.executemany(translate(sql), rows)

    def fetchone(self) -> Optional[Dict[str, Any]]:
        row = self._cursor.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self) -> List[Dict[str, Any]]:
        return [dict(row) for row in self._cursor.fetchall()]

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self._cursor.close()


class FakeConnection:
    def __init__(self, raw: sqlite3.Connection) -> None:
        self._raw = raw

    def cursor(self) -> FakeCursor:
        return FakeCursor(self._raw)

    def close(self) -> None:  # the shared in-memory database must outlive one request
        return None


class FakeStore:
    """A seeded in-memory catalog; ``connect`` has the same shape as ``db.connect``."""

    def __init__(self, seed: bool = True) -> None:
        self.raw = sqlite3.connect(":memory:", check_same_thread=False)
        self.raw.row_factory = sqlite3.Row
        self.raw.execute(SQLITE_PRODUCTS_DDL)
        if seed:
            self.raw.executemany(
                "INSERT INTO products (sku, name, category, description, price_cents, stock, icon)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                db.SEED_PRODUCTS,
            )
        self.raw.commit()

    def connect(self) -> FakeConnection:
        return FakeConnection(self.raw)

    def add(self, sku: str, name: str, category: str = "Audio", description: str = "x",
            price_cents: int = 100, stock: int = 1, icon: str = "audio") -> int:
        cur = self.raw.execute(
            "INSERT INTO products (sku, name, category, description, price_cents, stock, icon)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sku, name, category, description, price_cents, stock, icon),
        )
        self.raw.commit()
        return int(cur.lastrowid)


class RecordingConnection:
    """Records executed SQL so DDL/seed statements can be asserted without a server."""

    def __init__(self) -> None:
        self.statements: List[str] = []
        self.many: List[Any] = []

    def cursor(self) -> "RecordingConnection":
        return self

    def execute(self, sql: str, params: Any = None) -> None:
        self.statements.append(" ".join(sql.split()))

    def executemany(self, sql: str, rows: Any) -> None:
        self.statements.append(" ".join(sql.split()))
        self.many.append(list(rows))

    def fetchone(self) -> Dict[str, Any]:
        return {"total": len(self.many[-1]) if self.many else 0}

    def close(self) -> None:
        return None

    def __enter__(self) -> "RecordingConnection":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        return None


def ensure_pymysql() -> Any:
    """Return the real ``pymysql`` if installed, otherwise register a minimal stub."""
    try:
        import pymysql
        return pymysql
    except ImportError:
        pass
    module = types.ModuleType("pymysql")
    err = types.ModuleType("pymysql.err")
    cursors = types.ModuleType("pymysql.cursors")

    class OperationalError(Exception):
        pass

    class DictCursor:
        pass

    def connect(**_kwargs: Any) -> Any:
        raise OperationalError(2003, "stub pymysql: no server")

    err.OperationalError = OperationalError
    cursors.DictCursor = DictCursor
    module.err = err
    module.cursors = cursors
    module.connect = connect
    module.OperationalError = OperationalError
    sys.modules.update({"pymysql": module, "pymysql.err": err, "pymysql.cursors": cursors})
    return module
