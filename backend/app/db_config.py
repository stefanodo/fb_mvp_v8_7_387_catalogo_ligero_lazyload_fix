"""Database configuration - supports both SQLite (local) and PostgreSQL (production).

This module now attempts to discover a PostgreSQL connection string from a
variety of environment variable names that marketplace integrations (like
Neon) may create with custom prefixes. It only attempts to create local
development folders when running in non-production mode.
"""
import os
import sqlite3
import threading
from pathlib import Path
from typing import Optional
import urllib.parse


def _discover_database_url() -> Optional[str]:
    """Return the first available database URL from common env names.

    Order of precedence:
    1. Common canonical names (`DATABASE_URL`, `DATABASE_URL_UNPOOLED`,
       `POSTGRES_URL`, etc.)
    2. Any environment variable with a suffix matching Neon/Vercel integration
       patterns (e.g. `*_DATABASE_URL`, `*_POSTGRES_URL`).
    3. Construct a URL from `PGHOST`/`PGUSER`/`PGPASSWORD`/`PGDATABASE` if present.
    """
    candidates = [
        "DATABASE_URL",
        "DATABASE_URL_UNPOOLED",
        "POSTGRES_URL",
        "POSTGRES_URL_NON_POOLING",
        "POSTGRES_URL_NONPOOLING",
        "POSTGRES_PRISMA_URL",
        "POSTGRES_URL_NO_SSL",
    ]
    for name in candidates:
        val = os.getenv(name)
        if val:
            return val

    # Detect integration-provided vars with prefixes (e.g. fbmvp_DATABASE_URL)
    suffixes = ("_DATABASE_URL", "_POSTGRES_URL", "_POSTGRES_URL_NON_POOLING",
                "_POSTGRES_PRISMA_URL", "_POSTGRES_URL_NO_SSL")
    for key, val in os.environ.items():
        try:
            if any(key.endswith(s) for s in suffixes):
                return val
        except Exception:
            continue

    # As a last resort, attempt to build a URL from component parts
    user = os.getenv("PGUSER") or os.getenv("POSTGRES_USER") or os.getenv("PGUSER")
    host = os.getenv("PGHOST") or os.getenv("POSTGRES_HOST") or os.getenv("PGHOST")
    password = os.getenv("PGPASSWORD") or os.getenv("POSTGRES_PASSWORD")
    database = os.getenv("PGDATABASE") or os.getenv("POSTGRES_DATABASE")
    if user and host and database and password:
        return f"postgresql://{user}:{urllib.parse.quote(password)}@{host}/{database}"

    return None


# Discover DB connection and detect production mode
DATABASE_URL = _discover_database_url()
IS_PRODUCTION = DATABASE_URL is not None and "postgres" in DATABASE_URL.lower()

# SQLite for local development (only create local dirs when not production)
if not IS_PRODUCTION:
    DB_DIR = Path.home() / "Documents" / "F&B_MAC_RUNTIME"
    try:
        DB_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        # If creating in the user's Documents fails (e.g., unusual environments),
        # fall back to a temp directory so local dev can continue.
        import tempfile
        DB_DIR = Path(tempfile.gettempdir()) / "F&B_MAC_RUNTIME"
        try:
            DB_DIR.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
    DB_PATH = DB_DIR / "fb_mvp_v8.db"
else:
    # When running in production with Postgres, DB_PATH is unused but keep a
    # value for diagnostics elsewhere in the codebase.
    DB_PATH = Path("/tmp/fb_mvp_v8.db")


def get_db_connection():
    """Get database connection - PostgreSQL in production, SQLite locally"""
    if IS_PRODUCTION:
        # PostgreSQL connection for Vercel — return a lightweight adapter that
        # emulates the sqlite3 Connection/Cursor API used across the codebase.
        # Import adapter lazily to avoid importing psycopg2 during local dev.
        from app.pg_adapter import PGConnectionAdapter

        # If a request-scoped connection was already created by `core.db()`
        # or by another caller, return it so all code paths share the same
        # connection during a request. This avoids repeated TCP connects
        # when modules call `get_db_connection()` directly.
        try:
            # Import locally to avoid circular imports at module import time.
            import app.core as _core
            try:
                existing = _core._DB_CONN.get()
                if existing is not None:
                    return existing
            except Exception:
                existing = None
        except Exception:
            existing = None

        # Establish a new raw connection (prefer psycopg2, fallback to psycopg3)
        raw_conn = None
        try:
            import psycopg2 as _psycopg2  # type: ignore
            try:
                raw_conn = _psycopg2.connect(DATABASE_URL, sslmode="require")
            except Exception as exc:
                msg = str(exc).lower()
                if "server does not support ssl" in msg or "ssl" in msg:
                    raw_conn = _psycopg2.connect(DATABASE_URL)
                else:
                    raise
        except Exception:
            try:
                import psycopg as _psycopg3  # type: ignore
                try:
                    raw_conn = _psycopg3.connect(DATABASE_URL, sslmode="require")
                except Exception:
                    raw_conn = _psycopg3.connect(DATABASE_URL)
            except Exception:
                # Re-raise a clear error for the caller so failures are visible
                raise

        adapter = PGConnectionAdapter(raw_conn)

        # Wrap the adapter in a request-scoped thin wrapper so that legacy
        # code can call `.close()` safely (no-op) and middleware will call
        # `.really_close()` at request end to perform the actual close.
        class _RequestScopedConn:
            def __init__(self, raw):
                self._raw = raw
                self._adapter = raw
                self._closed = False

            def cursor(self):
                return self._adapter.cursor()

            def commit(self):
                return self._adapter.commit()

            def rollback(self):
                return self._adapter.rollback()

            def close(self):
                # Defer actual close until middleware calls `really_close()`
                self._closed = True

            def really_close(self):
                try:
                    if hasattr(self._adapter, 'close'):
                        self._adapter.close()
                except Exception:
                    pass

            def executescript(self, sql_script: str):
                return self._adapter.executescript(sql_script)

            def execute(self, sql: str, params=None):
                return self._adapter.execute(sql, params)

            def __getattr__(self, name: str):
                return getattr(self._adapter, name)

        req_conn = _RequestScopedConn(adapter)

        # Propagate into core._DB_CONN if available so other callers (and
        # middleware) will see the same request-scoped connection.
        try:
            import app.core as _core2
            try:
                _core2._DB_CONN.set(req_conn)
            except Exception:
                pass
        except Exception:
            pass

        return req_conn
    else:
        # SQLite for local development
        conn = sqlite3.connect(
            DB_PATH,
            timeout=240,
            isolation_level="DEFERRED",
            check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        # Ensure sqlite pragmas and performance settings are applied.
        try:
            from app.db_config import ensure_sqlite_pragmas as _ensure_pragmas
        except Exception:
            _ensure_pragmas = None
        if _ensure_pragmas:
            try:
                _ensure_pragmas(conn)
            except Exception:
                pass
        # Ensure local SQLite schema is present (centralized in backend/migrate.py)
        try:
            try:
                import migrate as _migrate
            except Exception:
                try:
                    from backend import migrate as _migrate
                except Exception:
                    _migrate = None
            if _migrate and hasattr(_migrate, "ensure_sqlite_schema"):
                try:
                    _migrate.ensure_sqlite_schema(conn)
                except Exception:
                    pass
        except Exception:
            pass

        return conn


def ensure_sqlite_pragmas(conn):
    """Apply recommended SQLite pragmas to `conn` in a safe, idempotent way.

    This centralizes pragma configuration so other modules no longer execute
    raw `PRAGMA ...` statements directly.
    """
    for pragma in [
        "PRAGMA journal_mode=WAL",
        "PRAGMA synchronous=NORMAL",
        "PRAGMA foreign_keys = ON",
        "PRAGMA busy_timeout=240000",
    ]:
        try:
            conn.execute(pragma)
        except Exception:
            pass


def init_database():
    """Initialize database schema (same for both PostgreSQL and SQLite)"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Your existing schema initialization here
    # This will work for both databases
    
    conn.commit()
    conn.close()
