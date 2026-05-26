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
        # PostgreSQL connection for Vercel
        import psycopg2
        import psycopg2.extras
        
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        conn.row_factory = psycopg2.extras.RealDictCursor
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
        
        # SQLite pragmas for performance
        for pragma in [
            "PRAGMA journal_mode=WAL",
            "PRAGMA synchronous=NORMAL",
            "PRAGMA busy_timeout=240000"
        ]:
            try:
                conn.execute(pragma)
            except Exception:
                pass
        
        return conn


def init_database():
    """Initialize database schema (same for both PostgreSQL and SQLite)"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Your existing schema initialization here
    # This will work for both databases
    
    conn.commit()
    conn.close()
