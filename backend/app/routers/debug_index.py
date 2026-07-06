from fastapi import APIRouter, HTTPException
import os
from typing import Optional
from app.core import db

router = APIRouter()


@router.get("/_verify_index")
def verify_index(token: Optional[str] = None, create: int = 0, explain: int = 0,
                 center_id: int = 0, session_id: int = 0, which: Optional[str] = None):
    """Lightweight debug endpoint to inspect/create indexes and run simple
    DB pings. Protected by VERIFY_INDEX_TOKEN when configured.
    """
    secret = os.getenv("VERIFY_INDEX_TOKEN", "")
    if secret and token != secret:
        raise HTTPException(status_code=403, detail="forbidden")

    try:
        conn = db()
        cur = conn.cursor()
    except Exception as e:
        return {"ok": False, "error": "db_connect_failed", "exc": str(e)}

    creation_error = None
    if int(create):
        try:
            cur.execute("CREATE INDEX IF NOT EXISTS idx_inventory_sessions_center_status ON inventory_sessions (center_id, status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_inventory_counts_session_id ON inventory_counts (session_id)")
        except Exception as e:
            creation_error = str(e)

    out = []
    explain_output = None
    # Try Postgres-style index listing first, fallback to SQLite PRAGMA
    try:
        cur.execute("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'inventory_sessions' ORDER BY indexname")
        rows = cur.fetchall()
        for r in rows:
            if hasattr(r, 'keys'):
                out.append({k: r[k] for k in r.keys()})
            elif isinstance(r, (list, tuple)):
                out.append({"indexname": r[0], "indexdef": r[1]})
            else:
                out.append({"raw": str(r)})
    except Exception:
        try:
            cur.execute("PRAGMA index_list('inventory_sessions')")
            rows = cur.fetchall()
            for r in rows:
                out.append({"raw": str(r)})
        except Exception as e:
            return {"ok": False, "error": "list_indexes_failed", "exc": str(e)}

    if int(explain):
        which_q = (which or 'session_lookup').lower()
        try:
            if which_q == 'session_lookup':
                cur.execute("EXPLAIN QUERY PLAN SELECT 1")
                ex = cur.fetchall()
                explain_output = [str(r) for r in ex]
            else:
                explain_output = [f"explain for {which_q} not implemented"]
        except Exception as e:
            explain_output = [f"explain_failed: {e}"]

    # Optional ping: triggered by which=ping_db
    if (which or '').lower() == 'ping_db':
        try:
            import time
            t0 = time.time()
            conn2 = db()
            t_conn = time.time() - t0
            cur2 = conn2.cursor()
            t_q0 = time.time()
            cur2.execute('SELECT 1')
            _ = cur2.fetchone()
            t_q = time.time() - t_q0
            try:
                conn2.close()
            except Exception:
                pass
            return {"ok": True, "db_connect_time": f"{t_conn:.3f}s", "simple_query_time": f"{t_q:.3f}s"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    return {"ok": True, "indexes": out, "creation_error": creation_error, "explain": explain_output}
