from fastapi import APIRouter, HTTPException
import os
from app.core import db

router = APIRouter()


@router.get("/_verify_index")
def verify_index(token: str | None = None, create: int = 0, explain: int = 0, center_id: int = 0, session_id: int = 0, which: str | None = None):
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
        # Optionally run EXPLAIN for known queries to inspect plan.
        explain_output = None
        if int(explain):
            which_q = (which or 'session_lookup').lower()
            try:
                if which_q == 'session_lookup':
                    expl_sql = """
                    EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                    SELECT * FROM inventory_sessions
                    WHERE center_id=%s AND status IN ('DRAFT','COUNTING')
                    ORDER BY id DESC LIMIT 1
                    """
                    cur.execute(expl_sql, (int(center_id),))
                elif which_q == 'counts_map':
                    expl_sql = """
                    EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                    SELECT * FROM inventory_counts WHERE session_id=%s ORDER BY id
                    """
                    cur.execute(expl_sql, (int(session_id),))
                elif which_q == 'production_stocks':
                    # Use the same query shape as `get_production_stocks` in core.py
                    center_where = "WHERE c.id=%s" if int(center_id) else ""
                    params = (int(center_id),) if int(center_id) else ()
                    expl_sql = f"""
                    EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                    WITH produced_items AS (
                        SELECT DISTINCT pl.item_id
                          FROM productions p
                          JOIN production_lines pl ON pl.production_id=p.id
                         WHERE UPPER(COALESCE(p.status,'')) IN ('CONFIRMED','CONFIRMADA','CONFIRMADO','ARCHIVED','ARCHIVADA','ARCHIVADO')
                           AND UPPER(COALESCE(pl.line_type,'')) IN ('IN','ENTRADA','PRODUCCION','PRODUCCIÓN')
                        UNION
                        SELECT DISTINCT produced_item_id
                          FROM recipes
                         WHERE COALESCE(produced_item_id,0)>0
                    )
                    SELECT c.id center_id,
                           c.name center_name,
                           w.id warehouse_id,
                           w.name warehouse_name,
                           i.id item_id,
                           i.name item_name,
                           i.unit,
                           i.current_price,
                           COALESCE(SUM(CASE
                               WHEN m.movement_type IN ('ENTRADA','IN')  THEN m.qty
                               WHEN m.movement_type IN ('SALIDA','OUT')  THEN -m.qty
                               ELSE 0
                           END), 0) stock_qty
                      FROM centers c
                      JOIN warehouses w ON w.center_id=c.id
                      JOIN produced_items pi ON 1=1
                      JOIN items i ON i.id=pi.item_id
                      LEFT JOIN movements m ON m.center_id=c.id
                                            AND m.warehouse_id=w.id
                                            AND m.item_id=i.id
                      {center_where}
                     GROUP BY c.id, c.name, w.id, w.name, i.id, i.name, i.unit, i.current_price
                        HAVING ABS(COALESCE(SUM(CASE
                                             WHEN m.movement_type IN ('ENTRADA','IN')  THEN m.qty
                                             WHEN m.movement_type IN ('SALIDA','OUT')  THEN -m.qty
                                             ELSE 0 END), 0)) > 0.000001
                        OR (
                             SELECT p.id
                                 FROM productions p
                                 JOIN production_lines pl ON pl.production_id=p.id
                                WHERE UPPER(COALESCE(p.status,'')) IN ('CONFIRMED','CONFIRMADA','CONFIRMADO','ARCHIVED','ARCHIVADA','ARCHIVADO')
                                  AND UPPER(COALESCE(pl.line_type,'')) IN ('IN','ENTRADA','PRODUCCION','PRODUCCIÓN')
                                  AND pl.item_id=i.id
                                  AND p.center_id=c.id
                                  AND p.warehouse_id=w.id
                                ORDER BY p.id DESC LIMIT 1
                        ) IS NOT NULL
                     ORDER BY c.name, w.name, i.name
                    """
                    cur.execute(expl_sql, params)
                else:
                    return {"ok": False, "error": f"unknown explain target: {which_q}"}
                ex_rows = cur.fetchall()
                explain_output = []
                for er in ex_rows:
                    if hasattr(er, "keys"):
                        explain_output.append({k: er[k] for k in er.keys()})
                    elif isinstance(er, (list, tuple)):
                        explain_output.append(er[0] if len(er) == 1 else list(er))
                    else:
                        explain_output.append(str(er))
            except Exception as e_pg:
                try:
                    # Fallback to a generic SQLite EXPLAIN QUERY PLAN when possible
                    cur.execute("EXPLAIN QUERY PLAN SELECT 1")
                    qp_rows = cur.fetchall()
                    explain_output = [str(r) for r in qp_rows]
                except Exception:
                    return {"ok": False, "error": "EXPLAIN failed", "pg_error": str(e_pg)}
        return {"ok": True, "indexes": out, "creation_error": creation_error, "explain": explain_output}
    except Exception as e:
        return {"ok": False, "error": str(e)}
