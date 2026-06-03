from fastapi import APIRouter, HTTPException
import os
from app.core import db

router = APIRouter()


@router.get("/_verify_index")
def verify_index(token: str | None = None, create: int = 0, explain: int = 0, center_id: int = 0):
    """Temporary debug endpoint to list indexes for `inventory_sessions`.

    If the environment variable `VERIFY_INDEX_TOKEN` is set, the endpoint
    requires the same token as a query parameter to avoid accidental public
    disclosure.
    """
    secret = os.getenv("VERIFY_INDEX_TOKEN", "")
    if secret and token != secret:
        raise HTTPException(status_code=403, detail="forbidden")

    try:
        conn = db()
        cur = conn.cursor()

        # Optionally create the index (temporary route for verification)
        if int(create):
            try:
                cur.execute("CREATE INDEX IF NOT EXISTS idx_inventory_sessions_center_status ON inventory_sessions (center_id, status)")
            except Exception as e:
                # Return creation error but continue to show current indexes
                creation_error = str(e)
            else:
                creation_error = None
        else:
            creation_error = None

        sql = """
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE tablename = 'inventory_sessions'
        ORDER BY indexname
        """
        cur.execute(sql)
        rows = cur.fetchall()
        out = []
        for r in rows:
            try:
                if hasattr(r, 'keys'):
                    out.append({k: r[k] for k in r.keys()})
                elif isinstance(r, (list, tuple)):
                    out.append({"indexname": r[0], "indexdef": r[1]})
                else:
                    out.append({"raw": str(r)})
            except Exception:
                out.append({"raw": str(r)})
        # Optionally run EXPLAIN for the session_lookup query to inspect plan.
        explain_output = None
        if int(explain):
            try:
                # Prefer Postgres EXPLAIN with ANALYZE and buffers in JSON.
                expl_sql = """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT * FROM inventory_sessions
                WHERE center_id=%s AND status IN ('DRAFT','COUNTING')
                ORDER BY id DESC LIMIT 1
                """
                cur.execute(expl_sql, (int(center_id),))
                ex_rows = cur.fetchall()
                # Normalize result into a JSON-serializable structure.
                explain_output = []
                for er in ex_rows:
                    if hasattr(er, "keys"):
                        explain_output.append({k: er[k] for k in er.keys()})
                    elif isinstance(er, (list, tuple)):
                        # PostgreSQL with FORMAT JSON returns a single-column row.
                        explain_output.append(er[0] if len(er) == 1 else list(er))
                    else:
                        explain_output.append(str(er))
            except Exception as e_pg:
                # Fallback: try a SQLite-friendly EXPLAIN QUERY PLAN.
                try:
                    cur.execute(
                        "EXPLAIN QUERY PLAN SELECT * FROM inventory_sessions WHERE center_id=? AND status IN ('DRAFT','COUNTING') ORDER BY id DESC LIMIT 1",
                        (int(center_id),),
                    )
                    qp_rows = cur.fetchall()
                    explain_output = []
                    for r in qp_rows:
                        if hasattr(r, "keys"):
                            explain_output.append({k: r[k] for k in r.keys()})
                        elif isinstance(r, (list, tuple)):
                            explain_output.append(list(r))
                        else:
                            explain_output.append(str(r))
                except Exception as e_sql:
                    return {"ok": False, "error": "EXPLAIN failed", "pg_error": str(e_pg), "sqlite_error": str(e_sql)}
        return {"ok": True, "indexes": out, "creation_error": creation_error, "explain": explain_output}
    except Exception as e:
        return {"ok": False, "error": str(e)}
