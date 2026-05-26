from __future__ import annotations

from datetime import datetime


def update_production_note(cur, production_id: int, note: str = "") -> dict | None:
    p = cur.execute("SELECT status,center_id FROM productions WHERE id=?", (production_id,)).fetchone()
    if not p or p["status"] != "DRAFT":
        return None
    cur.execute("UPDATE productions SET note=? WHERE id=?", (((note or "").strip()), production_id))
    return {"center_id": p["center_id"]}


def delete_draft_production(cur, production_id: int) -> dict | None:
    p = cur.execute("SELECT status,center_id FROM productions WHERE id=?", (production_id,)).fetchone()
    if not p or p["status"] != "DRAFT":
        return None
    cur.execute("DELETE FROM production_lines WHERE production_id=?", (production_id,))
    cur.execute("DELETE FROM productions WHERE id=?", (production_id,))
    return {"center_id": p["center_id"]}


def reopen_production(cur, production_id: int) -> dict | None:
    p = cur.execute("SELECT status,center_id FROM productions WHERE id=?", (production_id,)).fetchone()
    if not p:
        return None
    status = (p["status"] or '').strip().upper()
    if status == 'ARCHIVED':
        cur.execute("UPDATE productions SET status='CONFIRMED' WHERE id=?", (production_id,))
        return {"center_id": p["center_id"]}
    return None


def _norm_wh_name(name: str) -> str:
    s = (name or '').strip().lower()
    return (s.replace('á','a').replace('é','e').replace('í','i').replace('ó','o').replace('ú','u'))


def _warehouse_priority(name: str, production_warehouse_id: int, warehouse_id: int) -> int:
    n = _norm_wh_name(name)
    if 'camara' in n:
        return 10
    if 'almacen' in n or 'economato' in n:
        return 20
    if 'cocina' in n:
        return 30
    if int(warehouse_id or 0) == int(production_warehouse_id or 0):
        return 40
    return 90


def _current_stock_for_item(cur, center_id: int, warehouse_id: int, item_id: int) -> float:
    row = cur.execute(
        """SELECT COALESCE(SUM(CASE WHEN movement_type IN ('ENTRADA','IN') THEN qty
                                     WHEN movement_type IN ('SALIDA','OUT') THEN -qty ELSE -qty END),0) qty
               FROM movements WHERE center_id=? AND warehouse_id=? AND item_id=?""",
        (int(center_id), int(warehouse_id), int(item_id)),
    ).fetchone()
    return float(row['qty'] if row else 0.0)


def _insert_movement(cur, center_id: int, warehouse_id: int, item_id: int, mv_type: str, qty: float, unit: str, now: str, note: str):
    if float(qty or 0.0) <= 0:
        return
    cur.execute(
        """INSERT INTO movements(center_id,warehouse_id,item_id,movement_type,qty,unit,created_at,note)
           VALUES(?,?,?,?,?,?,?,?)""",
        (int(center_id), int(warehouse_id), int(item_id), mv_type, float(qty), unit, now, note),
    )


def _consume_from_operational_warehouses(cur, center_id: int, production_warehouse_id: int, item_id: int, qty_needed: float, unit: str, now: str, note: str) -> int:
    """Descuenta una salida de producción desde la ubicación real del stock.
    Prioridad operativa: Cámara -> Almacén/Economato -> Cocina -> almacén de la producción -> resto.
    Si no hay stock suficiente, registra el residual en el almacén más razonable para dejar visible el faltante.
    """
    remaining = float(qty_needed or 0.0)
    inserted = 0
    whs = cur.execute("SELECT id,name FROM warehouses WHERE center_id=? ORDER BY id", (int(center_id),)).fetchall()
    scored = []
    for w in whs:
        wid = int(w['id'])
        stock = _current_stock_for_item(cur, center_id, wid, item_id)
        scored.append((_warehouse_priority(w['name'] or '', production_warehouse_id, wid), wid, w['name'] or '', stock))
    scored.sort(key=lambda x: (x[0], x[1]))
    for _prio, wid, _name, stock in scored:
        if remaining <= 0:
            break
        if stock <= 0:
            continue
        take = min(remaining, stock)
        _insert_movement(cur, center_id, wid, item_id, 'SALIDA', take, unit, now, note + ' · consumo automático por almacén real')
        inserted += 1
        remaining -= take
    if remaining > 0.000001:
        # Residual visible: si falta stock, no se oculta. Se imputa al primer almacén operativo disponible.
        fallback = None
        for _prio, wid, _name, _stock in scored:
            fallback = wid
            if wid == int(production_warehouse_id or 0):
                break
        fallback = fallback or int(production_warehouse_id or 0)
        _insert_movement(cur, center_id, fallback, item_id, 'SALIDA', remaining, unit, now, note + ' · faltante visible')
        inserted += 1
    return inserted


def confirm_production(cur, production_id: int) -> dict | None:
    p = cur.execute("SELECT * FROM productions WHERE id=?", (production_id,)).fetchone()
    if not p or str(p["status"] or '').strip().upper() != "DRAFT":
        return None
    lines = cur.execute("SELECT * FROM production_lines WHERE production_id=? ORDER BY id", (production_id,)).fetchall()
    if not lines:
        return None

    # Blindaje: si hay consumos OUT pero falta entrada IN de elaborado, crear entrada desde la receta vinculada por nota.
    try:
        has_in = any(str(ln["line_type"] or '').strip().upper() in {"IN","ENTRADA","PRODUCCION","PRODUCCIÓN"} for ln in lines)
        has_out = any(str(ln["line_type"] or '').strip().upper() in {"OUT","SALIDA"} for ln in lines)
        if has_out and not has_in:
            raw_note = str(p["note"] or '').strip()
            candidates = []
            for part in raw_note.replace(' + ', '|').split('|'):
                name = part.split('·',1)[0].strip()
                if name:
                    candidates.append(name)
            rec = None
            for name in candidates:
                rec = cur.execute(
                    "SELECT id,name,yield_final_qty,yield_final_unit,COALESCE(produced_item_id,0) produced_item_id FROM recipes WHERE lower(trim(name))=lower(trim(?)) ORDER BY id LIMIT 1",
                    (name,),
                ).fetchone()
                if rec:
                    break
            if rec:
                item = None
                pid_item = int(rec["produced_item_id"] or 0)
                if pid_item > 0:
                    item = cur.execute("SELECT id,unit FROM items WHERE id=?", (pid_item,)).fetchone()
                if not item:
                    item = cur.execute("SELECT id,unit FROM items WHERE lower(trim(name))=lower(trim(?)) ORDER BY id LIMIT 1", ((rec["name"] or '').strip(),)).fetchone()
                if item:
                    from app.core import _unit_factor
                    qty = float(rec["yield_final_qty"] or 0.0) or 1.0
                    unit_in = (rec["yield_final_unit"] or item["unit"] or 'kg').strip() or 'kg'
                    base_unit = (item["unit"] or 'ud').strip() or 'ud'
                    qty_base = qty * float(_unit_factor(unit_in, base_unit) or 1.0)
                    cur.execute(
                        "INSERT INTO production_lines(production_id,line_type,item_id,qty_base,input_unit,qty_input) VALUES(?,?,?,?,?,?)",
                        (production_id, 'IN', int(item["id"]), float(qty_base), unit_in, qty),
                    )
                    lines = cur.execute("SELECT * FROM production_lines WHERE production_id=? ORDER BY id", (production_id,)).fetchall()
    except Exception:
        pass

    now = datetime.utcnow().isoformat()
    note = (p["note"] or "").strip()
    base_note = f"PRODUCCIÓN #{production_id}" + (f" · {note}" if note else "")
    movement_count = 0
    for ln in lines:
        line_type = str(ln["line_type"] or '').strip().upper()
        item = cur.execute("SELECT unit FROM items WHERE id=?", (ln["item_id"],)).fetchone()
        unit = (item["unit"] if item else "") or "ud"
        if line_type in {"OUT", "SALIDA"}:
            movement_count += _consume_from_operational_warehouses(
                cur, int(p["center_id"]), int(p["warehouse_id"]), int(ln["item_id"]), float(ln["qty_base"]), unit, now, base_note
            )
        else:
            # El elaborado terminado entra en el almacén elegido para la producción.
            _insert_movement(cur, int(p["center_id"]), int(p["warehouse_id"]), int(ln["item_id"]), 'ENTRADA', float(ln["qty_base"]), unit, now, base_note)
            movement_count += 1
    cur.execute("UPDATE productions SET status='CONFIRMED' WHERE id=?", (production_id,))
    return {"center_id": p["center_id"], "line_count": len(lines), "movement_count": movement_count}


def archive_production(cur, production_id: int) -> dict | None:
    p = cur.execute("SELECT status,center_id FROM productions WHERE id=?", (production_id,)).fetchone()
    if not p or p["status"] != "CONFIRMED":
        return None
    cur.execute("UPDATE productions SET status='ARCHIVED' WHERE id=?", (production_id,))
    return {"center_id": p["center_id"]}


def restore_archived_production(cur, production_id: int) -> dict | None:
    p = cur.execute("SELECT status,center_id FROM productions WHERE id=?", (production_id,)).fetchone()
    if not p or p["status"] != "ARCHIVED":
        return None
    cur.execute("UPDATE productions SET status='CONFIRMED' WHERE id=?", (production_id,))
    return {"center_id": p["center_id"]}
