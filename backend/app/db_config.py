"""Database configuration - supports both SQLite (local) and PostgreSQL (production)"""
import os
import sqlite3
from pathlib import Path
from typing import Optional

# Check if we're in production (Vercel/PostgreSQL) or local (SQLite)
DATABASE_URL = os.getenv("DATABASE_URL")
IS_PRODUCTION = DATABASE_URL is not None and "postgresql" in DATABASE_URL.lower()

# SQLite for local development
DB_DIR = Path.home() / "Documents" / "F&B_MAC_RUNTIME"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "fb_mvp_v8.db"


def get_db_connection():
    """Get database connection - PostgreSQL in production, SQLite locally"""
    
    if IS_PRODUCTION:
        # PostgreSQL connection for Vercel — return a lightweight adapter that
        # emulates the sqlite3 Connection/Cursor API used across the codebase.
        # Import adapter lazily to avoid importing psycopg2 during local dev.
        from app.pg_adapter import PGConnectionAdapter
        # Try psycopg2 first (commonly installed as psycopg2-binary). If it's
        # not available, fall back to psycopg (psycopg3) which tends to have
        # prebuilt wheels on modern systems.
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
            return PGConnectionAdapter(raw)
        except Exception:
            # Try psycopg (psycopg3)
            try:
                import psycopg as _psycopg3  # type: ignore
                try:
                    raw = _psycopg3.connect(DATABASE_URL, sslmode="require")
                except Exception:
                    raw = _psycopg3.connect(DATABASE_URL)
                return PGConnectionAdapter(raw)
            except Exception:
                # Re-raise a clear error for the caller so failures are visible
                raise
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
