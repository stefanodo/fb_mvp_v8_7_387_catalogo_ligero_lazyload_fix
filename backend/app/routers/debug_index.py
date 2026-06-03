from fastapi import APIRouter, HTTPException
import os
from app.core import db

router = APIRouter()


@router.get("/_verify_index")
def verify_index(token: str | None = None):
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
        return {"ok": True, "indexes": out}
    except Exception as e:
        return {"ok": False, "error": str(e)}
