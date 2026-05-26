from app.core import db, normalize_minmax_qty_for_base
from datetime import datetime
from typing import Optional

from app.services.units_service import to_base_qty, minmax_to_base


def create_stock_movement(cur, center_id: int, warehouse_id: int, item_id: int, movement_type: str, qty_value: float, qty_unit: str, note: str = ''):
    if float(qty_value or 0) <= 0:
        return {'ok': False, 'error': 'Cantidad debe ser > 0', '_status': 400}

    wh = cur.execute('SELECT center_id FROM warehouses WHERE id=?', (warehouse_id,)).fetchone()
    if not wh:
        return {'ok': False, 'error': 'Almacén inválido', '_status': 400}
    if int(wh['center_id'] or 0) != int(center_id or 0):
        return {'ok': False, 'error': 'El almacén no pertenece al local seleccionado', '_status': 400}
    item = cur.execute('SELECT id,name,unit FROM items WHERE id=?', (item_id,)).fetchone()
    if not item:
        return {'ok': False, 'error': 'Artículo inválido', '_status': 400}

    base_unit = item['unit']
    qty_base = to_base_qty(float(qty_value or 0.0), qty_unit, base_unit)
    if float(qty_base or 0) <= 0:
        return {'ok': False, 'error': 'Unidad incompatible con el artículo', '_status': 400}
    mt = (movement_type or '').upper().strip()
    if mt not in {'ENTRADA', 'SALIDA', 'IN', 'OUT'}:
        return {'ok': False, 'error': 'Tipo de movimiento inválido', '_status': 400}

    created_at = datetime.now().isoformat(timespec='seconds')
    cur.execute(
        """INSERT INTO movements(center_id,warehouse_id,item_id,movement_type,qty,unit,created_at,note)
           VALUES(?,?,?,?,?,?,?,?)""",
        (center_id, warehouse_id, item_id, mt, qty_base, base_unit, created_at, note)
    )
    movement_id = int(cur.lastrowid or 0)
    signed = "CASE WHEN upper(movement_type) IN ('ENTRADA','IN') THEN qty WHEN upper(movement_type) IN ('SALIDA','OUT') THEN -qty ELSE 0 END"
    stock_after = cur.execute(
        f"SELECT COALESCE(SUM({signed}),0) stock_qty FROM movements WHERE center_id=? AND warehouse_id=? AND item_id=?",
        (int(center_id or 0), int(warehouse_id or 0), int(item_id or 0)),
    ).fetchone()
    return {
        'ok': True,
        'message': 'Movimiento guardado',
        'movement_id': movement_id,
        'item_id': int(item_id or 0),
        'item_name': item['name'] if 'name' in item.keys() else '',
        'center_id': int(center_id or 0),
        'warehouse_id': int(warehouse_id or 0),
        'movement_type': mt,
        'qty_base': float(qty_base or 0),
        'base_unit': base_unit,
        'stock_after': float(stock_after['stock_qty'] or 0) if stock_after else 0.0,
        'created_at': created_at,
    }


def save_item_minmax(item_id: int, min_qty: float, max_qty: float, min_unit: str, max_unit: str, center_id: Optional[str] = '', warehouse_id: Optional[str] = ''):
    conn = db()
    cur = conn.cursor()
    item = cur.execute('SELECT id,name,unit FROM items WHERE id=?', (item_id,)).fetchone()
    if not item:
        conn.close()
        raise LookupError('Artículo inválido')
    base_unit = item['unit']
    min_base = minmax_to_base(float(min_qty or 0.0), min_unit, base_unit)
    max_base = minmax_to_base(float(max_qty or 0.0), max_unit, base_unit)
    # Blindaje: si llegan valores heredados absurdos en kg (ej. 20000 kg por antiguo dato en g),
    # se corrigen antes de guardar para no contaminar pedidos máximos.
    min_base = normalize_minmax_qty_for_base(min_base, base_unit)
    max_base = normalize_minmax_qty_for_base(max_base, base_unit)
    if min_base < 0 or max_base < 0 or max_base < min_base:
        conn.close()
        raise ValueError('Rango inválido')

    if str(center_id).isdigit() and str(warehouse_id).isdigit():
        wh = cur.execute('SELECT center_id FROM warehouses WHERE id=?', (int(warehouse_id),)).fetchone()
        if not wh or int(wh['center_id'] or 0) != int(center_id or 0):
            conn.close()
            raise ValueError('Almacén incoherente para el local')
        cur.execute(
            """INSERT INTO item_location_prefs(center_id,warehouse_id,item_id,min_qty,max_qty)
               VALUES(?,?,?,?,?)
               ON CONFLICT(center_id,warehouse_id,item_id)
               DO UPDATE SET min_qty=excluded.min_qty,max_qty=excluded.max_qty""",
            (int(center_id), int(warehouse_id), item_id, min_base, max_base)
        )
    else:
        cur.execute('UPDATE items SET min_qty=?, max_qty=? WHERE id=?', (min_base, max_base, item_id))
    conn.commit()
    conn.close()
    return {'ok': True, 'min_base': min_base, 'max_base': max_base}
