from __future__ import annotations

# ==============================================================================
# BLOQUE STOCK · Movimientos, niveles min/max, artículos
# ==============================================================================
from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from typing import Optional
from datetime import datetime
import sqlite3
import unicodedata
from urllib.parse import quote_plus
import time
import threading
import os

from app.core import (
    db, _retry_db_write, _parse_float, _resolve_item_id,
    ensure_columns, get_unit_factor, normalize_price_to_base,
    upper_name, suggest_item_waste_pct, get_dashboard_data, human_qty, fmt_num,
    preferred_price_unit, preferred_display_qty, get_elaborados_stock, get_production_stocks
)
from app.services.stock_service import create_stock_movement, save_item_minmax
from app.services.stock_queries_service import resolve_item_id_strict, stock_page_url
from app.services.orders_service import classify_order_fresh_group, item_matches_order_filters

router = APIRouter()

# Simple in-memory TTL cache for production stocks (keyed by center_id)
_PRODUCTION_STOCKS_CACHE: dict = {}
_PRODUCTION_STOCKS_CACHE_LOCK = threading.Lock()
# seconds; override with env var PRODUCTION_STOCKS_CACHE_TTL
_PRODUCTION_STOCKS_CACHE_TTL = int(os.getenv('PRODUCTION_STOCKS_CACHE_TTL', '30'))


def clear_production_stocks_cache(center_id: int | None = None):
    """Clear cached /api/elaborados entries. If center_id is provided,
    only clears that key; otherwise clears all.
    """
    try:
        with _PRODUCTION_STOCKS_CACHE_LOCK:
            if center_id is None:
                _PRODUCTION_STOCKS_CACHE.clear()
            else:
                k = f"center:{int(center_id or 0)}"
                if k in _PRODUCTION_STOCKS_CACHE:
                    del _PRODUCTION_STOCKS_CACHE[k]
    except Exception:
        pass


def _norm_search_text(value: str) -> str:
    s = unicodedata.normalize('NFKD', str(value or ''))
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    return s.lower().strip()



def _stock_anchor(section: str | None) -> str:
    key = (section or 'fresh').strip().lower()
    mapping = {
        'fresh': 'stockFreshPanel',
        'frozen': 'stockFrozenPanel',
        'dry': 'stockDryPanel',
        'clean': 'stockCleaningPanel',
        'cleaning': 'stockCleaningPanel',
        'unclassified': 'stockUnclassifiedPanel',
        'unlocated': 'stockUnlocatedPanel',
        'current_all': 'stockCurrentAllPanel',
        'productions': 'stockProductionsPanel',
    }
    return mapping.get(key, 'stockFreshPanel')

# ==============================================================================
# MOVIMIENTOS
# ==============================================================================

@router.post("/movement/create_form")
def create_movement_form(
    center_id: int = Form(...),
    warehouse_id: int = Form(...),
    item_id: Optional[str] = Form(None),
    item_query: str = Form(""),
    movement_type: str = Form(...),
    qty_value: str = Form("0"),
    qty_unit: str = Form(...),
    note: str = Form(""),
    after: str = Form("stay"),
    stock_section: str = Form("fresh"),
):
    resolved_item_id = resolve_item_id_strict(item_id, item_query)
    if not resolved_item_id:
        return RedirectResponse(url=stock_page_url(center_id=center_id, err="1", anchor=_stock_anchor(stock_section), stock_section=stock_section), status_code=303)

    res = _create_movement_internal(center_id, warehouse_id, int(resolved_item_id),
                                    movement_type, _parse_float(qty_value, 0.0), qty_unit, note)
    if isinstance(res, JSONResponse) and res.status_code >= 400:
        return RedirectResponse(url=stock_page_url(center_id=center_id, err="1", anchor=_stock_anchor(stock_section), stock_section=stock_section), status_code=303)

    if (after or "").lower() == "exit":
        return RedirectResponse(url=f"/?page=inicio&center_id={center_id}&mv_ok=1", status_code=303)
    return RedirectResponse(url=stock_page_url(center_id=center_id, ok="mv_ok", anchor=_stock_anchor(stock_section), stock_section=stock_section, stock_item_id=int(res.get('item_id') or resolved_item_id), stock_wh_id=int(res.get('warehouse_id') or warehouse_id), stock_q=item_query), status_code=303)


@router.post("/stock/initial_load_form")
def stock_initial_load_form(
    center_id: int = Form(...),
    warehouse_id: int = Form(...),
    item_id: Optional[str] = Form(None),
    item_query: str = Form(""),
    qty_value: str = Form("0"),
    qty_unit: str = Form(...),
    stock_section: str = Form("fresh"),
):
    return create_movement_form(
        center_id=center_id, warehouse_id=warehouse_id,
        item_id=item_id, item_query=item_query,
        movement_type="ENTRADA", qty_value=qty_value,
        qty_unit=qty_unit, note="CARGA INICIAL", after="stay", stock_section=stock_section)


@router.post("/api/movement")
def create_movement(
    center_id: int = Form(...),
    warehouse_id: int = Form(...),
    item_id: int = Form(...),
    movement_type: str = Form(...),
    qty_value: float = Form(...),
    qty_unit: str = Form(...),
    note: str = Form(""),
):
    return _create_movement_internal(center_id, warehouse_id, item_id, movement_type,
                                     qty_value, qty_unit, note)


def _create_movement_internal(center_id, warehouse_id, item_id, movement_type, qty_value, qty_unit, note):
    conn = db()
    cur = conn.cursor()
    try:
        res = create_stock_movement(cur, center_id, warehouse_id, item_id, movement_type, qty_value, qty_unit, note)
        if res.get('ok'):
            conn.commit()
            try:
                # Invalidate cached production stocks since movements may affect reported stock
                clear_production_stocks_cache(center_id)
            except Exception:
                pass
            return res
        return JSONResponse({'ok': False, 'error': res.get('error', 'Error')}, status_code=res.get('_status', 400))
    finally:
        conn.close()


# ==============================================================================
# MIN/MAX
# ==============================================================================

@router.post("/item/{item_id}/minmax_form")
def update_minmax_form(
    item_id: int,
    min_qty: str = Form("0"),
    max_qty: str = Form("0"),
    min_unit: str = Form(""),
    max_unit: str = Form(""),
    center_id: str = Form(""),
    warehouse_id: str = Form(""),
    stock_section: str = Form("current_all"),
    stock_q: str = Form(""),
    stock_item_id: str = Form(""),
    stock_wh_id: str = Form(""),
):
    def _num(s: str) -> float:
        s = (s or "").strip().replace(" ", "").replace(",", ".")
        return float(s) if s else 0.0

    conn = db()
    cur = conn.cursor()
    ensure_columns(cur)
    conn.close()

    q_q = f"&stock_q={quote_plus(stock_q)}" if (stock_q or '').strip() else ""
    item_q = f"&stock_item_id={int(stock_item_id)}" if str(stock_item_id).isdigit() else ""
    wh_q = f"&stock_wh_id={int(stock_wh_id)}" if str(stock_wh_id).isdigit() else ""
    try:
        save_item_minmax(item_id, _num(min_qty), _num(max_qty), min_unit, max_unit, center_id, warehouse_id)
    except Exception:
        center_q = f"&center_id={int(center_id)}" if str(center_id).isdigit() else ""
        section_q = f"&stock_section={stock_section}" if (stock_section or "").strip() else ""
        redirect_q = f"&minmax_center={int(center_id)}&minmax_wh={int(warehouse_id)}" if str(center_id).isdigit() and str(warehouse_id).isdigit() else ""
        return RedirectResponse(url=f"/?page=stock{center_q}&minmax_item={item_id}{redirect_q}{section_q}{q_q}{item_q}{wh_q}&err=1#minmaxPanel", status_code=303)

    center_q = f"&center_id={int(center_id)}" if str(center_id).isdigit() else ""
    section_q = f"&stock_section={stock_section}" if (stock_section or "").strip() else ""
    redirect_q = f"&minmax_center={int(center_id)}&minmax_wh={int(warehouse_id)}" if str(center_id).isdigit() and str(warehouse_id).isdigit() else ""
    return RedirectResponse(url=f"/?page=stock{center_q}&minmax_item={item_id}{redirect_q}{section_q}{q_q}{item_q}{wh_q}&ok=1#minmaxPanel", status_code=303)


@router.post("/api/item/{item_id}/minmax")
def update_minmax(
    item_id: int,
    min_qty: float = Form(...),
    max_qty: float = Form(...),
    min_unit: str = Form(""),
    max_unit: str = Form(""),
    center_id: str = Form(""),
    warehouse_id: str = Form(""),
    stock_section: str = Form("current_all"),
):
    conn = db()
    cur = conn.cursor()
    ensure_columns(cur)
    conn.close()
    try:
        save_item_minmax(item_id, float(min_qty), float(max_qty), min_unit, max_unit, center_id, warehouse_id)
    except LookupError:
        return JSONResponse({"ok": False, "error": "Artículo inválido"}, status_code=400)
    except Exception:
        return JSONResponse({"ok": False, "error": "Rango o unidad inválidos"}, status_code=400)
    return {"ok": True, "message": "Mín/Máx guardados"}


# ==============================================================================
# PRECIO ARTÍCULO
# ==============================================================================

@router.post("/item/{item_id}/price_form")
def update_item_price_form(item_id: int, current_price: str = Form("0")):
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE items SET current_price=? WHERE id=?",
                (_parse_float(current_price, 0.0), item_id))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/?page=admin&price_ok=1", status_code=303)


# ==============================================================================
# API STOCKS / ITEMS
# ==============================================================================

@router.get("/api/stocks")
def api_stocks(center_id: Optional[int] = None):
    centers, warehouses, items, stocks, summary, recipes = get_dashboard_data(center_id)
    stocks_json = [{k: s[k] for k in s.keys()} for s in stocks]
    return {"ok": True, "stocks": stocks_json, "summary": summary}


@router.get("/api/items")
def api_items(q: str = "", limit: int = 20):
    qn = (q or "").strip()
    limit = max(1, min(int(limit or 20), 50))
    conn = db()
    cur = conn.cursor()
    rows = cur.execute("SELECT id,name,unit,COALESCE(stock_area,'') stock_area FROM items ORDER BY name").fetchall()
    conn.close()
    items = [{"id": r["id"], "name": r["name"], "unit": r["unit"], "stock_area": r["stock_area"]} for r in rows]
    if qn:
        qnorm = _norm_search_text(qn)
        def rank(it):
            name_norm = _norm_search_text(it.get("name") or "")
            exact = 0 if name_norm == qnorm else 1
            starts = 0 if name_norm.startswith(qnorm) else 1
            contains = 0 if qnorm in name_norm else 1
            return (exact, starts, contains, name_norm)
        items = [it for it in items if qnorm in _norm_search_text(it.get("name") or "")]
        items.sort(key=rank)
    return {"ok": True, "items": items[:limit]}


@router.get("/api/items/search")
def search_items(q: str = "", limit: int = 50, block: str = "", fresh_group: str = ""):
    conn = db()
    cur = conn.cursor()
    qn = (q or "").strip()
    try:
        lim = max(1, min(int(limit or 50), 250))
    except Exception:
        lim = 50
    rows = cur.execute("SELECT id,name,unit,COALESCE(stock_area,'') stock_area FROM items ORDER BY LOWER(name)").fetchall()
    conn.close()
    items = []
    for r in rows:
        item = {"id": r["id"], "name": r["name"], "unit": r["unit"], "stock_area": r["stock_area"]}
        item["fresh_group"] = classify_order_fresh_group(item.get("name") or "", "")
        items.append(item)
    if block or fresh_group:
        items = [it for it in items if item_matches_order_filters(it, block=block, fresh_group=fresh_group)]
    if qn:
        qnorm = _norm_search_text(qn)
        def rank(it):
            name_norm = _norm_search_text(it.get("name") or "")
            exact = 0 if name_norm == qnorm else 1
            starts = 0 if name_norm.startswith(qnorm) else 1
            contains = 0 if qnorm in name_norm else 1
            return (exact, starts, contains, name_norm)
        items = [it for it in items if qnorm in _norm_search_text(it.get("name") or "")]
        items.sort(key=rank)
    return {"ok": True, "items": items[:lim]}


@router.get("/api/elaborados")
def api_elaborados(center_id: int = 0):
    """Devuelve el stock de elaborados con porciones calculadas."""
    key = f"center:{int(center_id or 0)}"
    now = time.time()
    try:
        # check cache first
        with _PRODUCTION_STOCKS_CACHE_LOCK:
            entry = _PRODUCTION_STOCKS_CACHE.get(key)
            if entry:
                ts, payload = entry
                if now - ts < _PRODUCTION_STOCKS_CACHE_TTL:
                    print(f"TIMING api_elaborados center={center_id} cached=1 ttl={_PRODUCTION_STOCKS_CACHE_TTL}")
                    return {"ok": True, "elaborados": payload}

        t0 = time.time()
        conn = db(); cur = conn.cursor()
        data = get_production_stocks(cur, center_id if center_id else None)
        conn.close()
        elapsed = time.time() - t0

        # cache result (thread-safe)
        try:
            with _PRODUCTION_STOCKS_CACHE_LOCK:
                _PRODUCTION_STOCKS_CACHE[key] = (time.time(), data)
        except Exception:
            pass

        print(f"TIMING api_elaborados center={center_id} cached=0 elapsed={elapsed:.3f}s")
        return {"ok": True, "elaborados": data}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
