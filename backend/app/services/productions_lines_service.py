from __future__ import annotations

from app.core import ensure_columns, get_unit_factor, _parse_float, safe_insert_returning
from app.services.productions_service import get_draft_production, resolve_line_payload


def add_manual_line(cur, production_id: int, line_type: str, item_id: str = "", item_query: str = "", qty_value: str = "", qty_unit: str = "") -> dict | None:
    ensure_columns(cur)
    line_type = (line_type or "").upper().strip()
    if line_type not in {"OUT", "IN"}:
        return None
    p = get_draft_production(cur, production_id)
    if not p or p["status"] != "DRAFT":
        return None
    payload = resolve_line_payload(cur, item_id=item_id, item_query=item_query, qty_value=qty_value, qty_unit=qty_unit)
    if not payload or float(payload["qty_base"] or 0.0) <= 0:
        return None
    existing = cur.execute(
        "SELECT id, qty_base, qty_input FROM production_lines WHERE production_id=? AND line_type=? AND item_id=? AND input_unit=? ORDER BY id LIMIT 1",
        (production_id, line_type, int(payload["item_id"]), str(payload["input_unit"] or 'ud'))
    ).fetchone()
    if existing:
        new_qty_base = float(existing["qty_base"] or 0.0) + float(payload["qty_base"] or 0.0)
        new_qty_input = float(existing["qty_input"] or 0.0) + float(payload["qty_input"] or 0.0)
        cur.execute(
            "UPDATE production_lines SET qty_base=?, qty_input=? WHERE id=? AND production_id=?",
            (new_qty_base, new_qty_input, int(existing["id"]), production_id),
        )
        return {"center_id": p["center_id"], "line_id": int(existing["id"])}
    # Insert production line in a DB-agnostic way
    sqlite_sql = "INSERT INTO production_lines(production_id,line_type,item_id,qty_base,input_unit,qty_input) VALUES(?,?,?,?,?,?)"
    pg_sql = sqlite_sql.replace('?', '%s')
    line_id = safe_insert_returning(
        cur,
        sqlite_sql,
        (production_id, line_type, payload["item_id"], payload["qty_base"], payload["input_unit"], payload["qty_input"]),
        pg_sql=pg_sql,
    ) or 0
    return {"center_id": p["center_id"], "line_id": int(line_id)}


def update_line_qty(cur, production_id: int, line_id: int, qty_value: str, qty_unit: str) -> dict | None:
    p = cur.execute("SELECT status,center_id FROM productions WHERE id=?", (production_id,)).fetchone()
    if not p or p["status"] != "DRAFT":
        return None
    ln = cur.execute("SELECT id,item_id FROM production_lines WHERE id=? AND production_id=?", (line_id, production_id)).fetchone()
    if not ln:
        return None
    qty_input = _parse_float(qty_value, 0.0)
    if qty_input <= 0:
        return None
    item = cur.execute("SELECT unit FROM items WHERE id=?", (int(ln["item_id"]),)).fetchone()
    base_unit = (item["unit"] if item else "g") or "g"
    factor = get_unit_factor(qty_unit, base_unit)
    qty_base = qty_input * factor
    if float(qty_base or 0.0) <= 0:
        return None
    cur.execute("UPDATE production_lines SET qty_base=?,input_unit=?,qty_input=? WHERE id=? AND production_id=?", (qty_base, qty_unit, qty_input, line_id, production_id))
    return {"center_id": p["center_id"]}


def delete_line(cur, production_id: int, line_id: int) -> dict | None:
    p = cur.execute("SELECT status,center_id FROM productions WHERE id=?", (production_id,)).fetchone()
    if not p or p["status"] != "DRAFT":
        return None
    cur.execute("DELETE FROM production_lines WHERE id=? AND production_id=?", (line_id, production_id))
    return {"center_id": p["center_id"]}
