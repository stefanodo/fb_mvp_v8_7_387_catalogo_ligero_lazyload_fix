from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import RedirectResponse
from datetime import datetime

from app.core import db, ensure_columns, _unit_factor

router = APIRouter()


def _safe_float(val, default: float = 0.0) -> float:
    try:
        return float(str(val or '').replace(',', '.').strip() or default)
    except (ValueError, TypeError):
        return default

def _norm_inv_unit(val: str) -> str:
    u = (val or '').strip().lower()
    aliases = {
        'racion': 'ración', 'raciones': 'ración', 'porcion': 'ración', 'porciones': 'ración',
        'lotes': 'lote', 'lt': 'l', 'lts': 'l'
    }
    return aliases.get(u, u or 'ud')


def _production_count_factor(cur, *, item_id: int, item_name: str, count_unit: str, base_unit: str) -> tuple[float, str]:
    """Convierte conteos de producciones en ración/lote a la unidad base del artículo.

    - ración = rendimiento final / nº de raciones de la receta vinculada.
    - lote = rendimiento final completo de la receta vinculada.
    Si no hay receta vinculada, vuelve a 1.0 y deja aviso en nota.
    """
    cu = _norm_inv_unit(count_unit)
    bu = (base_unit or 'ud').strip().lower() or 'ud'
    if cu not in {'ración', 'lote'}:
        return float(_unit_factor(cu, bu) or 1.0), ''
    rec = None
    try:
        rec = cur.execute(
            """SELECT id,name,COALESCE(yield_final_qty,0) yield_final_qty,
                      COALESCE(yield_final_unit,?) yield_final_unit, COALESCE(yield_portions,0) yield_portions
                 FROM recipes
                WHERE COALESCE(produced_item_id,0)=?
                   OR lower(trim(name))=lower(trim(?))
                ORDER BY CASE WHEN COALESCE(produced_item_id,0)=? THEN 0 ELSE 1 END, id
                LIMIT 1""",
            (bu, int(item_id or 0), (item_name or '').strip(), int(item_id or 0)),
        ).fetchone()
    except Exception:
        rec = None
    if not rec:
        return 1.0, 'sin receta vinculada para convertir ración/lote'
    yq = float(rec['yield_final_qty'] or 0.0)
    yu = (rec['yield_final_unit'] or bu).strip().lower() or bu
    yp = float(rec['yield_portions'] or 0.0)
    if yq <= 0:
        return 1.0, 'receta sin rendimiento final para convertir ración/lote'
    yq_base = yq * float(_unit_factor(yu, bu) or 1.0)
    if cu == 'ración':
        if yp <= 0:
            return 1.0, 'receta sin nº de raciones para convertir ración'
        return yq_base / yp, ''
    return yq_base, ''


def _allowed_inventory_modes_for_warehouse(warehouse_name: str | None):
    n = (warehouse_name or '').strip().lower()
    if n in ('economato',):
        return {'limpieza', 'libres'}
    if n in ('cocina', 'camara', 'cámara'):
        return {'materias_primas', 'producciones', 'libres'}
    return {'materias_primas', 'producciones', 'limpieza', 'libres'}


def _inventory_warehouse_belongs(cur, warehouse_id: int, center_id: int) -> bool:
    try:
        row = cur.execute("SELECT 1 FROM warehouses WHERE id=? AND center_id=?", (int(warehouse_id), int(center_id))).fetchone()
        return bool(row)
    except Exception:
        return False


def _normalize_inventory_warehouse_id(cur, warehouse_id: int, center_id: int) -> int:
    """Devuelve un almacén válido para el centro o 0 = Todos.

    Si una sesión queda con un warehouse_id de otro local, la navegación por bloques
    no debe romperse con warehouse_invalid. En ese caso se vuelve a Todos.
    """
    try:
        wid = int(warehouse_id or 0)
    except Exception:
        wid = 0
    if wid <= 0:
        return 0
    return wid if _inventory_warehouse_belongs(cur, wid, int(center_id or 0)) else 0



def _ensure_inventory_audit_schema(cur) -> None:
    audit_cols = {
        "original_counted_by_user_id": "INTEGER NOT NULL DEFAULT 0",
        "original_counted_by_name": "TEXT NOT NULL DEFAULT ''",
        "original_counted_at": "TEXT NOT NULL DEFAULT ''",
        "last_modified_by_user_id": "INTEGER NOT NULL DEFAULT 0",
        "last_modified_by_name": "TEXT NOT NULL DEFAULT ''",
        "last_modified_at": "TEXT NOT NULL DEFAULT ''",
        "previous_physical_qty": "REAL",
        "previous_count_unit": "TEXT NOT NULL DEFAULT ''",
        "modified_count": "INTEGER NOT NULL DEFAULT 0",
    }
    try:
        existing = {r[1] for r in cur.execute("PRAGMA table_info(inventory_counts)").fetchall()}
        for col, ddl in audit_cols.items():
            if col not in existing:
                cur.execute(f"ALTER TABLE inventory_counts ADD COLUMN {col} {ddl}")
    except Exception:
        pass
    try:
        cur.execute("""CREATE TABLE IF NOT EXISTS inventory_count_audit(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL DEFAULT 0,
            inventory_count_id INTEGER NOT NULL DEFAULT 0,
            item_id INTEGER NOT NULL DEFAULT 0,
            item_name TEXT NOT NULL DEFAULT '',
            source_type TEXT NOT NULL DEFAULT '',
            family_key TEXT NOT NULL DEFAULT '',
            warehouse_id INTEGER NOT NULL DEFAULT 0,
            previous_physical_qty REAL,
            previous_count_unit TEXT NOT NULL DEFAULT '',
            new_physical_qty REAL,
            new_count_unit TEXT NOT NULL DEFAULT '',
            changed_by_user_id INTEGER NOT NULL DEFAULT 0,
            changed_by_name TEXT NOT NULL DEFAULT '',
            changed_at TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT ''
        )""")
    except Exception:
        pass


def _count_changed(existing, pqty: float, cunit: str, checked: int, note: str) -> bool:
    if not existing:
        return False
    try:
        if abs(float(existing['physical_qty'] or 0) - float(pqty or 0)) > 0.000001:
            return True
    except Exception:
        return True
    if str(existing['count_unit'] or '') != str(cunit or ''):
        return True
    if int(existing['is_checked'] or 0) != int(checked or 0):
        return True
    if str(existing['note'] or '') != str(note or ''):
        return True
    return False

def _redirect(session_id: int, center_id: int, mode: str, family: str, msg: str = "", anchor: str = "inventoryWorkArea"):
    extra = f"&inv_msg={msg}" if msg else ""
    return RedirectResponse(
        url=f"/?page=inventario&center_id={int(center_id or 0)}&inv_session_id={int(session_id)}&inv_mode={mode}&inv_family={family}{extra}#{anchor or 'inventoryWorkArea'}",
        status_code=303,
    )


@router.post('/inventory/session/create_form')
def inventory_session_create_form(
    center_id: int = Form(0),
    warehouse_id: int = Form(0),
    session_type: str = Form('MIXTO'),
    responsible_user_id: int = Form(0),
    note: str = Form(''),
):
    conn = db(); cur = conn.cursor(); ensure_columns(cur)
    rid = int(responsible_user_id or 0)
    if rid <= 0:
        conn.close()
        return _redirect(0, center_id, 'materias_primas', 'verduras', 'responsible_required')
    resp = cur.execute("SELECT name FROM users WHERE id=? AND is_active=1", (rid,)).fetchone()
    if not resp:
        conn.close()
        return _redirect(0, center_id, 'materias_primas', 'verduras', 'responsible_required')
    warehouse_id = _normalize_inventory_warehouse_id(cur, warehouse_id, center_id)
    cur.execute(
        "INSERT INTO inventory_sessions(center_id,warehouse_id,session_type,status,created_at,note,responsible_user_id,responsible_name) VALUES(?,?,?,?,?,?,?,?)",
        (int(center_id or 0), int(warehouse_id or 0), (session_type or 'MIXTO').upper()[:20], 'DRAFT', datetime.utcnow().isoformat(), (note or '').strip(), rid, (resp['name'] or '').strip()),
    )
    sid = int(cur.lastrowid or 0)
    conn.commit(); conn.close()
    return _redirect(sid, center_id, 'materias_primas', 'verduras', 'session_created')


@router.post('/inventory/session/update_form')
def inventory_session_update_form(
    session_id: int = Form(...),
    center_id: int = Form(0),
    warehouse_id: int = Form(0),
    responsible_user_id: int = Form(0),
    status: str = Form('COUNTING'),
    note: str = Form(''),
    inv_mode: str = Form('materias_primas'),
    inv_family: str = Form('verduras'),
):
    conn = db(); cur = conn.cursor(); ensure_columns(cur)
    rid = int(responsible_user_id or 0)
    if rid <= 0:
        conn.close()
        return _redirect(session_id, center_id, inv_mode, inv_family, 'responsible_required')
    resp = cur.execute("SELECT name FROM users WHERE id=? AND is_active=1", (rid,)).fetchone()
    if not resp:
        conn.close()
        return _redirect(session_id, center_id, inv_mode, inv_family, 'responsible_required')
    warehouse_id = _normalize_inventory_warehouse_id(cur, warehouse_id, center_id)
    cur.execute(
        "UPDATE inventory_sessions SET warehouse_id=?, responsible_user_id=?, responsible_name=?, status=?, note=? WHERE id=?",
        (int(warehouse_id or 0), rid, (resp['name'] or '').strip(), (status or 'COUNTING').upper()[:20], (note or '').strip(), int(session_id)),
    )
    conn.commit(); conn.close()
    return _redirect(session_id, center_id, inv_mode, inv_family, 'session_saved')


@router.post('/inventory/counts/save_form')
def inventory_counts_save_form(
    session_id: int = Form(...),
    center_id: int = Form(0),
    inv_mode: str = Form('materias_primas'),
    inv_family: str = Form('verduras'),
    source_type: str = Form('raw'),
    item_id: list[str] = Form([]),
    item_name: list[str] = Form([]),
    warehouse_id: list[str] = Form([]),
    theoretical_qty: list[str] = Form([]),
    physical_qty: list[str] = Form([]),
    count_unit: list[str] = Form([]),
    line_note: list[str] = Form([]),
    is_checked: list[str] = Form([]),
    unit_cost_snapshot: list[str] = Form([]),
):
    conn = db(); cur = conn.cursor(); ensure_columns(cur); _ensure_inventory_audit_schema(cur)
    ses = cur.execute("SELECT responsible_user_id,responsible_name,center_id,warehouse_id FROM inventory_sessions WHERE id=?", (int(session_id),)).fetchone()
    if not ses or (int(ses['responsible_user_id'] or 0) <= 0 and not str(ses['responsible_name'] or '').strip()):
        conn.close()
        return _redirect(session_id, center_id, inv_mode, inv_family, 'responsible_required')
    session_center_id = int(ses['center_id'] or 0)
    session_warehouse_id = int(ses['warehouse_id'] or 0) if 'warehouse_id' in ses.keys() else 0
    actor_id = int(ses['responsible_user_id'] or 0)
    actor_name = str(ses['responsible_name'] or '').strip() or 'Sin responsable'
    now = datetime.utcnow().isoformat()
    fam = (inv_family or '').strip().lower()
    stype = (source_type or 'raw').strip().lower()
    cur.execute("UPDATE inventory_sessions SET status='COUNTING' WHERE id=? AND status='DRAFT'", (int(session_id),))
    total = max(len(item_id), len(item_name), len(warehouse_id), len(theoretical_qty), len(physical_qty), len(count_unit), len(line_note), len(unit_cost_snapshot))
    checked_set = {str(v) for v in (is_checked or [])}
    for idx in range(total):
        iid = int((item_id[idx] if idx < len(item_id) and str(item_id[idx]).strip().isdigit() else 0))
        iname = (item_name[idx] if idx < len(item_name) else '').strip()
        whid = int((warehouse_id[idx] if idx < len(warehouse_id) and str(warehouse_id[idx]).strip().isdigit() else 0))
        if whid <= 0 and session_warehouse_id > 0 and _inventory_warehouse_belongs(cur, session_warehouse_id, session_center_id):
            whid = session_warehouse_id
        tqty = _safe_float(theoretical_qty[idx] if idx < len(theoretical_qty) else '', 0.0)
        pqty_raw = (physical_qty[idx] if idx < len(physical_qty) else '').strip()
        pqty = _safe_float(pqty_raw, 0.0)
        cunit = _norm_inv_unit(count_unit[idx] if idx < len(count_unit) else '')
        note = (line_note[idx] if idx < len(line_note) else '').strip()
        cost = _safe_float(unit_cost_snapshot[idx] if idx < len(unit_cost_snapshot) else '', 0.0)
        checked = 1 if str(idx) in checked_set or pqty_raw != '' or note != '' else 0
        if whid > 0 and not _inventory_warehouse_belongs(cur, whid, session_center_id):
            continue
        existing = cur.execute(
            "SELECT * FROM inventory_counts WHERE session_id=? AND source_type=? AND item_id=? AND family_key=? AND warehouse_id=?",
            (int(session_id), stype, int(iid), fam, int(whid)),
        ).fetchone()
        # No crear líneas vacías nuevas: solo guardar las que tienen cantidad, nota o check.
        # Si ya existía, sí se actualiza para permitir borrar/corregir un conteo.
        if not existing and not int(checked or 0):
            continue
        payload = (int(session_id), stype, int(iid), iname, fam, int(whid), float(tqty), float(pqty), cunit, int(checked), note, float(cost))
        if existing:
            changed = _count_changed(existing, pqty, cunit, checked, note)
            keys = set(existing.keys())
            original_id = int(existing['original_counted_by_user_id'] or 0) if 'original_counted_by_user_id' in keys else 0
            original_name = str(existing['original_counted_by_name'] or '') if 'original_counted_by_name' in keys else ''
            original_at = str(existing['original_counted_at'] or '') if 'original_counted_at' in keys else ''
            if int(checked or 0) and not original_id and not original_name:
                original_id, original_name, original_at = actor_id, actor_name, now
            prev_qty = float(existing['physical_qty'] or 0)
            prev_unit = str(existing['count_unit'] or '')
            mod_count = int(existing['modified_count'] or 0) if 'modified_count' in keys else 0
            if changed:
                mod_count += 1
                cur.execute(
                    """UPDATE inventory_counts
                          SET item_name=?, theoretical_qty=?, physical_qty=?, count_unit=?, is_checked=?, note=?, unit_cost_snapshot=?,
                              original_counted_by_user_id=?, original_counted_by_name=?, original_counted_at=?,
                              last_modified_by_user_id=?, last_modified_by_name=?, last_modified_at=?,
                              previous_physical_qty=?, previous_count_unit=?, modified_count=?
                        WHERE id=?""",
                    (iname, float(tqty), float(pqty), cunit, int(checked), note, float(cost),
                     int(original_id or 0), original_name, original_at, actor_id, actor_name, now,
                     prev_qty, prev_unit, mod_count, int(existing['id'])),
                )
                cur.execute(
                    """INSERT INTO inventory_count_audit(session_id,inventory_count_id,item_id,item_name,source_type,family_key,warehouse_id,
                           previous_physical_qty,previous_count_unit,new_physical_qty,new_count_unit,changed_by_user_id,changed_by_name,changed_at,note)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (int(session_id), int(existing['id']), int(iid), iname, stype, fam, int(whid),
                     prev_qty, prev_unit, float(pqty), cunit, actor_id, actor_name, now, note),
                )
            else:
                cur.execute(
                    "UPDATE inventory_counts SET item_name=?, theoretical_qty=?, physical_qty=?, count_unit=?, is_checked=?, note=?, unit_cost_snapshot=?, original_counted_by_user_id=?, original_counted_by_name=?, original_counted_at=? WHERE id=?",
                    (iname, float(tqty), float(pqty), cunit, int(checked), note, float(cost), int(original_id or 0), original_name, original_at, int(existing['id'])),
                )
        else:
            orig_id = actor_id if int(checked or 0) else 0
            orig_name = actor_name if int(checked or 0) else ''
            orig_at = now if int(checked or 0) else ''
            cur.execute(
                """INSERT INTO inventory_counts(session_id,source_type,item_id,item_name,family_key,warehouse_id,theoretical_qty,physical_qty,count_unit,is_checked,note,unit_cost_snapshot,
                       original_counted_by_user_id,original_counted_by_name,original_counted_at,last_modified_by_user_id,last_modified_by_name,last_modified_at,previous_physical_qty,previous_count_unit,modified_count)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                payload + (orig_id, orig_name, orig_at, actor_id if int(checked or 0) else 0, actor_name if int(checked or 0) else '', now if int(checked or 0) else '', None, '', 0),
            )
    conn.commit(); conn.close()
    return _redirect(session_id, center_id, inv_mode, inv_family, 'block_saved', 'inventoryCountArea')


@router.post('/inventory/session/close_reconcile_form')
def inventory_session_close_reconcile_form(
    session_id: int = Form(...),
    center_id: int = Form(0),
    inv_mode: str = Form('materias_primas'),
    inv_family: str = Form('verduras'),
):
    """Cierre de inventario físico con conciliación automática.
    Para cada línea contada, compara el stock real actual en movements contra el físico introducido
    y registra un ajuste ENTRADA/SALIDA por la diferencia. No toca líneas no contadas.
    """
    conn = db(); cur = conn.cursor(); ensure_columns(cur)
    ses = cur.execute("SELECT id,status,center_id,warehouse_id,responsible_user_id,responsible_name FROM inventory_sessions WHERE id=?", (int(session_id),)).fetchone()
    if not ses:
        conn.close(); return _redirect(session_id, center_id, inv_mode, inv_family, 'session_missing')
    if (ses['status'] or '').upper() == 'CLOSED':
        conn.close(); return _redirect(session_id, center_id, inv_mode, inv_family, 'already_closed')
    if int(ses['center_id'] or 0) != int(center_id or 0):
        center_id = int(ses['center_id'] or center_id or 0)
    if int(ses['responsible_user_id'] or 0) <= 0 and not str(ses['responsible_name'] or '').strip():
        conn.close(); return _redirect(session_id, center_id, inv_mode, inv_family, 'responsible_required')
    rows = cur.execute(
        """SELECT * FROM inventory_counts
             WHERE session_id=? AND is_checked=1 AND item_id>0 AND warehouse_id>0
             ORDER BY id""",
        (int(session_id),),
    ).fetchall()
    now = datetime.utcnow().isoformat()
    adjusted = 0
    skipped = 0
    for r in rows:
        whid = int(r['warehouse_id'] or 0)
        if whid <= 0 and int(ses['warehouse_id'] or 0) > 0 and _inventory_warehouse_belongs(cur, int(ses['warehouse_id'] or 0), int(center_id or 0)):
            whid = int(ses['warehouse_id'] or 0)
        iid = int(r['item_id'] or 0)
        if not _inventory_warehouse_belongs(cur, whid, int(center_id or 0)):
            skipped += 1; continue
        it = cur.execute("SELECT unit,name FROM items WHERE id=?", (iid,)).fetchone()
        if not it:
            skipped += 1; continue
        base_unit = (it['unit'] or r['count_unit'] or 'ud').strip() or 'ud'
        count_unit_norm = _norm_inv_unit(r['count_unit'] or base_unit)
        if (r['source_type'] or '').lower() == 'production':
            factor, factor_note = _production_count_factor(cur, item_id=iid, item_name=(r['item_name'] or it['name'] or ''), count_unit=count_unit_norm, base_unit=base_unit)
        else:
            factor = float(_unit_factor(count_unit_norm, base_unit) or 0.0)
            factor_note = ''
        if factor <= 0:
            skipped += 1; continue
        physical_base = float(r['physical_qty'] or 0.0) * float(factor)
        stock_row = cur.execute(
            """SELECT COALESCE(SUM(CASE WHEN movement_type IN ('ENTRADA','IN') THEN qty
                                         WHEN movement_type IN ('SALIDA','OUT') THEN -qty ELSE -qty END),0) qty
                   FROM movements WHERE center_id=? AND warehouse_id=? AND item_id=?""",
            (int(center_id), whid, iid),
        ).fetchone()
        current_base = float(stock_row['qty'] if stock_row else 0.0)
        diff = physical_base - current_base
        if abs(diff) <= 0.000001:
            continue
        mv_type = 'ENTRADA' if diff > 0 else 'SALIDA'
        cur.execute(
            """INSERT INTO movements(center_id,warehouse_id,item_id,movement_type,qty,unit,created_at,note)
               VALUES(?,?,?,?,?,?,?,?)""",
            (int(center_id), whid, iid, mv_type, abs(diff), base_unit, now, f'AJUSTE INVENTARIO #{int(session_id)} · físico {physical_base:g} {base_unit}' + (f' · {factor_note}' if factor_note else '')),
        )
        adjusted += 1
    cur.execute("UPDATE inventory_sessions SET status='CLOSED', note=COALESCE(note,'') || ? WHERE id=?", (f"\nCierre conciliado {now}: {adjusted} ajustes, {skipped} omitidos.", int(session_id)))
    conn.commit(); conn.close()
    return _redirect(session_id, center_id, inv_mode, inv_family, f'inventory_closed_{adjusted}', 'inventoryWorkArea')


@router.post('/inventory/free/add_form')
def inventory_free_add_form(
    session_id: int = Form(...),
    center_id: int = Form(0),
    inv_mode: str = Form('libres'),
    inv_family: str = Form('libres'),
    warehouse_id: int = Form(0),
    free_name: str = Form(...),
    free_block: str = Form('materias_primas'),
    free_family: str = Form('otros'),
    free_qty: str = Form('0'),
    free_unit: str = Form('ud'),
    free_note: str = Form(''),
    free_cost: str = Form('0'),
):
    name = (free_name or '').strip()
    if not name:
        return _redirect(session_id, center_id, inv_mode, inv_family, 'free_empty')
    block = (free_block or 'materias_primas').strip().lower()
    family = (free_family or '').strip().lower()
    if block not in {'materias_primas','producciones','limpieza'}:
        block = 'materias_primas'
    if block == 'limpieza':
        family = 'limpieza'
    elif not family:
        family = 'otros'
    family_key = f"{block}:{family}"
    conn = db(); cur = conn.cursor(); ensure_columns(cur); _ensure_inventory_audit_schema(cur)
    ses = cur.execute("SELECT responsible_user_id,responsible_name FROM inventory_sessions WHERE id=?", (int(session_id),)).fetchone()
    actor_id = int((ses['responsible_user_id'] if ses else 0) or 0)
    actor_name = str((ses['responsible_name'] if ses else '') or '').strip() or 'Sin responsable'
    now = datetime.utcnow().isoformat()
    if int(warehouse_id or 0) > 0 and not _inventory_warehouse_belongs(cur, int(warehouse_id), int(center_id or 0)):
        conn.close()
        return _redirect(session_id, center_id, inv_mode, inv_family, 'warehouse_invalid')
    cur.execute(
        """INSERT INTO inventory_counts(session_id,source_type,item_id,item_name,family_key,warehouse_id,theoretical_qty,physical_qty,count_unit,is_checked,note,unit_cost_snapshot,
               original_counted_by_user_id,original_counted_by_name,original_counted_at,last_modified_by_user_id,last_modified_by_name,last_modified_at,modified_count)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            int(session_id), 'free', 0, name.upper()[:160], family_key, int(warehouse_id or 0), 0.0,
            float(str(free_qty or '0').replace(',', '.')), (free_unit or 'ud').strip()[:20], 1,
            (free_note or '').strip(), float(str(free_cost or '0').replace(',', '.')),
            actor_id, actor_name, now, actor_id, actor_name, now, 0,
        ),
    )
    cur.execute("UPDATE inventory_sessions SET status='COUNTING' WHERE id=? AND status='DRAFT'", (int(session_id),))
    conn.commit(); conn.close()
    return _redirect(session_id, center_id, inv_mode, inv_family, 'free_added', 'inventoryCountArea')
