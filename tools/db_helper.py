#!/usr/bin/env python3
"""Small DB helper utilities for tools to obtain table columns in a
DB-agnostic way (works with sqlite3 cursors/connections and the
Postgres adapter cursor used in production).

Keep this lightweight to avoid importing heavy deps when running
simple maintenance scripts.
"""
from __future__ import annotations
from typing import Set
try:
    # Prefer the application's helper if available
    from app.core import get_table_columns_from_cursor as _core_get_cols
except Exception:
    _core_get_cols = None


def get_table_columns(cur_or_conn, table_name: str) -> Set[str]:
    """Return a set of column names for `table_name`.

    Accepts either a sqlite3 connection/cursor or a Postgres adapter
    cursor/connection. Returns an empty set on error.
    """
    try:
        cur = cur_or_conn.cursor() if hasattr(cur_or_conn, "cursor") and callable(getattr(cur_or_conn, "cursor")) else cur_or_conn
        if _core_get_cols:
            try:
                return set(_core_get_cols(cur, table_name))
            except Exception:
                pass
        try:
            cur.execute(f"PRAGMA table_info({table_name})")
            rows = cur.fetchall()
            # Rows can be sqlite Row objects or sequences; name is at index 1
            cols = set()
            for r in rows:
                try:
                    cols.add(r[1])
                except Exception:
                    try:
                        cols.add(r.get("name"))
                    except Exception:
                        continue
            return cols
        except Exception:
            return set()
    except Exception:
        return set()
