from fastapi import APIRouter, HTTPException
import os
from app.core import db

router = APIRouter()


@router.get("/_verify_index")
def verify_index(token: str | None = None, create: int = 0):
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
        return {"ok": True, "indexes": out, "creation_error": creation_error}
    except Exception as e:
        return {"ok": False, "error": str(e)}
