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
        # Prefer a process-local connection pool (psycopg2) to avoid creating
        # a fresh TCP/SSL connection on every `get_db_connection()` call.
        # Pool is lazily initialized on first use. If psycopg2 is not
        # available, fall back to direct connects while attempting to reuse
        # a request-scoped connection (if `app.core._DB_CONN` exists).
        from app.pg_adapter import PGConnectionAdapter

        # Module-level pool globals
        global _PG_POOL, _PG_POOL_LOCK, _PG_POOL_DRIVER
        try:
            _PG_POOL
        except NameError:
            _PG_POOL = None
            _PG_POOL_LOCK = threading.Lock()
            _PG_POOL_DRIVER = None

        def _init_pool():
            nonlocal_vars = globals()
            with _PG_POOL_LOCK:
                if globals().get("_PG_POOL") is not None:
                    return
                min_size = int(os.getenv("PG_POOL_MIN", "1"))
                max_size = int(os.getenv("PG_POOL_MAX", os.getenv("PG_CONN_POOL_SIZE", "6")))
                # Try psycopg2 ThreadedConnectionPool first
                try:
                    import psycopg2 as _psycopg2  # type: ignore
                    from psycopg2.pool import ThreadedConnectionPool  # type: ignore
                    try:
                        pool = ThreadedConnectionPool(min_size, max_size, DATABASE_URL)
                    except TypeError:
                        # Some older psycopg2 versions expect dsn as keyword
                        pool = ThreadedConnectionPool(min_size, max_size, dsn=DATABASE_URL)
                    globals()['_PG_POOL'] = pool
                    globals()['_PG_POOL_DRIVER'] = 'psycopg2'
                    return
                except Exception:
                    globals()['_PG_POOL'] = None
                    globals()['_PG_POOL_DRIVER'] = None
                    # Do not raise here; fall back to direct connects below

        # Lazy-init pool (best-effort)
        try:
            if _PG_POOL is None:
                _init_pool()
        except Exception:
            pass

        # If pool available (psycopg2), get a connection from it and return
        # a wrapper that returns the conn to the pool on `close()`.
        if globals().get('_PG_POOL') is not None and globals().get('_PG_POOL_DRIVER') == 'psycopg2':
            try:
                pool = globals()['_PG_POOL']
                raw = pool.getconn()
                adapter = PGConnectionAdapter(raw)

                class _PooledConn:
                    def __init__(self, raw_conn, adapter, pool):
                        self._raw = raw_conn
                        self._adapter = adapter
                        self._pool = pool

                    def cursor(self):
                        return self._adapter.cursor()

                    def commit(self):
                        return self._adapter.commit()

                    def rollback(self):
                        return self._adapter.rollback()

                    def close(self):
                        try:
                            self._pool.putconn(self._raw)
                        except Exception:
                            try:
                                self._raw.close()
                            except Exception:
                                pass

                    def executescript(self, sql_script: str):
                        return self._adapter.executescript(sql_script)

                    def execute(self, sql: str, params=None):
                        return self._adapter.execute(sql, params)

                    def __getattr__(self, name: str):
                        return getattr(self._adapter, name)

                return _PooledConn(raw, adapter, pool)
            except Exception:
                # Fall through to direct connect below
                pass

        # No pool available — attempt to reuse a per-request connection when
        # possible by storing it in `app.core._DB_CONN` (if present).
        try:
            from app.core import _DB_CONN
        except Exception:
            _DB_CONN = None

        # If a request-scoped connection exists, return it.
        try:
            if _DB_CONN is not None:
                existing = _DB_CONN.get()
                if existing is not None:
                    return existing
        except Exception:
            pass

        # Finally, fall back to direct connect (psycopg2 then psycopg3)
        try:
            import psycopg2 as _psycopg2  # type: ignore
            try:
                raw = _psycopg2.connect(DATABASE_URL, sslmode="require")
            except Exception as exc:
                msg = str(exc).lower()
                if "server does not support ssl" in msg or "ssl" in msg:
                    raw = _psycopg2.connect(DATABASE_URL)
                else:
                    raise
            conn = PGConnectionAdapter(raw)
        except Exception:
            try:
                import psycopg as _psycopg3  # type: ignore
                try:
                    raw = _psycopg3.connect(DATABASE_URL, sslmode="require")
                except Exception:
                    raw = _psycopg3.connect(DATABASE_URL)
                conn = PGConnectionAdapter(raw)
            except Exception:
                raise

        # If request-scoped storage is available, save this connection so
        # subsequent get_db_connection() calls during the same request reuse it.
        try:
            if _DB_CONN is not None:
                class _ReqConnWrapper:
                    def __init__(self, adapter_conn):
                        self._adapter = adapter_conn

                    def cursor(self):
                        return self._adapter.cursor()

                    def commit(self):
                        return self._adapter.commit()

                    def rollback(self):
                        return self._adapter.rollback()

                    def close(self):
                        # deferred — leave to middleware to really close
                        pass

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

                req_conn = _ReqConnWrapper(conn)
                try:
                    _DB_CONN.set(req_conn)
                except Exception:
                    pass
                return req_conn
        except Exception:
            pass

        return conn
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
