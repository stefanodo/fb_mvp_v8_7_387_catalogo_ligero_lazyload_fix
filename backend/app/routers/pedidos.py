from __future__ import annotations

# ==============================================================================
# BLOQUE PEDIDOS · Pedidos, líneas, sugerencias, impresión
# ==============================================================================
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import Optional
from datetime import datetime
import sqlite3

from app.core import (
    db, _parse_float, ensure_columns, _resolve_item_id, _unit_factor,
    _suggest_supplier_id, order_with_lines, human_qty, fmt_dt, status_label,
    normalize_stock_area, normalize_minmax_qty_for_base,
)
from app.core import safe_insert_returning
from app.core import db_truthy_sql
from app.services.orders_service import order_page_url, normalize_order_note, parse_optional_int, infer_order_block

router = APIRouter()


def _order_norm_text(value: str) -> str:
    return (value or '').strip().lower().replace('á','a').replace('é','e').replace('í','i').replace('ó','o').replace('ú','u')


def _order_preferred_warehouse_id(cur, center_id: int, block_key: str) -> int | None:
    preferred_map = {
        'fresh': ['camara'],
        'frozen': ['congel', 'camara'],
        'dry': ['economato'],
        'clean': ['economato'],
    }
    preferreds = preferred_map.get((block_key or '').strip().lower(), [])
    rows = cur.execute("SELECT id,name FROM warehouses WHERE center_id=? ORDER BY id", (int(center_id),)).fetchall()
    picked = None
    for row in rows:
        wid = int(row['id'] or 0)
        name_norm = _order_norm_text(row['name'] or '')
        if preferreds and any(pref in name_norm for pref in preferreds):
            return wid
        if picked is None:
            picked = wid
    return picked


def _warehouse_belongs_to_center(cur, warehouse_id: int, center_id: int) -> bool:
    try:
        row = cur.execute("SELECT 1 FROM warehouses WHERE id=? AND center_id=?", (int(warehouse_id), int(center_id))).fetchone()
        return bool(row)
    except Exception:
        return False


def _order_item_block_key(item_name: str, stock_area: str) -> str:
    area = normalize_stock_area(stock_area or '')
    if area == 'FRESCOS':
        return 'fresh'
    if area == 'CONGELADOS':
        return 'frozen'
    if area == 'SECOS':
        return 'dry'
    if area == 'LIMPIEZA':
        return 'clean'
    n = _order_norm_text(item_name)
    clean_words = ['deterg','lejia','desengras','lavavaj','friegas','papel','guante','limpi','higien','jabon']
    fresh_words = ['tomate','lechuga','cebolla','ajo','pimiento','cilantro','espinaca','pollo','ternera','cerdo','salmon','atun','atún','bacalao','merluza','dorada','lubina','gamba','langost','pulpo','calamar','almeja','ostra','navaja','berberecho','chirla','vieira','huevo','huevos','queso','leche','nata','mantequilla','yogur','mozzarella','sandia','melon','melón','lima','limon','limón','pepino','aguacate']
    dry_words = ['harina','arroz','pasta','azucar','azúcar','sal ','sal fina','sal maldon','aceite','vinagre','conserva','tomate seco','panko','pan rallado','legumbre','garbanzo','lenteja','fruto seco','almendra','pistacho','oregano','orégano','pimienta','especia','salsa soja']
    frozen_words = ['congelad', 'ultracongel', 'frozen']
    if any(k in n for k in clean_words):
        return 'clean'
    if any(k in n for k in frozen_words):
        return 'frozen'
    if any(k in n for k in fresh_words):
        return 'fresh'
    if any(k in n for k in dry_words):
        return 'dry'
    return 'free'


def _order_redirect(order_id: int, center_id: int, **params):
    return RedirectResponse(url=order_page_url(center_id=center_id, oid=order_id, **params), status_code=303)


def _order_has_responsible(cur, order_id: int) -> bool:
    row = cur.execute("SELECT COALESCE(responsible_user_id,0) responsible_user_id, COALESCE(responsible_name,'') responsible_name FROM orders WHERE id=?", (order_id,)).fetchone()
    if not row:
        return False
    return int(row["responsible_user_id"] or 0) > 0 and bool(str(row["responsible_name"] or "").strip())


def _order_stock_qty(cur, center_id: int, warehouse_id: int, item_id: int) -> float:
    row = cur.execute(
        """
        SELECT COALESCE(SUM(CASE WHEN movement_type IN ('ENTRADA','IN') THEN qty
                                 WHEN movement_type IN ('SALIDA','OUT') THEN -qty ELSE -qty END),0) stock_qty
          FROM movements
         WHERE center_id=? AND warehouse_id=? AND item_id=?
        """,
        (int(center_id), int(warehouse_id), int(item_id)),
    ).fetchone()
    return float((row["stock_qty"] if row else 0.0) or 0.0)


def _order_item_minmax(cur, center_id: int, warehouse_id: int, item_id: int):
    row = cur.execute(
        """
        SELECT i.id item_id, i.name item_name, i.unit base_unit, COALESCE(i.stock_area,'') stock_area,
               COALESCE(lp.min_qty, i.min_qty) min_qty,
               COALESCE(lp.max_qty, i.max_qty) max_qty,
               CASE WHEN lp.item_id IS NOT NULL THEN 1 ELSE 0 END has_location_pref
          FROM items i
          LEFT JOIN item_location_prefs lp ON lp.center_id=? AND lp.warehouse_id=? AND lp.item_id=i.id
         WHERE i.id=?
        """,
        (int(center_id), int(warehouse_id), int(item_id)),
    ).fetchone()
    if not row:
        return None
    d = {k: row[k] for k in row.keys()}
    d["min_qty"] = normalize_minmax_qty_for_base(d.get("min_qty"), d.get("base_unit"))
    d["max_qty"] = normalize_minmax_qty_for_base(d.get("max_qty"), d.get("base_unit"))
    return d


def _order_primary_warehouse_for_item(cur, center_id: int, item_id: int) -> int | None:
    # Primero respetar una preferencia min/max específica del artículo.
    pref = cur.execute(
        """
        SELECT warehouse_id
          FROM item_location_prefs
         WHERE center_id=? AND item_id=?
         ORDER BY CASE WHEN COALESCE(max_qty,0)>0 OR COALESCE(min_qty,0)>0 THEN 0 ELSE 1 END, id
         LIMIT 1
        """,
        (int(center_id), int(item_id)),
    ).fetchone()
    if pref:
        return int(pref["warehouse_id"] or 0) or None
    item = cur.execute("SELECT name, COALESCE(stock_area,'') stock_area FROM items WHERE id=?", (int(item_id),)).fetchone()
    if not item:
        return None
    block = _order_item_block_key(item["name"] or '', item["stock_area"] or '')
    return _order_preferred_warehouse_id(cur, center_id, block)


def _order_upsert_line_to_qty(cur, order_id: int, center_id: int, warehouse_id: int, item_id: int, qty_base: float, base_unit: str, supplier_id=None) -> bool:
    """Inserta o eleva la cantidad de una línea. Devuelve True si cambia el carrito."""
    qty_base = float(qty_base or 0.0)
    if qty_base <= 0:
        return False
    supplier_id = supplier_id if supplier_id is not None else _suggest_supplier_id(cur, int(center_id), int(item_id))
    existing = cur.execute(
        "SELECT id, qty_base, supplier_id FROM order_lines WHERE order_id=? AND warehouse_id=? AND item_id=? ORDER BY id LIMIT 1",
        (int(order_id), int(warehouse_id), int(item_id)),
    ).fetchone()
    if existing:
        old_qty = float(existing["qty_base"] or 0.0)
        new_qty = max(old_qty, qty_base)
        if abs(new_qty - old_qty) <= 0.000001 and (existing["supplier_id"] or supplier_id):
            return False
        cur.execute(
            "UPDATE order_lines SET qty_base=?, input_unit=?, qty_input=?, supplier_id=COALESCE(supplier_id, ?), is_checked=0 WHERE id=? AND order_id=?",
            (new_qty, base_unit, new_qty, supplier_id, int(existing["id"]), int(order_id)),
        )
        return True
    cur.execute(
        "INSERT INTO order_lines(order_id,warehouse_id,item_id,qty_base,input_unit,qty_input,supplier_id,is_checked) VALUES(?,?,?,?,?,?,?,?)",
        (int(order_id), int(warehouse_id), int(item_id), qty_base, base_unit, qty_base, supplier_id, 0),
    )
    return True




def _order_suggested_supplier(cur, center_id: int, item_id: int) -> int | None:
    try:
        sid = _suggest_supplier_id(cur, int(center_id), int(item_id)) or 0
        return int(sid) if sid else None
    except Exception:
        return None


def _order_supplier_filter_allows(cur, center_id: int, item_id: int, supplier_filter_id: int | None) -> bool:
    """Filtro de proveedor para pedidos.

    Regla operativa v8_7_289:
    - Si no se eligió proveedor, se muestran todos los artículos del bloque.
    - Si se eligió proveedor y el artículo ya tiene proveedores asociados, se muestra solo si uno
      coincide con el proveedor elegido.
    - Si el artículo NO tiene ningún proveedor asociado, se permite mostrarlo/añadirlo para que
      quede asignado al proveedor objetivo. Esto evita la pantalla vacía con proveedores nuevos
      o catálogos todavía sin vincular.
    """
    if not supplier_filter_id:
        return True
    try:
        rows = cur.execute(
            """SELECT DISTINCT supplier_id
                 FROM supplier_item_prices
                WHERE item_id=? AND (center_id IS NULL OR center_id=?)""",
            (int(item_id), int(center_id)),
        ).fetchall()
        supplier_ids = {int(r["supplier_id"]) for r in rows if r["supplier_id"]}
        if not supplier_ids:
            return True
        return int(supplier_filter_id) in supplier_ids
    except Exception:
        return True

def _order_replenish_qty_for_position(cur, center_id: int, warehouse_id: int, item_id: int, *, extra_planned_out: float = 0.0, require_under_min: bool = True) -> tuple[float, dict]:
    meta = _order_item_minmax(cur, center_id, warehouse_id, item_id) or {}
    stock_qty = _order_stock_qty(cur, center_id, warehouse_id, item_id)
    projected_stock = stock_qty - float(extra_planned_out or 0.0)
    min_qty = float(meta.get("min_qty") or 0.0)
    max_qty = float(meta.get("max_qty") or 0.0)
    if max_qty <= 0:
        return 0.0, {**meta, "stock_qty": stock_qty, "projected_stock": projected_stock}
    if require_under_min and min_qty > 0 and projected_stock >= min_qty:
        return 0.0, {**meta, "stock_qty": stock_qty, "projected_stock": projected_stock}
    qty = max(0.0, max_qty - projected_stock)
    return qty, {**meta, "stock_qty": stock_qty, "projected_stock": projected_stock}


def _order_candidate_minmax_rows(cur, center_id: int, *, block_key: str | None = None, warehouse_id: int | None = None):
    """Devuelve posiciones reales de min/max. Si no hay pref de ubicación, usa almacén preferido por bloque.
    Evita el bug anterior de revisar solo el primer almacén del centro.
    """
    rows = []
    # Preferencias explícitas por centro/almacén/artículo.
    for r in cur.execute(
        """
        SELECT lp.warehouse_id, i.id item_id, i.name item_name, i.unit base_unit, COALESCE(i.stock_area,'') stock_area,
               COALESCE(lp.min_qty, i.min_qty) min_qty, COALESCE(lp.max_qty, i.max_qty) max_qty
          FROM item_location_prefs lp
          JOIN items i ON i.id=lp.item_id
         WHERE lp.center_id=? AND (COALESCE(lp.min_qty,0)>0 OR COALESCE(lp.max_qty,0)>0)
        """,
        (int(center_id),),
    ).fetchall():
        wid = int(r["warehouse_id"] or 0)
        if warehouse_id and wid != int(warehouse_id):
            continue
        bk = _order_item_block_key(r["item_name"] or '', r["stock_area"] or '')
        if block_key and bk != block_key:
            continue
        d = {k: r[k] for k in r.keys()}
        d['min_qty'] = normalize_minmax_qty_for_base(d.get('min_qty'), d.get('base_unit'))
        d['max_qty'] = normalize_minmax_qty_for_base(d.get('max_qty'), d.get('base_unit'))
        rows.append(d)
    seen = {(int(r['warehouse_id']), int(r['item_id'])) for r in rows}
    # Min/max global sin preferencia: usar almacén operativo preferente por bloque.
    for r in cur.execute(
        """
        SELECT i.id item_id, i.name item_name, i.unit base_unit, COALESCE(i.stock_area,'') stock_area,
               COALESCE(i.min_qty,0) min_qty, COALESCE(i.max_qty,0) max_qty
          FROM items i
         WHERE COALESCE(i.max_qty,0)>0 OR COALESCE(i.min_qty,0)>0
        """
    ).fetchall():
        bk = _order_item_block_key(r["item_name"] or '', r["stock_area"] or '')
        if block_key and bk != block_key:
            continue
        wid = _order_preferred_warehouse_id(cur, int(center_id), bk) or _order_preferred_warehouse_id(cur, int(center_id), 'fresh')
        if not wid:
            continue
        if warehouse_id and int(wid) != int(warehouse_id):
            continue
        key = (int(wid), int(r['item_id']))
        if key in seen:
            continue
        d = {k: r[k] for k in r.keys()}
        d['min_qty'] = normalize_minmax_qty_for_base(d.get('min_qty'), d.get('base_unit'))
        d['max_qty'] = normalize_minmax_qty_for_base(d.get('max_qty'), d.get('base_unit'))
        d['warehouse_id'] = int(wid)
        rows.append(d)
    return rows


def _order_responsible_row(cur, user_id: int):
    rid = int(user_id or 0)
    if rid <= 0:
        return None
    active_clause = db_truthy_sql('is_active', cur)
    rows = cur.execute(f"SELECT id,name FROM users WHERE {active_clause} ORDER BY id").fetchall()
    if not rows:
        return None
    non_admin = [r for r in rows if (str(r['name'] or '').strip().upper() != 'ADMIN GENERAL')]
    eligible = non_admin if non_admin else rows
    for row in eligible:
        if int(row['id'] or 0) == rid:
            return row
    return None


@router.post("/order/new_form")
def order_new_form(center_id: int = Form(...), responsible_user_id: int = Form(0), note: str = Form("")):
    conn = db(); cur = conn.cursor(); ensure_columns(cur)
    rid = int(responsible_user_id or 0)
    if rid <= 0:
        conn.close()
        return RedirectResponse(url=order_page_url(center_id=center_id, ord_msg='responsible_required', anchor=''), status_code=303)
    resp = _order_responsible_row(cur, rid)
    if not resp:
        conn.close()
        return RedirectResponse(url=order_page_url(center_id=center_id, ord_msg='responsible_required', anchor=''), status_code=303)
    now = datetime.utcnow().isoformat()
    # Insert order in DB-agnostic way and obtain id
    sqlite_sql = "INSERT INTO orders(center_id,status,created_at,note,responsible_user_id,responsible_name) VALUES(?,'DRAFT',?,?,?,?)"
    params = (center_id, now, normalize_order_note(note), int(resp['id']), (resp['name'] or '').strip())
    pg_sql = sqlite_sql.replace('?', '%s')
    oid = safe_insert_returning(cur, sqlite_sql, params, pg_sql=pg_sql) or 0
    conn.commit(); conn.close()
    return RedirectResponse(url=order_page_url(center_id=center_id, oid=oid),
                            status_code=303)


@router.post("/order/{order_id}/responsible_form")
def order_responsible_form(order_id: int, responsible_user_id: int = Form(0)):
    conn = db(); cur = conn.cursor(); ensure_columns(cur)
    o = cur.execute("SELECT center_id,status FROM orders WHERE id=?", (order_id,)).fetchone()
    if not o or o["status"] != "DRAFT":
        conn.close()
        return RedirectResponse(url=order_page_url(oid=order_id, err=1), status_code=303)
    rid = int(responsible_user_id or 0)
    if rid <= 0:
        conn.close()
        return RedirectResponse(url=order_page_url(center_id=int(o['center_id']), oid=order_id, ord_msg='responsible_required'), status_code=303)
    resp = _order_responsible_row(cur, rid)
    if not resp:
        conn.close()
        return RedirectResponse(url=order_page_url(center_id=int(o['center_id']), oid=order_id, ord_msg='responsible_required'), status_code=303)
    cur.execute("UPDATE orders SET responsible_user_id=?, responsible_name=? WHERE id=?", (int(resp['id']), (resp['name'] or '').strip(), order_id))
    conn.commit(); conn.close()
    return RedirectResponse(url=order_page_url(center_id=int(o['center_id']), oid=order_id, ok=1), status_code=303)


@router.post("/order/{order_id}/add_suggestions_form")
def order_add_suggestions_form(order_id: int, warehouse_id: str = Form(""), supplier_id: str = Form("")):
    conn = db(); cur = conn.cursor(); ensure_columns(cur)
    o = cur.execute("SELECT center_id,status FROM orders WHERE id=?", (order_id,)).fetchone()
    if not o or o["status"] != "DRAFT":
        conn.close()
        return RedirectResponse(url=order_page_url(oid=order_id, err=1), status_code=303)
    if not _order_has_responsible(cur, order_id):
        conn.close()
        return RedirectResponse(url=order_page_url(center_id=int(o['center_id']), oid=order_id, ord_msg='responsible_required'), status_code=303)
    center_id = int(o["center_id"])
    sid_filter = parse_optional_int(supplier_id)
    wh_id = None
    try:
        if str(warehouse_id).strip().isdigit():
            wh_id = int(str(warehouse_id).strip())
    except Exception:
        pass
    if wh_id is None:
        roww = cur.execute("SELECT id FROM warehouses WHERE center_id=? ORDER BY id LIMIT 1",
                           (center_id,)).fetchone()
        if roww:
            wh_id = int(roww["id"])
    if wh_id is None or not _warehouse_belongs_to_center(cur, int(wh_id), center_id):
        conn.close()
        return _order_redirect(order_id, center_id, err=1)

    # Sin warehouse_id explícito: revisar todas las posiciones min/max del centro.
    # Antes se usaba solo el primer almacén, lo que dejaba fuera artículos de Cámara/Economato.
    candidate_rows = _order_candidate_minmax_rows(cur, center_id, warehouse_id=wh_id if str(warehouse_id).strip().isdigit() else None)
    added = 0
    for r in candidate_rows:
        warehouse_id_int = int(r["warehouse_id"] or 0)
        item_id_int = int(r["item_id"] or 0)
        if warehouse_id_int <= 0 or item_id_int <= 0:
            continue
        if not _order_supplier_filter_allows(cur, center_id, item_id_int, sid_filter):
            continue
        qty_to_order, meta = _order_replenish_qty_for_position(
            cur, center_id, warehouse_id_int, item_id_int, require_under_min=True
        )
        if qty_to_order <= 0:
            continue
        base_unit = ((r["base_unit"] if "base_unit" in r else meta.get("base_unit")) or "ud").strip() or "ud"
        if _order_upsert_line_to_qty(cur, order_id, center_id, warehouse_id_int, item_id_int, qty_to_order, base_unit):
            added += 1

    conn.commit(); conn.close()
    return RedirectResponse(
        url=order_page_url(center_id=center_id, oid=order_id, ok=1, added=added, anchor='orderAutoTools'),
        status_code=303)




@router.post("/order/{order_id}/add_production_needs_form")
def order_add_production_needs_form(order_id: int, supplier_id: str = Form("")):
    conn = db(); cur = conn.cursor(); ensure_columns(cur)
    o = cur.execute("SELECT center_id,status FROM orders WHERE id=?", (order_id,)).fetchone()
    if not o or o["status"] != "DRAFT":
        conn.close()
        return RedirectResponse(url=order_page_url(oid=order_id, err=1), status_code=303)
    center_id = int(o["center_id"])
    sid_filter = parse_optional_int(supplier_id)
    if not _order_has_responsible(cur, order_id):
        conn.close()
        return RedirectResponse(url=order_page_url(center_id=center_id, oid=order_id, ord_msg='responsible_required'), status_code=303)

    # 1) Producciones abiertas: calcular necesidad proyectada y reponer hasta máximo si aplica.
    required_rows = cur.execute(
        """
        SELECT p.warehouse_id, pl.item_id, SUM(pl.qty_base) required_qty
          FROM productions p
          JOIN production_lines pl ON pl.production_id=p.id
         WHERE p.center_id=? AND UPPER(COALESCE(p.status,''))='DRAFT' AND UPPER(COALESCE(pl.line_type,''))='OUT'
         GROUP BY p.warehouse_id, pl.item_id
        """,
        (center_id,),
    ).fetchall()
    required_map = {(int(r['warehouse_id']), int(r['item_id'])): float(r['required_qty'] or 0.0) for r in required_rows}

    added = 0
    for key, required_qty in required_map.items():
        warehouse_id, item_id = key
        qty_to_order, meta = _order_replenish_qty_for_position(
            cur, center_id, warehouse_id, item_id, extra_planned_out=float(required_qty or 0.0), require_under_min=False
        )
        # Si no hay min/max configurado, al menos cubrir faltante real de producción abierta.
        if qty_to_order <= 0:
            stock_qty = _order_stock_qty(cur, center_id, warehouse_id, item_id)
            qty_to_order = max(0.0, float(required_qty or 0.0) - stock_qty)
        if qty_to_order <= 0:
            continue
        if not _order_supplier_filter_allows(cur, center_id, item_id, sid_filter):
            continue
        item = cur.execute("SELECT unit FROM items WHERE id=?", (item_id,)).fetchone()
        base_unit = ((item['unit'] if item else 'ud') or 'ud').strip() or 'ud'
        if _order_upsert_line_to_qty(cur, order_id, center_id, warehouse_id, item_id, qty_to_order, base_unit, supplier_id=sid_filter):
            added += 1

    # 2) Producciones ya confirmadas: el consumo ya impactó stock. Si dejaron artículos bajo mínimo,
    # pedir hasta máximo. Esto corrige el caso CACCIO PEPPE: Provolone/Parmesano tras confirmar producción.
    recent_rows = cur.execute(
        """
        SELECT DISTINCT p.warehouse_id, pl.item_id
          FROM productions p
          JOIN production_lines pl ON pl.production_id=p.id
         WHERE p.center_id=?
           AND UPPER(COALESCE(p.status,'')) IN ('CONFIRMED','CONFIRMADA')
           AND UPPER(COALESCE(pl.line_type,''))='OUT'
        """,
        (center_id,),
    ).fetchall()
    for rr in recent_rows:
        warehouse_id = int(rr['warehouse_id'] or 0)
        item_id = int(rr['item_id'] or 0)
        if warehouse_id <= 0 or item_id <= 0:
            continue
        if not _order_supplier_filter_allows(cur, center_id, item_id, sid_filter):
            continue
        qty_to_order, meta = _order_replenish_qty_for_position(
            cur, center_id, warehouse_id, item_id, require_under_min=True
        )
        if qty_to_order <= 0:
            continue
        base_unit = (meta.get('base_unit') or 'ud').strip() or 'ud'
        if _order_upsert_line_to_qty(cur, order_id, center_id, warehouse_id, item_id, qty_to_order, base_unit, supplier_id=sid_filter):
            added += 1

    conn.commit(); conn.close()
    return RedirectResponse(
        url=order_page_url(center_id=center_id, oid=order_id, ok=1, added=added, anchor='orderAutoTools'),
        status_code=303)


@router.post("/order/{order_id}/add_block_to_max_form")
def order_add_block_to_max_form(order_id: int, block_key: str = Form('fresh'), supplier_id: str = Form("")):
    conn = db(); cur = conn.cursor(); ensure_columns(cur)
    o = cur.execute("SELECT center_id,status FROM orders WHERE id=?", (order_id,)).fetchone()
    if not o or o['status'] != 'DRAFT':
        conn.close()
        return RedirectResponse(url=order_page_url(oid=order_id, err=1), status_code=303)
    center_id = int(o['center_id'])
    sid_filter = parse_optional_int(supplier_id)
    if not _order_has_responsible(cur, order_id):
        conn.close()
        return _order_redirect(order_id, center_id, ord_msg='responsible_required')
    block_key = _order_norm_text(block_key or 'fresh')
    block_alias = {'frescos':'fresh','fresh':'fresh','secos':'dry','dry':'dry','limpieza':'clean','clean':'clean','cleaning':'clean','congelados':'frozen','frozen':'frozen','libres':'free','free':'free'}
    block_key = block_alias.get(block_key, 'fresh')
    if block_key not in {'fresh','dry','clean','frozen'}:
        block_key = 'fresh'

    # Max F/C/S/L: revisar todos los artículos del bloque con min/max, no solo un almacén fijo.
    # Si hay preferencia por artículo en Cámara/Economato, se respeta. Si no, se usa almacén preferente del bloque.
    candidate_rows = _order_candidate_minmax_rows(cur, center_id, block_key=block_key)

    # Producciones abiertas también deben considerarse para no pedir de menos antes de producir.
    planned_out = {}
    for rr in cur.execute("""
        SELECT p.warehouse_id, pl.item_id, SUM(pl.qty_base) qty
          FROM productions p JOIN production_lines pl ON pl.production_id=p.id
         WHERE p.center_id=? AND UPPER(COALESCE(p.status,''))='DRAFT' AND UPPER(COALESCE(pl.line_type,''))='OUT'
         GROUP BY p.warehouse_id, pl.item_id
    """, (center_id,)).fetchall():
        planned_out[(int(rr['warehouse_id']), int(rr['item_id']))] = float(rr['qty'] or 0.0)

    changed = 0
    for r in candidate_rows:
        warehouse_id = int(r['warehouse_id'] or 0)
        item_id = int(r['item_id'] or 0)
        if not _order_supplier_filter_allows(cur, center_id, item_id, sid_filter):
            continue
        extra = float(planned_out.get((warehouse_id, item_id), 0.0))
        qty_to_order, meta = _order_replenish_qty_for_position(
            cur, center_id, warehouse_id, item_id, extra_planned_out=extra, require_under_min=False
        )
        if qty_to_order <= 0:
            continue
        base_unit = ((r['base_unit'] if 'base_unit' in r else meta.get('base_unit')) or 'ud').strip() or 'ud'
        if _order_upsert_line_to_qty(cur, order_id, center_id, warehouse_id, item_id, qty_to_order, base_unit, supplier_id=sid_filter):
            changed += 1

    conn.commit(); conn.close()
    return _order_redirect(order_id, center_id, ok=1, added=changed, anchor='orderAutoTools')


@router.post("/order/{order_id}/toggle_line_check/{line_id}")
def order_toggle_line_check(order_id: int, line_id: int, is_checked: str = Form('0')):
    conn = db(); cur = conn.cursor(); ensure_columns(cur)
    o = cur.execute("SELECT center_id,status FROM orders WHERE id=?", (order_id,)).fetchone()
    if not o or o['status'] != 'DRAFT':
        conn.close()
        return RedirectResponse(url=order_page_url(oid=order_id, err=1), status_code=303)
    cur.execute("UPDATE order_lines SET is_checked=? WHERE id=? AND order_id=?", (1 if str(is_checked).strip() in {'1','true','on','yes'} else 0, line_id, order_id))
    conn.commit(); conn.close()
    return _order_redirect(order_id, int(o['center_id']), ok=1)


@router.post("/order/{order_id}/add_block_lines_form")
async def order_add_block_lines_form(
    request: Request,
    order_id: int,
    block_key: str = Form('fresh'),
    supplier_id: str = Form(''),
):
    conn = db(); cur = conn.cursor(); ensure_columns(cur)
    o = cur.execute("SELECT center_id,status FROM orders WHERE id=?", (order_id,)).fetchone()
    if not o or o["status"] != "DRAFT":
        conn.close()
        return RedirectResponse(url=order_page_url(oid=order_id, err=1), status_code=303)
    center_id = int(o["center_id"])
    if not _order_has_responsible(cur, order_id):
        conn.close()
        return RedirectResponse(url=order_page_url(center_id=center_id, oid=order_id, ord_msg='responsible_required'), status_code=303)
    block_key = _order_norm_text(block_key or 'fresh')
    block_alias = {'frescos':'fresh','fresh':'fresh','secos':'dry','dry':'dry','limpieza':'clean','clean':'clean','cleaning':'clean','congelados':'frozen','frozen':'frozen','libres':'free','free':'free','producciones':'prod','produccion':'prod','prod':'prod'}
    block_key = block_alias.get(block_key, 'fresh')
    if block_key not in {'fresh','dry','clean','free','frozen','prod'}:
        block_key = 'fresh'
    default_wh_id = None
    if block_key == 'free':
        default_wh_id = _order_preferred_warehouse_id(cur, center_id, 'fresh') or _order_preferred_warehouse_id(cur, center_id, 'dry')
    elif block_key != 'prod':
        default_wh_id = _order_preferred_warehouse_id(cur, center_id, block_key)
    if block_key != 'prod' and (default_wh_id is None or not _warehouse_belongs_to_center(cur, int(default_wh_id), center_id)):
        conn.close()
        return RedirectResponse(url=order_page_url(center_id=center_id, oid=order_id, err=1), status_code=303)
    sid = parse_optional_int(supplier_id)
    form = await request.form()
    added = 0
    for key, raw in form.items():
        if not str(key).startswith('qty_'):
            continue
        suffix = str(key)[4:]
        item_id = None
        wh_id = default_wh_id
        if block_key == 'prod':
            if '__' in suffix:
                item_part, wh_part = suffix.split('__', 1)
            else:
                item_part = suffix
                wh_part = str(form.get(f'wh_{suffix}', '') or '').strip()
            if not str(item_part).isdigit():
                continue
            item_id = int(item_part)
            try:
                wh_id = int(wh_part or 0)
            except Exception:
                wh_id = 0
            if wh_id <= 0 or not _warehouse_belongs_to_center(cur, int(wh_id), center_id):
                continue
        else:
            item_part = suffix
            if not item_part.isdigit():
                continue
            item_id = int(item_part)
        qty_input = _parse_float(raw, 0.0)
        if qty_input <= 0:
            continue
        unit_key = f'unit_{suffix}' if block_key == 'prod' else f'unit_{item_id}'
        iu = str(form.get(unit_key, '') or '').strip()
        item = cur.execute("SELECT id,unit FROM items WHERE id=?", (item_id,)).fetchone()
        if not item:
            continue
        base_unit = (item['unit'] or 'ud').strip() or 'ud'
        iu = iu or base_unit
        qty_base = float(qty_input) * float(_unit_factor(iu, base_unit))
        if qty_base <= 0:
            continue
        line_sid = sid
        if not line_sid:
            try:
                line_sid = _suggest_supplier_id(cur, center_id, item_id) or None
            except Exception:
                line_sid = None
        existing = cur.execute("SELECT id,qty_base FROM order_lines WHERE order_id=? AND warehouse_id=? AND item_id=?", (order_id, int(wh_id), item_id)).fetchone()
        if existing:
            cur.execute("UPDATE order_lines SET qty_base=?, input_unit=?, qty_input=?, supplier_id=COALESCE(?, supplier_id), is_checked=0 WHERE id=? AND order_id=?",
                        (qty_base, iu, float(qty_input), line_sid, int(existing['id']), order_id))
        else:
            cur.execute("INSERT INTO order_lines(order_id,warehouse_id,item_id,qty_base,input_unit,qty_input,supplier_id,is_checked) VALUES(?,?,?,?,?,?,?,?)",
                        (order_id, int(wh_id), item_id, qty_base, iu, float(qty_input), line_sid, 0))
        added += 1
    conn.commit(); conn.close()
    return RedirectResponse(url=order_page_url(center_id=center_id, oid=order_id, ok=1, added=added, anchor='orderAddLine'), status_code=303)


@router.post("/order/{order_id}/add_line_form")
def order_add_line_form(
    order_id: int,
    warehouse_id: int = Form(...),
    item_id: str = Form(""),
    item_query: str = Form(""),
    qty_value: str = Form(""),
    qty_unit: str = Form(""),
    supplier_id: str = Form(""),
):
    conn = db(); cur = conn.cursor()
    o = cur.execute("SELECT center_id,status FROM orders WHERE id=?", (order_id,)).fetchone()
    if not o or o["status"] != "DRAFT":
        conn.close()
        return RedirectResponse(url=order_page_url(oid=order_id, err=1), status_code=303)
    if not _order_has_responsible(cur, order_id):
        conn.close()
        return RedirectResponse(url=order_page_url(center_id=int(o['center_id']), oid=order_id, ord_msg='responsible_required'), status_code=303)
    if not _warehouse_belongs_to_center(cur, int(warehouse_id), int(o['center_id'])):
        conn.close()
        return RedirectResponse(url=order_page_url(center_id=int(o['center_id']), oid=order_id, err=1), status_code=303)
    resolved_item_id = _resolve_item_id(cur, item_id, item_query)
    if not resolved_item_id:
        conn.close()
        return RedirectResponse(url=order_page_url(oid=order_id, err=1), status_code=303)
    item = cur.execute("SELECT unit FROM items WHERE id=?", (int(resolved_item_id),)).fetchone()
    if not item:
        conn.close()
        return RedirectResponse(url=order_page_url(oid=order_id, err=1), status_code=303)
    base_unit = item["unit"]
    iu = (qty_unit or base_unit).strip() or base_unit
    factor = _unit_factor(iu, base_unit)
    qty_input = _parse_float(qty_value, 0.0)
    qty_base = float(qty_input) * float(factor)
    if qty_base <= 0:
        conn.close()
        return RedirectResponse(url=order_page_url(oid=order_id, err=1), status_code=303)
    sid = parse_optional_int(supplier_id)
    existing = cur.execute("SELECT id,qty_base FROM order_lines WHERE order_id=? AND warehouse_id=? AND item_id=?", (order_id, int(warehouse_id), int(resolved_item_id))).fetchone()
    if existing:
        cur.execute("UPDATE order_lines SET qty_base=?, input_unit=?, qty_input=?, supplier_id=COALESCE(?, supplier_id), is_checked=0 WHERE id=? AND order_id=?",
                    (qty_base, iu, float(qty_input), sid, int(existing['id']), order_id))
    else:
        cur.execute(
            "INSERT INTO order_lines(order_id,warehouse_id,item_id,qty_base,input_unit,qty_input,supplier_id,is_checked) VALUES(?,?,?,?,?,?,?,?)",
            (order_id, int(warehouse_id), int(resolved_item_id), qty_base, iu, float(qty_input), sid, 0))
    conn.commit(); conn.close()
    return RedirectResponse(
        url=order_page_url(center_id=int(o['center_id']), oid=order_id, ok=1),
        status_code=303)


@router.post("/order/{order_id}/update_line/{line_id}")
def order_update_line_form(
    order_id: int, line_id: int,
    qty_value: str = Form(...), qty_unit: str = Form(...), supplier_id: str = Form(""),
):
    conn = db(); cur = conn.cursor()
    o = cur.execute("SELECT center_id,status FROM orders WHERE id=?", (order_id,)).fetchone()
    if not o or o["status"] != "DRAFT":
        conn.close()
        return RedirectResponse(url=order_page_url(oid=order_id, err=1), status_code=303)
    if not _order_has_responsible(cur, order_id):
        conn.close()
        return RedirectResponse(url=order_page_url(center_id=int(o['center_id']), oid=order_id, ord_msg='responsible_required'), status_code=303)
    ln = cur.execute("SELECT id,item_id FROM order_lines WHERE id=? AND order_id=?",
                     (line_id, order_id)).fetchone()
    if not ln:
        conn.close()
        return RedirectResponse(url=order_page_url(oid=order_id, err=1), status_code=303)
    qty_input = _parse_float(qty_value, 0.0)
    if qty_input <= 0:
        conn.close()
        return RedirectResponse(url=order_page_url(center_id=int(o['center_id']), oid=order_id, err=1),
                                status_code=303)
    item = cur.execute("SELECT unit FROM items WHERE id=?", (int(ln["item_id"]),)).fetchone()
    base_unit = (item["unit"] if item else "ud") or "ud"
    iu = (qty_unit or base_unit).strip() or base_unit
    qty_base = float(qty_input) * float(_unit_factor(iu, base_unit))
    if qty_base <= 0:
        conn.close()
        return RedirectResponse(url=order_page_url(center_id=int(o['center_id']), oid=order_id, err=1), status_code=303)
    sid = parse_optional_int(supplier_id)
    cur.execute("UPDATE order_lines SET qty_base=?,input_unit=?,qty_input=?,supplier_id=COALESCE(?, supplier_id),is_checked=0 WHERE id=? AND order_id=?",
                (qty_base, iu, float(qty_input), sid, line_id, order_id))
    conn.commit(); conn.close()
    return RedirectResponse(
        url=order_page_url(center_id=int(o['center_id']), oid=order_id, ok=1),
        status_code=303)


@router.post("/order/{order_id}/delete_line/{line_id}")
def order_delete_line_form(order_id: int, line_id: int):
    conn = db(); cur = conn.cursor()
    o = cur.execute("SELECT center_id,status FROM orders WHERE id=?", (order_id,)).fetchone()
    if not o or o["status"] != "DRAFT":
        conn.close()
        return RedirectResponse(url=order_page_url(oid=order_id, err=1), status_code=303)
    if not _order_has_responsible(cur, order_id):
        conn.close()
        return RedirectResponse(url=order_page_url(center_id=int(o['center_id']), oid=order_id, ord_msg='responsible_required'), status_code=303)
    cur.execute("DELETE FROM order_lines WHERE id=? AND order_id=?", (line_id, order_id))
    conn.commit(); conn.close()
    return RedirectResponse(
        url=order_page_url(center_id=int(o['center_id']), oid=order_id, anchor='orderLines'), status_code=303)


@router.post("/order/{order_id}/confirm_form")
def order_confirm_form(order_id: int):
    conn = db(); cur = conn.cursor()
    o = cur.execute("SELECT center_id,status FROM orders WHERE id=?", (order_id,)).fetchone()
    if not o or o["status"] != "DRAFT":
        conn.close()
        return RedirectResponse(url=order_page_url(oid=order_id, err=1), status_code=303)
    if not _order_has_responsible(cur, order_id):
        conn.close()
        return RedirectResponse(url=order_page_url(center_id=int(o['center_id']), oid=order_id, ord_msg='responsible_required'), status_code=303)
    ln = cur.execute("SELECT COUNT(*) c FROM order_lines WHERE order_id=?", (order_id,)).fetchone()["c"]
    if not ln:
        conn.close()
        return RedirectResponse(
            url=order_page_url(center_id=int(o['center_id']), oid=order_id, err=1),
            status_code=303)
    cur.execute("UPDATE orders SET status='CONFIRMED' WHERE id=?", (order_id,))
    conn.commit(); conn.close()
    return RedirectResponse(
        url=order_page_url(center_id=int(o['center_id']), oid=order_id, ok=1),
        status_code=303)


@router.post("/order/{order_id}/reopen_form")
def order_reopen_form(order_id: int):
    conn = db(); cur = conn.cursor()
    o = cur.execute("SELECT center_id,status FROM orders WHERE id=?", (order_id,)).fetchone()
    if not o or o["status"] != "CONFIRMED":
        conn.close()
        return RedirectResponse(url=order_page_url(oid=order_id, err=1), status_code=303)
    if not _order_has_responsible(cur, order_id):
        conn.close()
        return RedirectResponse(url=order_page_url(center_id=int(o['center_id']), oid=order_id, ord_msg='responsible_required'), status_code=303)
    cur.execute("UPDATE orders SET status='DRAFT' WHERE id=?", (order_id,))
    conn.commit(); conn.close()
    return RedirectResponse(
        url=order_page_url(center_id=int(o['center_id']), oid=order_id, ok=1),
        status_code=303)



@router.post("/order/{order_id}/delete_form")
def order_delete_form(order_id: int):
    conn = db(); cur = conn.cursor()
    o = cur.execute("SELECT status,center_id FROM orders WHERE id=?", (order_id,)).fetchone()
    if not o or o["status"] != "DRAFT":
        conn.close()
        return RedirectResponse(url=order_page_url(oid=order_id, err=1), status_code=303)
    center_id = int(o["center_id"])
    cur.execute("DELETE FROM order_lines WHERE order_id=?", (order_id,))
    cur.execute("DELETE FROM orders WHERE id=?", (order_id,))
    conn.commit(); conn.close()
    return RedirectResponse(url=order_page_url(center_id=center_id, ok=1, anchor=''), status_code=303)


@router.post("/order/{order_id}/archive_form")
def order_archive_form(order_id: int):
    conn = db(); cur = conn.cursor()
    o = cur.execute("SELECT status,center_id FROM orders WHERE id=?", (order_id,)).fetchone()
    if not o or o["status"] != "CONFIRMED":
        conn.close()
        return RedirectResponse(url=order_page_url(oid=order_id, err=1), status_code=303)
    cur.execute("UPDATE orders SET status='ARCHIVED' WHERE id=?", (order_id,))
    conn.commit(); conn.close()
    return RedirectResponse(url=order_page_url(center_id=int(o['center_id']), ok=1, anchor=''), status_code=303)


@router.post("/order/{order_id}/restore_form")
def order_restore_form(order_id: int):
    conn = db(); cur = conn.cursor()
    o = cur.execute("SELECT status,center_id FROM orders WHERE id=?", (order_id,)).fetchone()
    if not o or o["status"] != "ARCHIVED":
        conn.close()
        return RedirectResponse(url=order_page_url(oid=order_id, err=1), status_code=303)
    cur.execute("UPDATE orders SET status='CONFIRMED' WHERE id=?", (order_id,))
    conn.commit(); conn.close()
    return RedirectResponse(
        url=order_page_url(center_id=int(o['center_id']), oid=order_id, show_archived_orders=1, ok=1),
        status_code=303)


@router.get("/order/{order_id}/print", response_class=HTMLResponse)
def order_print(order_id: int, request: Request):
    conn = db(); cur = conn.cursor()
    od = order_with_lines(cur, int(order_id))
    conn.close()
    if not od:
        return HTMLResponse("Pedido no encontrado", status_code=404)
    lines = od.get("lines") or []
    def _sort_key(line):
        supplier = (line.get("supplier_name") or "~").strip().lower()
        item = (line.get("item_name") or "").strip().lower()
        return (supplier, item)
    lines = sorted(lines, key=_sort_key)

    def esc(s):
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def qty_str(l):
        try:
            q = float(l.get("qty_input") or 0)
            u = (l.get("input_unit") or l.get("base_unit") or "").strip()
            return esc(human_qty(q, u))
        except Exception:
            return esc(str(l.get("qty_base") or ""))

    grouped_rows = []
    last_supplier = None
    for l in lines:
        supplier_label = esc(l.get('supplier_name','') or '—')
        if supplier_label != last_supplier:
            grouped_rows.append(f"<tr class='supplier-group'><td colspan='4'><b>Proveedor: {supplier_label}</b></td></tr>")
            last_supplier = supplier_label
        grouped_rows.append(
            f"<tr><td>{esc(l.get('item_name',''))}</td>"
            f"<td>{esc(l.get('warehouse_name',''))}</td>"
            f"<td>{supplier_label}</td>"
            f"<td style='text-align:right'>{qty_str(l)}</td></tr>"
        )
    rows = ''.join(grouped_rows)
    html = f"""<!doctype html><html><head><meta charset='utf-8'><title>Pedido #{od['id']}</title>
<style>
  @page {{ size:A4; margin:14mm; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,Arial,sans-serif; font-size:12px; }}
  h1 {{ font-size:18px; margin:0 0 6px 0; }}
  .meta {{ margin:0 0 12px 0; color:#333; }}
  table {{ width:100%; border-collapse:collapse; }}
  th,td {{ border:1px solid #999; padding:6px; }}
  th {{ background:#f2f2f2; text-align:left; }}
  .supplier-group td {{ background:#f7f7f7; font-weight:700; }}
  .print-footer {{ margin-top:auto; padding-top:10mm; text-align:right; font-size:9px; color:#666; }}
</style></head><body>
<h1>Pedido #{od['id']} · {esc(od.get('center_name',''))}</h1>
<div class='meta'>
  <div><b>Estado:</b> {esc(status_label(od.get('status','')))}</div>
  <div><b>Fecha:</b> {esc(fmt_dt(od.get('created_at','')))}</div>
  <div><b>Nota:</b> {esc(od.get('note','') or '—')}</div>
</div>
<table><thead><tr><th>Artículo</th><th>Almacén</th><th>Proveedor</th><th style='text-align:right'>Cantidad</th></tr></thead>
<tbody>{rows}</tbody></table>
<div class='print-footer'><div class='print-logo'><div class='brand'>F&amp;B MVP</div><div>Created by Mauro Ciccarelli</div></div></div>
<script>window.print();</script>
</body></html>"""
    return HTMLResponse(html)

@router.post("/order/{order_id}/free_note_form")
def order_free_note_form(order_id: int, text: str = Form(''), target_date: str = Form('')):
    conn = db(); cur = conn.cursor(); ensure_columns(cur)
    o = cur.execute("SELECT center_id,status FROM orders WHERE id=?", (order_id,)).fetchone()
    if not o or o['status'] != 'DRAFT':
        conn.close()
        return RedirectResponse(url=order_page_url(oid=order_id, err=1), status_code=303)
    txt = (text or '').strip()
    if not txt:
        conn.close()
        return RedirectResponse(url=order_page_url(center_id=int(o['center_id']), oid=order_id, err=1, anchor='orderAddLine'), status_code=303)
        # Schema for `order_free_notes` is managed by `backend/migrate.py`.
    cur.execute("INSERT INTO order_free_notes(order_id,center_id,text,target_date,status,created_at) VALUES(?,?,?,?,?,?)",
                (int(order_id), int(o['center_id']), txt, (target_date or '').strip(), 'IDEA', datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit(); conn.close()
    return RedirectResponse(url=order_page_url(center_id=int(o['center_id']), oid=order_id, ok=1, anchor='orderAddLine'), status_code=303)
