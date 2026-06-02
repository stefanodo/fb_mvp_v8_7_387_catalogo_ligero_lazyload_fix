"""PostgreSQL adapter that exposes a minimal sqlite3-like Connection/Cursor
interface so the existing codebase (which uses '?' qmark placeholders and
`executescript`) can run against psycopg connections with minimal changes.

This adapter performs a best-effort replacement of ``?`` placeholders with
``%s`` and uses dict-like row factories so rows behave like dicts
(``row['col']``). It prefers `psycopg2` when installed, and falls back to
`psycopg` (psycopg3) if available to reduce build issues on macOS.
"""
from __future__ import annotations

from typing import Any
import re

# Prefer psycopg2 (psycopg2-binary). If not available, attempt to import
# psycopg (psycopg3) and use its dict row factory. We keep module references
# in local names so callers can work regardless of which package is installed.
_PG2 = False
_PG3 = False
_psycopg2 = None
_psycopg2_extras = None
_psycopg3 = None
_psycopg3_rows = None
try:
    import psycopg2 as _psycopg2  # type: ignore
    import psycopg2.extras as _psycopg2_extras  # type: ignore
    _PG2 = True
except Exception:
    try:
        import psycopg as _psycopg3  # type: ignore
        import psycopg.rows as _psycopg3_rows  # type: ignore
        _PG3 = True
    except Exception:
        _psycopg2 = None
        _psycopg2_extras = None
        _psycopg3 = None
        _psycopg3_rows = None


class PGCursorAdapter:
    def __init__(self, cursor: Any):
        self._cursor = cursor
        # mark this wrapper as Postgres-backed for runtime checks
        self._is_postgres = True
        # Temporary storage for a row consumed during `execute()` (e.g. RETURNING)
        # so subsequent `fetchone()` / `fetchall()` calls still see it.
        self._pending_row = None

    def execute(self, sql: str, params=None):
        if params is None:
            params = []
        new_sql = self._convert_qmarks(sql)
        # Skip SQLite-only statements when running against Postgres.
        # This is a conservative safeguard: schema provisioning and
        # sqlite-specific DDL should be executed at build-time by
        # `backend/migrate.py`, not at runtime. If a legacy SQLite
        # token slips through, ignore it to avoid crashing the app.
        try:
            su = new_sql.strip().upper()
            if any(tok in su for tok in ("AUTOINCREMENT", "PRAGMA", "SQLITE_MASTER")):
                # No-op: preserve cursor shape but do not execute.
                self.lastrowid = None
                self._pending_row = None
                return self
        except Exception:
            # On any error while checking, fall back to attempting execution.
            pass
        try:
            self._cursor.execute(new_sql, params)
        except Exception:
            # Ensure the connection is rolled back so the transaction does
            # not remain in an aborted state (which causes
            # InFailedSqlTransaction on subsequent commands). Rollback
            # here and re-raise so callers can handle the original error.
            try:
                self._cursor.connection.rollback()
            except Exception:
                pass
            raise
        # Provide a sqlite3-like `lastrowid` compatibility layer for callers
        # that still expect `cur.lastrowid`. We try, in order:
        # 1) If the INSERT used RETURNING, fetch the returned value.
        # 2) Otherwise, attempt `SELECT LASTVAL()` on a new cursor (best-effort).
        self.lastrowid = None
        # Clear any previous pending row; we'll capture a new one if RETURNING
        self._pending_row = None
        try:
            sql_up = new_sql.strip().upper()
            if sql_up.startswith('INSERT'):
                if 'RETURNING' in sql_up:
                    try:
                        # Fetch the RETURNING row but keep it available for
                        # subsequent fetchone()/fetchall() calls by storing
                        # it in `_pending_row`.
                        row = self._cursor.fetchone()
                        self._pending_row = row
                        if row:
                            if isinstance(row, dict):
                                for v in row.values():
                                    try:
                                        self.lastrowid = int(v)
                                        break
                                    except Exception:
                                        continue
                            else:
                                try:
                                    self.lastrowid = int(row[0])
                                except Exception:
                                    self.lastrowid = None
                    except Exception:
                        self.lastrowid = None
                else:
                    try:
                        conn = self._cursor.connection
                        aux = conn.cursor()
                        aux.execute('SELECT LASTVAL()')
                        last = aux.fetchone()
                        try:
                            if isinstance(last, (list, tuple)) and last:
                                self.lastrowid = int(last[0])
                            elif last:
                                # dict-like
                                for v in (last.values() if hasattr(last, 'values') else [last]):
                                    try:
                                        self.lastrowid = int(v); break
                                    except Exception:
                                        continue
                        except Exception:
                            self.lastrowid = None
                        try:
                            aux.close()
                        except Exception:
                            pass
                    except Exception:
                        self.lastrowid = None
        except Exception:
            self.lastrowid = None
        return self

    def executemany(self, sql: str, seq_of_params):
        new_sql = self._convert_qmarks(sql)
        try:
            self._cursor.executemany(new_sql, seq_of_params)
        except Exception:
            try:
                self._cursor.connection.rollback()
            except Exception:
                pass
            raise
        return self

    def fetchone(self):
        if self._pending_row is not None:
            r = self._pending_row
            self._pending_row = None
            return r
        return self._cursor.fetchone()

    def fetchall(self):
        if self._pending_row is not None:
            first = self._pending_row
            self._pending_row = None
            rest = self._cursor.fetchall()
            if rest:
                return [first] + rest
            return [first]
        return self._cursor.fetchall()

    def fetchmany(self, size=None):
        if self._pending_row is not None:
            # If a pending row exists, return it first and then the rest.
            if size is None or size <= 1:
                r = self._pending_row
                self._pending_row = None
                return [r]
            else:
                rest = self._cursor.fetchmany(size - 1)
                r = [self._pending_row]
                self._pending_row = None
                return r + rest
        return self._cursor.fetchmany(size) if size is not None else self._cursor.fetchmany()

    def __iter__(self):
        return iter(self._cursor)

    def __getattr__(self, name: str):
        return getattr(self._cursor, name)

    @staticmethod
    def _convert_qmarks(sql: str) -> str:
        # Naive conversion: replace qmark placeholders with psycopg2 '%s'.
        # This is intentionally simple for the current codebase; avoid
        # replacing question marks in SQL literals would require full SQL
        # parsing which is out of scope here.
        if '?' not in sql and 'COLLATE' not in sql.upper():
            return sql
        sql2 = sql.replace('?', '%s')
        # Translate SQLite `COLLATE NOCASE` usage into a Postgres-friendly
        # expression. Common pattern is `ORDER BY name COLLATE NOCASE` —
        # convert that to `ORDER BY LOWER(name)`. After attempting the
        # more specific transformation, strip any remaining `COLLATE NOCASE`
        # tokens conservatively so they don't break on Postgres.
        try:
            # ORDER BY <col> [ASC|DESC] COLLATE NOCASE  ->  ORDER BY LOWER(<col>) [ASC|DESC]
            sql2 = re.sub(r"ORDER\s+BY\s+([A-Za-z0-9_\.]+)(\s+(?:ASC|DESC))?\s+COLLATE\s+NOCASE",
                          lambda m: f"ORDER BY LOWER({m.group(1)}){m.group(2) or ''}",
                          sql2,
                          flags=re.I)
            # Remove any remaining COLLATE NOCASE tokens as a fallback.
            sql2 = re.sub(r'COLLATE\s+NOCASE', '', sql2, flags=re.I)
        except Exception:
            pass
        # Convert SQLite-friendly UPSERT shorthand `INSERT OR IGNORE` into
        # Postgres-compatible `INSERT ... ON CONFLICT DO NOTHING` when needed.
        try:
            up = sql2.upper()
            if 'INSERT OR IGNORE' in up and 'ON CONFLICT' not in up:
                # Replace the `INSERT OR IGNORE` token with `INSERT` and
                # append `ON CONFLICT DO NOTHING` before RETURNING if present.
                sql2 = re.sub(r'INSERT\s+OR\s+IGNORE', 'INSERT', sql2, flags=re.I)
                if 'RETURNING' in up:
                    # Insert ON CONFLICT DO NOTHING before RETURNING clause
                    m = re.search(r'\bRETURNING\b', up)
                    if m:
                        idx = m.start()
                        sql2 = sql2[:idx] + ' ON CONFLICT DO NOTHING ' + sql2[idx:]
                else:
                    sql2 = sql2 + ' ON CONFLICT DO NOTHING'
        except Exception:
            pass
        # Convert simple `REPLACE INTO table(cols) VALUES(...)` usages into
        # `INSERT INTO ... ON CONFLICT (id) DO UPDATE SET ...` when the
        # column list contains an `id` column. This is a conservative,
        # best-effort translation to preserve semantics for common patterns
        # where `REPLACE` targets the primary key `id`.
        try:
            up = sql2.upper()
            if 'REPLACE INTO' in up:
                m = re.search(r'Replace\s+INTO\s+([A-Za-z0-9_\.]+)\s*\(([^)]+)\)\s*VALUES\s*\(', sql2, flags=re.I)
                if m:
                    tbl = m.group(1)
                    cols = [c.strip() for c in m.group(2).split(',')]
                    cols_lc = [c.lower() for c in cols]
                    if 'id' in cols_lc:
                        # Build SET clause from columns except `id` and timestamps
                        set_cols = [c for c in cols if c.lower() not in ('id', 'created_at')]
                        if set_cols:
                            set_clause = ','.join([f"{c}=EXCLUDED.{c}" for c in set_cols])
                        else:
                            set_clause = ''
                        # Replace leading token and append ON CONFLICT clause.
                        sql2 = re.sub(r'RePLACE\s+INTO', 'INSERT INTO', sql2, flags=re.I)
                        if set_clause:
                            if 'RETURNING' in up:
                                m2 = re.search(r'\bRETURNING\b', up)
                                if m2:
                                    idx = m2.start()
                                    sql2 = sql2[:idx] + f' ON CONFLICT (id) DO UPDATE SET {set_clause} ' + sql2[idx:]
                                else:
                                    sql2 = sql2 + f' ON CONFLICT (id) DO UPDATE SET {set_clause}'
                            else:
                                sql2 = sql2 + f' ON CONFLICT (id) DO UPDATE SET {set_clause}'
                        else:
                            # If there are no updatable columns, fallback to DO NOTHING
                            if 'RETURNING' in up:
                                m2 = re.search(r'\bRETURNING\b', up)
                                if m2:
                                    idx = m2.start()
                                    sql2 = sql2[:idx] + ' ON CONFLICT (id) DO NOTHING ' + sql2[idx:]
                                else:
                                    sql2 = sql2 + ' ON CONFLICT (id) DO NOTHING'
                            else:
                                sql2 = sql2 + ' ON CONFLICT (id) DO NOTHING'
        except Exception:
            pass
        return sql2


class PGConnectionAdapter:
    def __init__(self, conn: Any):
        self._conn = conn

    def cursor(self):
        # Return a cursor that yields dict-like rows
        try:
            if _PG2 and _psycopg2_extras is not None:
                cur = self._conn.cursor(cursor_factory=_psycopg2_extras.RealDictCursor)
            elif _PG3 and _psycopg3_rows is not None:
                cur = self._conn.cursor(row_factory=_psycopg3_rows.dict_row)
            else:
                cur = self._conn.cursor()
        except Exception:
            cur = self._conn.cursor()
        return PGCursorAdapter(cur)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()

    def __getattr__(self, name: str):
        return getattr(self._conn, name)

    def executescript(self, sql_script: str):
        # Very small helper to run a script containing multiple statements.
        # Split on semicolons and execute sequentially. Caller should commit.
        statements = [s.strip() for s in sql_script.split(';') if s.strip()]
        cur = self.cursor()
        for stmt in statements:
            su = stmt.strip().upper()
            # Skip SQLite-only DDL or pragmas when running against Postgres.
            # Schema provisioning for Postgres should be done with backend/migrate.py
            if any(tok in su for tok in ("AUTOINCREMENT", "PRAGMA", "SQLITE_MASTER")):
                continue
            try:
                cur.execute(stmt)
            except Exception:
                # Best-effort: ignore failing DDL statements here to avoid
                # breaking runtime when a legacy SQLite statement slips through.
                pass
        return

    def execute(self, sql: str, params=None):
        # Convenience: support `conn.execute(...)` calls present in some
        # modules which expect the sqlite3.Connection API. Return the
        # adapted cursor so callers can read `.lastrowid` or `.fetchone()`.
        cur = self.cursor()
        cur.execute(sql, params)
        return cur
