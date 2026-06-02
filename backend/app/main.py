from __future__ import annotations

# ==============================================================================
# F&B MVP · main.py — Punto de entrada limpio
# Versión modular v8.7.175
# Cada bloque funcional está en su propio router:
#   stock · recetas · producciones · pedidos · albaranes · laboratorio · admin
# El OCR engine está aislado en app/ocr/engine.py
# ==============================================================================
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional
import sqlite3
import re
import time
import os
import io
import socket
import subprocess

from app.core import (
    # DB y configuración
    db, init_db, ensure_columns, apply_startup_business_corrections, _retry_db_write, _is_db_locked_error,
    APP_DIR, UPLOADS_DIR, BUILD_ID, DB_PATH,
    # Constantes de negocio
    CATEGORY_CODES, SUBCATEGORIES, ALLERGENS_UE,
    # Formato y utilidades
    human_qty, fmt_dt, status_label, fmt_num, fmt_price,
    display_price_from_base, preferred_price_unit, preferred_display_qty,
    _ocr_state_label, _parse_float, _cache_bust_token, _norm_text, safe_insert_returning,
    # Datos del dashboard
    get_dashboard_data, recipe_visible_in_center,
    STOCK_AREAS, stock_area_label, normalize_stock_area, normalize_minmax_qty_for_base,
    get_production_stocks,
    recipe_with_calc, production_with_lines, order_with_lines,
    _supplier_options_for_item, cleanup_receipt_photos,
    # Recetas
    next_recipe_code, _parse_scope,
    # Albaranes OCR display
    _ocr_postfix_product_cleanup, _ocr_lock_path,
    # Limpieza startup
    _clear_pending_receipts_runtime,
)

# --- Routers ---
from app.productions_panel import create_batch_productions
from app.services.productions_view_service import get_production_detail, list_productions
from app.services.productions_constants_service import production_groups, production_units
from app.services.orders_service import classify_order_fresh_group, infer_order_block
from app.services.waste_service import list_waste_records, waste_analytics, WASTE_REASONS, ensure_waste_schema
from app.services.operational_quick_service import list_operational_queue, get_ai_status
from app.services.monthly_direction_dashboard_service import build_monthly_direction_dashboard
from app.services.monthly_supplier_dashboard_service import build_monthly_supplier_dashboard
from app.services.monthly_recipe_sales_dashboard_service import build_monthly_recipe_sales_dashboard
from app.services.daily_business_dashboard_service import build_daily_business_dashboard
from app.services.executive_finance_dashboard_service import build_executive_finance_dashboard
from app.services.pos_modifiers_service import build_monthly_modifier_dashboard, list_recipe_modifiers_admin, interpret_free_pos_modifier_note
from app.services.oido_alfi_service import answer_oido_alfi
from app.routers import stock, recetas, producciones, pedidos, albaranes, laboratorio, admin, inventario, mermas, operativa, ai_system
from app.recipe_ai import router as recipe_ai_router

# ==============================================================================
# APP
# ==============================================================================

app = FastAPI(title=f"F&B MVP {BUILD_ID}")


class TimingMiddleware(BaseHTTPMiddleware):
    """Minimal timing middleware that logs and exposes X-Response-Time.

    Keeps implementation tiny and defensive so it never blocks requests.
    """
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        try:
            response = await call_next(request)
        except Exception as exc:
            dt = time.time() - start
            try:
                print(f"[timing] {request.method} {request.url.path} {dt:.3f}s ERROR {exc}")
            except Exception:
                pass
            raise
        dt = time.time() - start
        try:
            # Expose timing for quick diagnostics in responses and logs
            response.headers["X-Response-Time"] = f"{dt:.3f}s"
        except Exception:
            pass
        try:
            print(f"[timing] {request.method} {request.url.path} {dt:.3f}s")
        except Exception:
            pass
        return response


class NoStoreMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        try:
            path = request.url.path or ""
            ctype = (response.headers.get("content-type") or "").lower()
            if request.method == "GET" and (path == "/" or "text/html" in ctype):
                response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
        except Exception:
            pass
        return response


app.add_middleware(TimingMiddleware)
app.add_middleware(NoStoreMiddleware)

# --- Montar routers ---
app.include_router(stock.router)
app.include_router(recetas.router)
app.include_router(producciones.router)
app.include_router(pedidos.router)
app.include_router(albaranes.router)
app.include_router(laboratorio.router)
app.include_router(admin.router)
app.include_router(inventario.router)
app.include_router(mermas.router)
app.include_router(operativa.router)
app.include_router(ai_system.router)
app.include_router(recipe_ai_router.router)

# --- Archivos estáticos ---
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")

# --- Templates ---
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))
templates.env.globals.update(
    human_qty=human_qty,
    fmt_dt=fmt_dt,
    status_label=status_label,
    fmt_num=fmt_num,
    fmt_price=fmt_price,
    display_price_from_base=display_price_from_base,
    preferred_price_unit=preferred_price_unit,
    ocr_state_label=_ocr_state_label,
)


def _normalize_search_text(value: str) -> str:
    return _norm_text(value or '').strip().lower()


def _jinja_search_test(value, pattern) -> bool:
    return _normalize_search_text(pattern) in _normalize_search_text(value)


templates.env.tests['search'] = _jinja_search_test


def _fmt_qty(value, decimals: int = 3):
    try:
        if value is None:
            return "0"
        v = float(value)
    except Exception:
        return str(value)
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return f"{v:.{decimals}f}".rstrip("0").rstrip(".")


templates.env.filters["fmt_qty"] = _fmt_qty


def _jinja_search(value, pattern):
    try:
        import unicodedata
        def _norm(v):
            txt = str(v or '').strip().lower()
            txt = unicodedata.normalize('NFKD', txt)
            return ''.join(ch for ch in txt if not unicodedata.combining(ch))
        v = _norm(value)
        p = _norm(pattern)
        if not p:
            return True
        return p in v
    except Exception:
        return False


templates.env.tests["search"] = _jinja_search




@app.get("/api/tpv/modifiers/interpret")
def api_tpv_modifiers_interpret(recipe_id: int = 0, note: str = "", qty: float = 1.0, center_id: int = 0):
    """Previsualiza cómo System MAC interpretaría una nota libre del TPV.

    Solo lectura: no mueve stock, no cambia receta maestra y no confirma ventas.
    """
    try:
        conn = db(); cur = conn.cursor(); ensure_columns(cur)
        data = interpret_free_pos_modifier_note(cur, recipe_id=recipe_id, note=note, qty_sold=qty, center_id=center_id)
        conn.close()
        return JSONResponse(data)
    except Exception as exc:
        return JSONResponse({"ok": False, "status": "ERROR", "message": str(exc)}, status_code=200)


@app.get("/api/oido-alfi/query")
def api_oido_alfi_query(q: str = "", center_id: int = 0):
    """Consulta segura de OÍDO ALFI. Solo lectura; no ejecuta cambios críticos."""
    try:
        return JSONResponse(answer_oido_alfi(q, center_id))
    except Exception as exc:
        return JSONResponse({"ok": False, "type": "error", "message": f"OÍDO ALFI no pudo completar la consulta: {exc}"}, status_code=200)

# ==============================================================================
# STARTUP
# ==============================================================================

@app.on_event("startup")
def startup():
    try:
        print(f"SYSTEM_MAC_RUNTIME_DB={DB_PATH}")
        print(f"SYSTEM_MAC_UPLOADS_DIR={UPLOADS_DIR}")
    except Exception:
        pass
    try:
        _clear_pending_receipts_runtime()
    except Exception as exc:
        print(f"STARTUP_CLEAR_PENDING_SKIP reason={exc}")
    last_exc = None
    for attempt in range(8):
        try:
            init_db()
            try:
                apply_startup_business_corrections()
            except Exception as exc:
                print(f"STARTUP_BUSINESS_CORRECTIONS_SKIP reason={exc}")
            return
        except sqlite3.OperationalError as exc:
            last_exc = exc
            if not _is_db_locked_error(exc):
                raise
            print(f"STARTUP_DB_LOCKED attempt={attempt+1}/8")
            time.sleep(0.6 * (attempt + 1))
    print(f"STARTUP_DB_LOCKED_SKIP reason={last_exc}")




def _norm_warehouse_name(value: str) -> str:
    return (value or '').strip().lower().replace('á', 'a')


def _preferred_warehouse_names_for_raw_family(fam: str) -> set[str]:
    fam = (fam or '').strip().lower()
    if fam in {'verduras', 'carnes', 'pescados', 'lacteos_huevos', 'congelados'}:
        return {'camara'}
    if fam in {'secos', 'limpieza'}:
        return {'economato'}
    return set()


def _collapse_stock_rows_for_operational_view(rows, family_names: set[str] | None = None):
    selected = []
    groups = {}
    for s in rows or []:
        fam = (s.get('inventory_raw_family') or '').strip().lower()
        if family_names and fam not in family_names:
            continue
        key = (int(s.get('center_id') or 0), int(s.get('item_id') or 0))
        groups.setdefault(key, []).append(s)
    for _, item_rows in groups.items():
        ordered = sorted(
            item_rows,
            key=lambda s: (
                0 if _norm_warehouse_name(s.get('warehouse_name') or '') in _preferred_warehouse_names_for_raw_family(s.get('inventory_raw_family') or '') else 1,
                0 if normalize_stock_area(s.get('stock_area') or '') not in {'', 'SIN_CLASIFICACION'} else 1,
                0 if (float(s.get('stock_qty') or 0) != 0 or bool((s.get('last_move_at') or '').strip())) else 1,
                0 if (float(s.get('min_qty') or 0) > 0 or float(s.get('max_qty') or 0) > 0) else 1,
                str(s.get('warehouse_name') or ''),
                int(s.get('warehouse_id') or 0),
            )
        )
        if ordered:
            picked = dict(ordered[0])
            picked['_collapsed_from'] = len(item_rows)
            picked['_operational_warehouse_preferred'] = _norm_warehouse_name(picked.get('warehouse_name') or '') in _preferred_warehouse_names_for_raw_family(picked.get('inventory_raw_family') or '')
            active_alts = [r for r in item_rows if int(r.get('warehouse_id') or 0) != int(picked.get('warehouse_id') or 0) and (float(r.get('stock_qty') or 0) != 0 or bool((r.get('last_move_at') or '').strip()))]
            stock_area = normalize_stock_area(picked.get('stock_area') or '')
            class_note = ''
            if stock_area == 'SIN_CLASIFICACION':
                class_note = 'Pend. clasificar · revisar familia operativa'
            elif not stock_area:
                class_note = 'Sin ubicar · falta almacén lógico'
            picked['_classification_note'] = class_note
            if len(item_rows) > 1:
                picked['_operational_note'] = f"Vista operativa: {len(item_rows)} posiciones → {picked.get('warehouse_name') or 'almacén principal'}"
                if active_alts:
                    picked['_operational_note'] += f" · {len(active_alts)} con actividad adicional"
            else:
                picked['_operational_note'] = ''
            selected.append(picked)
    return sorted(selected, key=lambda s: (str(s.get('center_name') or '').lower(), str(s.get('item_name') or '').lower(), str(s.get('warehouse_name') or '').lower()))


def _inventory_raw_family(name: str, stock_area: str = ""):
    n = (name or "").lower()
    area = normalize_stock_area(stock_area or "")
    meat = ["pollo","ternera","vacuno","cerdo","solomillo","costilla","hamburg","secreto","presa","carrillera","chuleta","entrecot","cordero","bacon","panceta","jamon","jamón","chorizo"]
    fish = ["lubina","merluza","atun","atún","salmon","salmón","bacalao","pescado","sepia","calamar","langost","gamba","pulpo","mejillon","mejillón","marisco","dorada","almeja","ostra","navaja","berberecho","chirla","vieira"]
    dairy = ["huevo","huevos","leche","nata","queso","mantequilla","yogur","yogurt","mozzarella","parmesano","cheddar"]
    veg = ["tomate","lechuga","cebolla","ceboll","puerro","pimiento","pepino","cilantro","jalape","espinaca","zanahoria","patata","papa","berenjena","calabacin","calabacín","aguacate","brocoli","brócoli","col","repollo","hierba","menta","albahaca","cebollino","seta","champi","ajo","perejil","lima","limon","limón"]
    if area == 'LIMPIEZA':
        return 'limpieza'
    if area == 'CONGELADOS':
        return 'congelados'
    if area == 'SECOS':
        return 'secos'
    if any(k in n for k in fish):
        return 'pescados'
    if any(k in n for k in meat):
        return 'carnes'
    if any(k in n for k in dairy):
        return 'lacteos_huevos'
    if any(k in n for k in veg):
        return 'verduras'
    if area == 'FRESCOS':
        return 'verduras'
    if area == 'SIN_CLASIFICACION':
        return 'otros'
    return 'otros'


def _inventory_production_family(prod_group: str, name: str = "", recipe_subcategory: str = "", recipe_category: str = ""):
    g = (prod_group or "").strip().lower()
    n = (name or "").strip().lower()
    rs = (recipe_subcategory or "").strip().lower()
    rc = (recipe_category or "").strip().lower()

    def map_family(v: str):
        v = (v or "").strip().lower()
        if not v or v == "sin definir":
            return ""
        if "salsa" in v or "demi" in v or "alioli" in v or "vinagreta" in v:
            return "salsas"
        if "frío" in v or "frio" in v or "ensalad" in v:
            return "frio"
        if "caliente" in v:
            return "caliente"
        if "guarn" in v or "arroz" in v or "patata" in v:
            return "guarniciones"
        if "postr" in v or "tarta" in v or "bizcocho" in v or "crema" in v:
            return "postres"
        if "otro" in v:
            return "otros"
        return ""

    # Excepción operativa: si el nombre o la categoría general dicen claramente que es salsa,
    # no debe caer en Caliente por una subcategoría heredada/conflictiva.
    sauce_hint = any(k in (n + ' ' + rc + ' ' + g) for k in ['salsa', 'demi', 'alioli', 'vinagreta'])
    if sauce_hint:
        return 'salsas'

    fam = map_family(rs) or map_family(rc) or map_family(g)
    if fam:
        return fam
    if 'pico de gallo' in n or 'guacamole' in n or 'ensalad' in n:
        return 'frio'
    if 'tarta' in n or 'bizcocho' in n or 'crema' in n:
        return 'postres'
    if 'arroz' in n or 'patata' in n:
        return 'guarniciones'
    return 'otros'


_FINAL_DISH_HINTS = [
    'con ', ' y ', ' sobre ', ' al ', ' a la ', ' a los ', ' a las ', 'relleno', 'rellena',
    'hamburguesa', 'bocadillo', 'sandwich', 'taco ', 'ensalada de lechuga', 'salmon con',
    'salmón con', 'solomillo con', 'patatas al cabrales'
]
_IMAGE_FILE_HINTS = ['img ', 'img_', 'img-', 'imagen ', 'foto ', '.jpg', '.jpeg', '.png', '.heic', '.heif']
_INGREDIENT_ONLY_HINTS = ['tomillo fresco', 'romero fresco', 'cilantro', 'albahaca', 'perejil', 'tomate', 'lechuga']
_PRODUCTION_STRONG_HINTS = ['pico de gallo','fumet','fondo','caldo','salsa','demi glace','demi-glace','vinagreta','alioli','guacamole','pure','puré','patatas fritas','masa','base','porcionado','porcionada']
_OPERATIONAL_GROUP_HINTS = ['salsa','guarn','base','masa','pasteler','porcion','porción','frio','frío','caliente','postre']

def _norm_ascii(txt: str = '') -> str:
    try:
        import unicodedata
        t = unicodedata.normalize('NFKD', str(txt or ''))
        t = ''.join(ch for ch in t if not unicodedata.combining(ch))
        return t.lower().strip()
    except Exception:
        return str(txt or '').lower().strip()

def _looks_like_imported_file_name(name: str = '') -> bool:
    n = _norm_ascii(name)
    if not n:
        return True
    if any(h in n for h in _IMAGE_FILE_HINTS):
        return True
    # IMG 3878 / IMG3878 / IMG_3878
    compact = n.replace('_',' ').replace('-',' ').strip()
    parts = compact.split()
    return len(parts) <= 2 and parts and parts[0] == 'img' and any(ch.isdigit() for ch in compact)

def _is_likely_final_dish(name: str = '', category: str = '', subcategory: str = '') -> bool:
    n = _norm_ascii(name)
    c = _norm_ascii(category)
    sc = _norm_ascii(subcategory)
    combined = ' '.join([n,c,sc])
    if any(k in combined for k in ['principal', 'entrante', 'pescado', 'carne']) and not any(k in combined for k in _PRODUCTION_STRONG_HINTS):
        return True
    if any(h in n for h in _FINAL_DISH_HINTS) and not any(k in n for k in ['pico de gallo','patatas fritas','fumet','caldo','fondo','salsa','pure','puré']):
        return True
    return False

def _is_clean_production_candidate(name: str = '', category: str = '', subcategory: str = '', is_subrecipe=0, produced_item_id=0, explicit_producible=0) -> bool:
    n = _norm_ascii(name)
    c = _norm_ascii(category)
    sc = _norm_ascii(subcategory)
    if not n or _looks_like_imported_file_name(n):
        return False
    if any(n == h or n.startswith(h + ' ') for h in _INGREDIENT_ONLY_HINTS) and not any(k in n for k in _PRODUCTION_STRONG_HINTS):
        return False
    try:
        if int(explicit_producible or 0) == 1 or int(is_subrecipe or 0) == 1 or int(produced_item_id or 0) > 0:
            # aun así bloquear basura de foto
            return not _looks_like_imported_file_name(n)
    except Exception:
        pass
    if _is_likely_final_dish(n, c, sc):
        return False
    combined = ' '.join([n,c,sc])
    if any(k in combined for k in _PRODUCTION_STRONG_HINTS + _OPERATIONAL_GROUP_HINTS):
        return True
    return False


def _inventory_production_temperature(prod_group: str = '', name: str = '', recipe_subcategory: str = '', recipe_category: str = '') -> str:
    """Devuelve dimensión principal de producción: frio/caliente/postres.

    No compite con subcategorías como salsas, guarniciones o bases.
    Sirve para que el filtro Frío muestre también salsas/bases/guarniciones frías.
    """
    txt = ' '.join([str(prod_group or ''), str(name or ''), str(recipe_subcategory or ''), str(recipe_category or '')]).lower()
    if any(k in txt for k in ['postre', 'pasteler', 'tarta', 'bizcocho', 'dulce']):
        return 'postres'
    if any(k in txt for k in ['frío', 'frio', 'cold', 'ensalad', 'pico de gallo', 'guacamole', 'tartar', 'vinagreta']):
        return 'frio'
    if any(k in txt for k in ['caliente', 'hot', 'cocido', 'horno', 'plancha', 'frito']):
        return 'caliente'
    # Si no hay dato térmico, no se inventa; queda en subcategoría/otros.
    return ''


def _inventory_recipe_subfamily(prod_group: str = '', name: str = '', recipe_subcategory: str = '', recipe_category: str = '') -> str:
    """Subcategoría operativa independiente para Producciones."""
    txt = ' '.join([str(prod_group or ''), str(name or ''), str(recipe_subcategory or ''), str(recipe_category or '')]).lower()
    if any(k in txt for k in ['salsa', 'demi', 'alioli', 'vinagreta']):
        return 'salsas'
    if any(k in txt for k in ['guarn', 'arroz', 'patata', 'puré', 'pure']):
        return 'guarniciones'
    if any(k in txt for k in ['base', 'fondo', 'caldo']):
        return 'bases'
    if any(k in txt for k in ['masa', 'pan', 'pasta']):
        return 'masas'
    if any(k in txt for k in ['pasteler', 'tarta', 'bizcocho']):
        return 'pasteleria'
    if any(k in txt for k in ['porcion', 'porción', 'porcionado']):
        return 'porcionados'
    return ''


def _production_inventory_families(prod_group: str = '', name: str = '', recipe_subcategory: str = '', recipe_category: str = '') -> list[str]:
    """Familias en las que debe aparecer una receta/producción.

    Una misma producción puede verse por dimensión principal (Frío/Caliente/Postre)
    y por tipo operativo (Salsas/Guarniciones/Bases...).
    """
    out = []
    temp = _inventory_production_temperature(prod_group, name, recipe_subcategory, recipe_category)
    sub = _inventory_recipe_subfamily(prod_group, name, recipe_subcategory, recipe_category)
    primary = _inventory_production_family(prod_group, name, recipe_subcategory, recipe_category)
    for k in [temp, sub, primary]:
        if k and k not in out:
            out.append(k)
    if not out:
        out.append('otros')
    return out


def _inventory_counts_lookup(counts_map: dict, source_type: str, item_id: int, fams: list[str], warehouse_id: int):
    for fam in fams or []:
        key = f"{source_type}:{int(item_id or 0)}:{fam}:{int(warehouse_id or 0)}"
        if key in counts_map:
            return key, counts_map.get(key) or {}
    fam = (fams or ['otros'])[0]
    return f"{source_type}:{int(item_id or 0)}:{fam}:{int(warehouse_id or 0)}", {}


def _inventory_counts_map(session_id: int):
    if not session_id:
        return {}
    conn = db(); cur = conn.cursor()
    rows = cur.execute("SELECT * FROM inventory_counts WHERE session_id=? ORDER BY id", (int(session_id),)).fetchall()
    conn.close()
    out = {}
    for r in rows:
        d = {k: r[k] for k in r.keys()}
        key = f"{d.get('source_type') or 'raw'}:{int(d.get('item_id') or 0)}:{d.get('family_key') or ''}:{int(d.get('warehouse_id') or 0)}"
        out[key] = d
    return out





def _inventory_count_audit_label(cnt: dict) -> str:
    if not cnt:
        return ''
    orig = str(cnt.get('original_counted_by_name') or '').strip()
    mod = str(cnt.get('last_modified_by_name') or '').strip()
    mod_count = int(cnt.get('modified_count') or 0) if str(cnt.get('modified_count') or '0').isdigit() else 0
    parts = []
    if orig:
        parts.append(f"Contó: {orig}")
    if mod and mod_count > 0:
        if mod == orig:
            parts.append(f"Modificado por {mod}")
        else:
            parts.append(f"Modificado por {mod} (antes {orig or 'sin dato'})")
    if mod_count > 0:
        parts.append(f"Cambios: {mod_count}")
    return ' · '.join(parts)

def _inventory_allowed_modes_for_warehouse_name(warehouse_name: str | None):
    n = _norm_warehouse_name(warehouse_name or '')
    if n == 'economato':
        return {'limpieza', 'libres'}
    if n == 'cocina':
        return {'producciones', 'libres'}
    if n == 'cámara':
        return {'materias_primas', 'libres'}
    return {'materias_primas', 'producciones', 'limpieza', 'libres'}






def _inventory_normalize_family_for_warehouse(inv_mode: str, inv_family: str, warehouse_name: str = '') -> str:
    """Mantiene bloque/familia coherentes con el almacén físico seleccionado.

    Evita estados mezclados como Cocina + Secos o Cámara + Limpieza que aparecían
    al volver atrás o cambiar chips rápido en Inventario. El almacén filtra la zona
    física; si la familia heredada no aplica, se resetea a una familia operativa
    compatible y previsible.
    """
    mode = (inv_mode or 'materias_primas').strip().lower()
    fam = (inv_family or '').strip().lower()
    wh = _norm_warehouse_name(warehouse_name or '')
    raw_valid = {'verduras','carnes','pescados','lacteos_huevos','secos','congelados','limpieza','otros'}
    prod_valid = {'frio','caliente','postres','salsas','guarniciones','bases','masas','pasteleria','porcionados','otros'}
    if mode == 'producciones':
        return fam if fam in prod_valid else 'frio'
    if mode == 'limpieza':
        return 'limpieza'
    if mode == 'libres':
        return 'libres'
    if fam not in raw_valid:
        fam = 'verduras'
    # Economato es seco/limpieza; limpieza tiene bloque propio. En materias primas,
    # el default coherente es Secos.
    if wh == 'economato' and fam not in {'secos','otros'}:
        return 'secos'
    # Cámara concentra frescos/congelados. Nunca debe heredar Secos/Limpieza.
    if wh == 'camara' and fam in {'secos','limpieza'}:
        return 'verduras'
    # Cocina no debe quedarse mostrando Secos heredados de Economato.
    if wh == 'cocina' and fam in {'secos','limpieza'}:
        return 'verduras'
    return fam

def _default_warehouse_name_for_stock_area(stock_area: str) -> str | None:
    area = normalize_stock_area(stock_area or '')
    if area == 'LIMPIEZA':
        return 'economato'
    if area == 'SECOS':
        return 'economato'
    if area == 'FRESCOS':
        return 'cámara'
    if area == 'CONGELADOS':
        return 'cámara'
    return None

def _build_inventory_context(*, center_id, warehouses, stocks, production_stocks, request):
    inv_mode = (request.query_params.get('inv_mode') or 'materias_primas').strip().lower()
    if inv_mode not in {'materias_primas','producciones','limpieza','libres'}:
        inv_mode = 'materias_primas'
    inv_family = (request.query_params.get('inv_family') or ('verduras' if inv_mode=='materias_primas' else 'frio')).strip().lower()
    raw_valid = {'verduras','carnes','pescados','lacteos_huevos','secos','congelados','limpieza','otros'}
    prod_valid = {'frio','caliente','postres','salsas','guarniciones','bases','masas','pasteleria','porcionados','otros'}
    # Al cambiar rubro/bloque, la familia previa puede no ser válida.
    # Reset explícito e independiente para evitar que el usuario tenga que tocar familia manualmente.
    if inv_mode=='materias_primas' and inv_family not in raw_valid: inv_family='verduras'
    if inv_mode=='producciones' and inv_family not in prod_valid: inv_family='frio'
    if inv_mode=='limpieza': inv_family='limpieza'
    if inv_mode=='libres': inv_family='libres'

    conn = db(); cur = conn.cursor()
    ensure_columns(cur)
    current_session = None
    sid_q = request.query_params.get('inv_session_id') or ''
    if str(sid_q).isdigit():
        row = cur.execute("SELECT * FROM inventory_sessions WHERE id=?", (int(sid_q),)).fetchone()
        if row:
            current_session = {k: row[k] for k in row.keys()}
    if current_session is None:
        row = cur.execute("SELECT * FROM inventory_sessions WHERE center_id=? AND status IN ('DRAFT','COUNTING') ORDER BY id DESC LIMIT 1", (int(center_id or 0),)).fetchone()
        if row:
            current_session = {k: row[k] for k in row.keys()}
    if current_session is None:
        warehouse_id = 0
        sqlite_sql = "INSERT INTO inventory_sessions(center_id,warehouse_id,session_type,status,created_at,note) VALUES(?,?,?,?,datetime('now'),'')"
        pg_sql = sqlite_sql.replace('?', '%s')
        sid = safe_insert_returning(cur, sqlite_sql, (int(center_id or 0), int(warehouse_id or 0), 'MIXTO', 'DRAFT'), pg_sql=pg_sql)
        conn.commit()
        if sid:
            row = cur.execute("SELECT * FROM inventory_sessions WHERE id=?", (int(sid),)).fetchone()
            current_session = {k: row[k] for k in row.keys()} if row else None
        else:
            # Deterministic lookup when no id was returned
            try:
                row = cur.execute("SELECT id FROM inventory_sessions WHERE center_id=? AND warehouse_id=? AND session_type=? AND status=? ORDER BY id DESC LIMIT 1", (int(center_id or 0), int(warehouse_id or 0), 'MIXTO', 'DRAFT')).fetchone()
                last_id = int(row['id']) if row else 0
            except Exception:
                last_id = 0
            row = cur.execute("SELECT * FROM inventory_sessions WHERE id=?", (int(last_id),)).fetchone()
            current_session = {k: row[k] for k in row.keys()} if row else None
    conn.close()

    # Ensure we always have a dict to work with. If DB operations somehow
    # failed to create or return a session, provide a safe fallback so the
    # view can render instead of crashing with a TypeError.
    if current_session is None:
        current_session = {
            'id': 0,
            'warehouse_id': 0,
            'warehouse_name': 'Todos',
            'responsible_user_id': 0,
            'responsible_name': '',
            'note': ''
        }

    # Si la vista entra sin inv_session_id explícito, no preseleccionar responsable en la UI.
    if not str(sid_q).isdigit():
        current_session.setdefault('responsible_user_id', 0)
        current_session.setdefault('responsible_name', '')
        current_session.setdefault('note', '')

    counts_map = _inventory_counts_map(int(current_session.get('id') or 0))
    selected_wh = int(current_session.get('warehouse_id') or 0)
    warehouse_lookup = {0: 'Todos'}
    for _w in warehouses:
        try:
            _wid = int((_w['id'] if hasattr(_w, 'keys') else _w.get('id')) or 0)
        except Exception:
            _wid = 0
        _name = str((_w['name'] if hasattr(_w, 'keys') else _w.get('name')) or '').strip()
        if _name:
            warehouse_lookup[_wid] = _name
    current_session['warehouse_name'] = warehouse_lookup.get(selected_wh, 'Todos')
    # HOTFIX v8_7_331: el cambio de bloque/rubro NO debe quedar bloqueado
    # por el almacén guardado en la sesión. El almacén sirve para filtrar/contar,
    # no para impedir navegar entre Materias primas, Producciones, Limpieza y Líneas libres.
    # Antes se forzaba el modo permitido por almacén y por eso la vista quedaba clavada
    # en Producciones hasta tocar familia.
    allowed_modes = {'materias_primas', 'producciones', 'limpieza', 'libres'}
    seen_warehouse_ids = set()
    seen_warehouse_names = {'todos'}
    warehouse_options = [{'id': 0, 'name': 'Todos'}]
    for w in warehouses:
        row = {k: w[k] for k in w.keys()} if hasattr(w, 'keys') else dict(w)
        try:
            wid = int(row.get('id') or 0)
        except Exception:
            wid = 0
        wname = str(row.get('name') or '').strip() or f'Almacén {wid}'
        if len(wname) < 2 and wid != 0:
            continue
        wkey = wname.lower()
        if wid in seen_warehouse_ids or wkey in seen_warehouse_names:
            continue
        seen_warehouse_ids.add(wid)
        seen_warehouse_names.add(wkey)
        row['name'] = wname
        warehouse_options.append(row)
    selected_wh_name_norm = _norm_warehouse_name(current_session.get('warehouse_name'))
    inv_family = _inventory_normalize_family_for_warehouse(inv_mode, inv_family, current_session.get('warehouse_name') or '')
    raw_groups = {k: [] for k in ['verduras','carnes','pescados','lacteos_huevos','secos','congelados','limpieza','otros']}
    base_stock_source = []
    for srow in stocks:
        d = dict(srow)
        d['inventory_raw_family'] = _inventory_raw_family(d.get('item_name') or '', d.get('stock_area') or '')
        base_stock_source.append(d)
    # Diagnóstico: total conteable por familia sin el filtro de almacén actual.
    all_operational_stock = _collapse_stock_rows_for_operational_view(base_stock_source)
    all_raw_counts = {k: 0 for k in raw_groups.keys()}
    wh_raw_counts = {}
    for _d in base_stock_source:
        _fam = _d.get('inventory_raw_family') or 'otros'
        _wh = int(_d.get('warehouse_id') or 0)
        wh_raw_counts.setdefault(_wh, {k: 0 for k in raw_groups.keys()})
    for _d in all_operational_stock:
        _fam = _d.get('inventory_raw_family') or 'otros'
        if _fam in all_raw_counts:
            all_raw_counts[_fam] += 1
    for _d in base_stock_source:
        _fam = _d.get('inventory_raw_family') or 'otros'
        _wh = int(_d.get('warehouse_id') or 0)
        if _fam in wh_raw_counts.get(_wh, {}):
            # Solo contar filas operativas que existen en ese almacén tras higiene principal:
            # si no tiene actividad y no es almacén recomendado, el filtro principal la descartará.
            pass
    stock_source = list(base_stock_source)
    if selected_wh:
        stock_source = [d for d in stock_source if int(d.get('warehouse_id') or 0) == int(selected_wh)]
    else:
        # Vista global de Inventario: una línea operativa por artículo, no una por almacén.
        # Esto evita duplicados pero permite ver TODO el catálogo conteable, incluso stock 0.
        stock_source = list(all_operational_stock)
    for s in stock_source:
        try:
            whid = int(s.get('warehouse_id') or 0)
        except Exception:
            whid = 0
        fam = _inventory_raw_family(s.get('item_name') or '', s.get('stock_area') or '')
        key = f"raw:{int(s.get('item_id') or 0)}:{fam}:{whid}"
        cnt = counts_map.get(key) or {}
        raw_groups.setdefault(fam, []).append({
            'key': key,
            'item_id': int(s.get('item_id') or 0),
            'item_name': s.get('item_name') or '',
            'warehouse_id': whid,
            'warehouse_name': s.get('warehouse_name') or '',
            'base_unit': s.get('unit') or 'ud',
            'theoretical_qty': float(s.get('stock_qty') or 0),
            'physical_qty': float(cnt.get('physical_qty') or 0),
            'count_unit': (cnt.get('count_unit') or s.get('unit') or 'ud'),
            'is_checked': int(cnt.get('is_checked') or 0),
            'note': cnt.get('note') or '',
            'audit_summary': _inventory_count_audit_label(cnt),
            'original_counted_by_name': cnt.get('original_counted_by_name') or '',
            'last_modified_by_name': cnt.get('last_modified_by_name') or '',
            'modified_count': int(cnt.get('modified_count') or 0),
            'unit_cost_snapshot': float(s.get('current_price') or 0),
            'duplicate_collapsed': int(s.get('_collapsed_from') or 1),
            'operational_note': s.get('_operational_note') or '',
            'classification_note': s.get('_classification_note') or '',
        })
    # Higiene visual de inventario: evitar que el mismo artículo aparezca repetido muchas veces
    # por duplicados de catálogo o uniones de stock sin movimiento. Se agrupa por nombre+almacén+unidad.
    # Si existen cantidades teóricas en varias filas con el mismo nombre, se suman para no perder lectura.
    for fam in list(raw_groups.keys()):
        grouped = []
        by_key = {}
        for r in raw_groups.get(fam, []):
            name_key = str(r.get('item_name') or '').strip().lower()
            wh_key = int(r.get('warehouse_id') or 0)
            unit_key = str(r.get('base_unit') or '').strip().lower()
            key2 = (name_key, wh_key, unit_key)
            if key2 in by_key:
                prev = by_key[key2]
                try:
                    prev['theoretical_qty'] = float(prev.get('theoretical_qty') or 0) + float(r.get('theoretical_qty') or 0)
                except Exception:
                    pass
                # Si la línea duplicada estaba contada, conservar el dato humano.
                if int(r.get('is_checked') or 0) == 1:
                    prev['physical_qty'] = r.get('physical_qty') or prev.get('physical_qty')
                    prev['count_unit'] = r.get('count_unit') or prev.get('count_unit')
                    prev['note'] = r.get('note') or prev.get('note')
                    prev['is_checked'] = 1
                prev['duplicate_collapsed'] = int(prev.get('duplicate_collapsed') or 1) + 1
                continue
            r['duplicate_collapsed'] = 1
            by_key[key2] = r
            grouped.append(r)
        raw_groups[fam] = grouped
    for fam in raw_groups:
        raw_groups[fam].sort(key=lambda x: ((x['theoretical_qty']<=0), x['item_name'].lower()))

    prod_groups = {k: [] for k in ['frio','caliente','postres','salsas','guarniciones','bases','masas','pasteleria','porcionados','otros']}
    prod_id_groups = {}
    recipe_meta = {}
    if production_stocks:
        conn = db(); cur = conn.cursor()
        ids = sorted({int(p.get('last_prod_id') or 0) for p in production_stocks if int(p.get('last_prod_id') or 0) > 0})
        if ids:
            qs = ','.join('?'*len(ids))
            rows = cur.execute(f"SELECT id, COALESCE(production_group,'Otros') production_group FROM productions WHERE id IN ({qs})", ids).fetchall()
            prod_id_groups = {int(r['id']): (r['production_group'] or 'Otros') for r in rows}
        recipe_names = sorted({str(p.get('recipe_name') or p.get('item_name') or '').strip().lower() for p in production_stocks if str(p.get('recipe_name') or p.get('item_name') or '').strip()})
        if recipe_names:
            qs = ','.join('?'*len(recipe_names))
            rows = cur.execute(f"SELECT lower(trim(name)) k, COALESCE(subcategory,'') subcategory, COALESCE(category,'') category FROM recipes WHERE lower(trim(name)) IN ({qs})", recipe_names).fetchall()
            recipe_meta = {str(r['k']): {'subcategory': (r['subcategory'] or ''), 'category': (r['category'] or '')} for r in rows}
        conn.close()
    for p in production_stocks:
        try:
            whid = int(p.get('warehouse_id') or 0)
        except Exception:
            whid = 0
        if selected_wh and whid != selected_wh:
            continue
        pg = prod_id_groups.get(int(p.get('last_prod_id') or 0), '')
        recipe_key = str(p.get('recipe_name') or p.get('item_name') or '').strip().lower()
        recipe_meta_row = recipe_meta.get(recipe_key, {})
        recipe_sub = recipe_meta_row.get('subcategory', '')
        recipe_cat = recipe_meta_row.get('category', '')
        if _looks_like_imported_file_name(p.get('item_name') or '') or _is_likely_final_dish(p.get('item_name') or '', recipe_cat, recipe_sub):
            continue
        fams = _production_inventory_families(pg, p.get('item_name') or '', recipe_sub, recipe_cat)
        key, cnt = _inventory_counts_lookup(counts_map, 'production', int(p.get('item_id') or 0), fams, whid)
        base_row = {
            'key': key, 'item_id': int(p.get('item_id') or 0), 'item_name': p.get('item_name') or '',
            'warehouse_id': whid, 'warehouse_name': p.get('warehouse_name') or '',
            'base_unit': p.get('unit') or 'ud', 'theoretical_qty': float(p.get('stock_qty') or 0),
            'physical_qty': float(cnt.get('physical_qty') or 0), 'count_unit': (cnt.get('count_unit') or p.get('unit') or 'ud'),
            'is_checked': int(cnt.get('is_checked') or 0), 'note': cnt.get('note') or '',
            'audit_summary': _inventory_count_audit_label(cnt),
            'original_counted_by_name': cnt.get('original_counted_by_name') or '',
            'last_modified_by_name': cnt.get('last_modified_by_name') or '',
            'modified_count': int(cnt.get('modified_count') or 0),
            'unit_cost_snapshot': float(p.get('current_price') or 0),
            'production_group': pg or 'Otros',
            'yield_portions': float(p.get('yield_portions') or 0),
            'yield_final_qty': float(p.get('yield_final_qty') or 0),
            'yield_final_unit': (p.get('yield_final_unit') or p.get('unit') or ''),
        }
        for fam in fams:
            row2 = dict(base_row)
            row2['key'] = f"production:{int(p.get('item_id') or 0)}:{fam}:{whid}"
            row2['inventory_family_alias'] = fam
            prod_groups.setdefault(fam, []).append(row2)
    # Añadir recetas/subrecetas producibles como líneas esperadas sin stock, para que
    # Inventario pueda buscarlas y contarlas aunque todavía no tengan producción confirmada.
    try:
        existing_names = {str(r.get('item_name') or '').strip().lower() for rows in prod_groups.values() for r in rows}
        conn_rec = db(); cur_rec = conn_rec.cursor()
        rec_rows = cur_rec.execute("""SELECT id,name,COALESCE(category,'') category,COALESCE(subcategory,'') subcategory,
                                          COALESCE(yield_final_unit,'kg') yield_final_unit,
                                          COALESCE(yield_final_qty,0) yield_final_qty,
                                          COALESCE(yield_portions,0) yield_portions,
                                          COALESCE(is_subrecipe,0) is_subrecipe,
                                          COALESCE(produced_item_id,0) produced_item_id,
                                          COALESCE(is_producible,0) is_producible
                                     FROM recipes
                                    WHERE COALESCE(is_active,1)=1
                                    ORDER BY name LIMIT 500""").fetchall()
        conn_rec.close()
        for rr in rec_rows:
            nm = str(rr['name'] or '').strip()
            if not nm or nm.lower() in existing_names:
                continue
            if not _is_clean_production_candidate(nm, rr['category'] or '', rr['subcategory'] or '', rr['is_subrecipe'] if 'is_subrecipe' in rr.keys() else 0, rr['produced_item_id'] if 'produced_item_id' in rr.keys() else 0, rr['is_producible'] if 'is_producible' in rr.keys() else 0):
                continue
            fams = _production_inventory_families('', nm, rr['subcategory'] or '', rr['category'] or '')
            key, cnt = _inventory_counts_lookup(counts_map, 'production', int(rr['id'] or 0), fams, 0)
            base_row = {
                'key': key, 'item_id': int(rr['id'] or 0), 'item_name': nm,
                'warehouse_id': 0, 'warehouse_name': 'Receta / sin stock',
                'base_unit': (rr['yield_final_unit'] or 'kg'), 'theoretical_qty': 0.0,
                'physical_qty': float(cnt.get('physical_qty') or 0), 'count_unit': (cnt.get('count_unit') or rr['yield_final_unit'] or 'kg'),
                'is_checked': int(cnt.get('is_checked') or 0), 'note': cnt.get('note') or '',
                'audit_summary': _inventory_count_audit_label(cnt),
                'original_counted_by_name': cnt.get('original_counted_by_name') or '',
                'last_modified_by_name': cnt.get('last_modified_by_name') or '',
                'modified_count': int(cnt.get('modified_count') or 0),
                'unit_cost_snapshot': 0.0, 'production_group': (fams[0].title() if fams else 'Otros'), 'from_recipe_without_stock': 1,
                'yield_portions': float(rr['yield_portions'] or 0),
                'yield_final_qty': float(rr['yield_final_qty'] or 0),
                'yield_final_unit': (rr['yield_final_unit'] or 'kg'),
            }
            for fam in fams:
                row2 = dict(base_row)
                row2['key'] = f"production:{int(rr['id'] or 0)}:{fam}:0"
                row2['inventory_family_alias'] = fam
                prod_groups.setdefault(fam, []).append(row2)
            existing_names.add(nm.lower())
    except Exception as exc:
        print(f"INVENTORY_RECIPE_PROD_SKIP reason={exc}")

    for fam in prod_groups:
        prod_groups[fam].sort(key=lambda x: ((x['theoretical_qty']<=0), x['item_name'].lower()))

    conn = db(); cur = conn.cursor()
    free_rows_raw = cur.execute("SELECT * FROM inventory_counts WHERE session_id=? AND source_type='free' ORDER BY id DESC", (int(current_session.get('id') or 0),)).fetchall()
    conn.close()
    free_rows = []
    for r in free_rows_raw:
        d = {k:r[k] for k in r.keys()}
        fk = str(d.get('family_key') or '').strip().lower()
        block = 'materias_primas'; fam = 'otros'
        if ':' in fk:
            block, fam = fk.split(':', 1)
        elif fk in {'limpieza','libres'}:
            block, fam = ('limpieza','limpieza') if fk == 'limpieza' else ('materias_primas','otros')
        d['free_block'] = block
        d['free_family'] = fam or 'otros'
        d['audit_summary'] = _inventory_count_audit_label(d)
        free_rows.append(d)

    def _count_checked(rows):
        return sum(1 for r in rows if int(r.get('is_checked') or 0) == 1)

    raw_total = sum(len(v) for v in raw_groups.values())
    prod_total = sum(len(v) for v in prod_groups.values())
    free_total = len(free_rows)
    raw_checked = sum(_count_checked(v) for v in raw_groups.values())
    prod_checked = sum(_count_checked(v) for v in prod_groups.values())
    free_checked = _count_checked(free_rows)

    if inv_mode == 'materias_primas':
        current_rows = raw_groups.get(inv_family, [])
    elif inv_mode == 'producciones':
        current_rows = prod_groups.get(inv_family, [])
    elif inv_mode == 'limpieza':
        current_rows = raw_groups.get('limpieza', [])
    else:
        current_rows = free_rows

    inventory_filter_diagnostic = {
        'warehouse_id': int(selected_wh or 0),
        'warehouse_name': current_session.get('warehouse_name') or 'Todos',
        'mode': inv_mode,
        'family': inv_family,
        'visible': len(current_rows),
        'total_same_family_all_warehouses': int(all_raw_counts.get(inv_family, 0)) if inv_mode == 'materias_primas' else None,
        'note': '',
    }
    if inv_mode == 'materias_primas' and selected_wh and len(current_rows) < int(all_raw_counts.get(inv_family, 0) or 0):
        inventory_filter_diagnostic['note'] = f"El almacén activo filtra la vista: mostrando {len(current_rows)} de {int(all_raw_counts.get(inv_family, 0) or 0)} artículos de esta familia. Cambia a Todos o al almacén físico correcto si faltan líneas."
    if inv_mode == 'materias_primas' and selected_wh_name_norm == 'cocina' and inv_family in {'verduras','carnes','pescados','lacteos_huevos','congelados'}:
        inventory_filter_diagnostic['note'] = inventory_filter_diagnostic['note'] or 'Cocina solo muestra artículos ubicados en Cocina. Para frescos, revisa Cámara o Todos.'

    production_family_labels = {'frio':'Frío','caliente':'Caliente','postres':'Postres','salsas':'Salsas','guarniciones':'Guarniciones','bases':'Bases','masas':'Masas','pasteleria':'Pastelería','porcionados':'Porcionados','otros':'Otros'}
    production_index = []
    for _fam, _rows in prod_groups.items():
        for _r in _rows:
            production_index.append({
                'name': _r.get('item_name') or '',
                'family': _fam,
                'family_label': production_family_labels.get(_fam, _fam),
                'theoretical_qty': _r.get('theoretical_qty') or 0,
                'unit': _r.get('base_unit') or 'kg',
                'center_id': int(center_id or 0),
                'session_id': int(current_session.get('id') or 0),
            })

    summary = {
        'raw_total': raw_total,
        'raw_checked': raw_checked,
        'production_total': prod_total,
        'production_checked': prod_checked,
        'free_total': free_total,
        'free_checked': free_checked,
        'current_total': len(current_rows),
        'current_checked': _count_checked(current_rows),
        'current_pending': max(len(current_rows) - _count_checked(current_rows), 0),
        'limpieza_total': len(raw_groups.get('limpieza', [])),
        'limpieza_checked': _count_checked(raw_groups.get('limpieza', [])),
    }
    return {
        'inventory_session': current_session, 'inventory_mode': inv_mode, 'inventory_family': inv_family,
        'inventory_raw_groups': raw_groups, 'inventory_production_groups': prod_groups,
        'inventory_free_rows': free_rows, 'inventory_warehouse_options': warehouse_options,
        'inventory_summary': summary,
        'inventory_filter_diagnostic': inventory_filter_diagnostic,
        'inventory_production_index': production_index,
    }

# ==============================================================================
# RUTA PRINCIPAL — GET /
# ==============================================================================

ORDER_CATEGORY_OPTIONS = [
    ('', 'Auto'),
    ('verduras', 'Verduras'),
    ('pescados', 'Pescados'),
    ('carnes', 'Carnes'),
    ('huevos', 'Huevos'),
    ('lacteos', 'Lácteos'),
    ('preparaciones', 'Preparaciones'),
    ('limpieza', 'Limpieza'),
    ('congelados', 'Congelados'),
]

def _order_norm_text(val: str) -> str:
    import unicodedata
    s = unicodedata.normalize('NFKD', str(val or ''))
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    return s.strip().lower()

def _normalize_order_category(val: str) -> str:
    v = _order_norm_text(val or '')
    mapping = {
        'verduras': 'verduras', 'verdura': 'verduras',
        'pescados': 'pescados', 'pescado': 'pescados', 'marisco': 'pescados',
        'carnes': 'carnes', 'carne': 'carnes',
        'huevos': 'huevos', 'huevo': 'huevos',
        'lacteos': 'lacteos', 'lacteo': 'lacteos', 'lacteos/huevos': 'lacteos', 'preparaciones': 'preparaciones', 'preparacion': 'preparaciones', 'limpieza': 'limpieza', 'congelados': 'congelados'
    }
    return mapping.get(v, '')


def _order_item_category(name: str, stock_area: str = "", explicit: str = "") -> str:
    exp = _normalize_order_category(explicit)
    if exp:
        return exp
    area = normalize_stock_area(stock_area or '')
    if area == 'LIMPIEZA':
        return 'limpieza'
    return classify_order_fresh_group(name, explicit)

def _order_default_input_unit(base_unit: str) -> str:
    u = (base_unit or '').strip().lower()
    if u in {'manojo','manojos','atado','atados'}:
        return 'manojo'
    if u == 'ud':
        return 'ud'
    if u in {'g','kg','ml','l'}:
        # Política operativa System MAC: compra/stock de alimentos y líquidos por kg.
        return 'kg'
    return u or 'ud'


def _order_unit_choices(base_unit: str):
    default = _order_default_input_unit(base_unit)
    choices = [default]
    family = (base_unit or '').strip().lower()
    if family in {'manojo','manojos','atado','atados'}:
        extra = ['manojo','kg','g','ud']
    elif family in {'g','kg','ml','l'}:
        extra = ['kg','g','manojo','ud']
    elif family == 'ud':
        extra = ['ud','manojo','kg','g']
    else:
        extra = [family, 'kg','g','manojo','ud']
    for x in extra:
        if x and x not in choices:
            choices.append(x)
    return choices




def _safe_local_hostname() -> str:
    try:
        hn = subprocess.check_output(["scutil", "--get", "LocalHostName"], text=True).strip()
        if hn:
            return hn
    except Exception:
        pass
    try:
        return socket.gethostname().split('.')[0] or "Mac"
    except Exception:
        return "Mac"


def _detect_lan_ip_candidates() -> list[str]:
    """IPs probables del Mac accesibles desde móvil. Incluye Wi-Fi y hotspot iPhone."""
    candidates: list[str] = []
    def add(ip: str):
        ip = (ip or "").strip()
        if ip and not ip.startswith("127.") and ip not in candidates:
            candidates.append(ip)
    # 1) rutas conocidas macOS
    for iface in ("en0", "en1", "en2", "bridge100"):
        try:
            out = subprocess.check_output(["ipconfig", "getifaddr", iface], text=True, stderr=subprocess.DEVNULL).strip()
            add(out)
        except Exception:
            pass
    # 2) socket UDP: suele devolver la IP activa de salida
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.2)
        sock.connect(("8.8.8.8", 80))
        add(sock.getsockname()[0])
        sock.close()
    except Exception:
        pass
    # 3) fallback hostname
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            add(info[4][0])
    except Exception:
        pass
    # Prioriza redes privadas típicas: hotspot iPhone suele 172.20.10.x; Wi-Fi 192.168.x.x.
    def score(ip: str) -> int:
        if ip.startswith("172.20.10."):
            return 0
        if ip.startswith("192.168."):
            return 1
        if ip.startswith("10."):
            return 2
        if ip.startswith("172."):
            return 3
        return 9
    return sorted(candidates, key=score)


def _local_mobile_urls(request: Request) -> dict:
    """URLs beta local. Si existe HTTPS temporal público, se prioriza."""
    port = int(os.environ.get("FB_SERVER_PORT") or (request.url.port or 8000))
    public_https = (os.environ.get("FB_PUBLIC_HTTPS_URL") or "").strip().rstrip("/")
    env_lan = (os.environ.get("FB_LAN_URL") or "").strip().rstrip("/")
    env_bonjour = (os.environ.get("FB_BONJOUR_URL") or "").strip().rstrip("/")
    candidates = _detect_lan_ip_candidates()
    ip = candidates[0] if candidates else (request.url.hostname or "127.0.0.1")
    ip_base = env_lan or f"http://{ip}:{port}"
    host = _safe_local_hostname()
    local_base = env_bonjour or f"http://{host}.local:{port}"
    preferred = public_https or local_base or ip_base
    return {
        "preferred_base": preferred,
        "ip_base": ip_base,
        "local_base": local_base,
        "public_https": public_https,
        "lan_ips": candidates,
        "port": port,
    }


def _local_mobile_url(request: Request) -> str:
    return _local_mobile_urls(request)["preferred_base"]


def _mobile_app_url(base: str) -> str:
    return base.rstrip("/") + "/?page=inicio&center_id=0&mobile=1"


@app.get("/mobile_qr.png")
def mobile_qr(request: Request, kind: str = "preferred"):
    urls = _local_mobile_urls(request)
    base = urls.get("preferred_base") or urls.get("ip_base")
    if kind == "ip":
        base = urls.get("ip_base") or base
    elif kind in {"local", "bonjour"}:
        base = urls.get("local_base") or base
    elif kind == "https" and urls.get("public_https"):
        base = urls.get("public_https")
    url = _mobile_app_url(base)
    try:
        import qrcode
        img = qrcode.make(url)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        from fastapi.responses import Response
        return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control":"no-store, no-cache, max-age=0"})
    except Exception:
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(url, headers={"Cache-Control":"no-store"})


@app.get("/movil", response_class=HTMLResponse)
def mobile_access(request: Request):
    urls = _local_mobile_urls(request)
    preferred = _mobile_app_url(urls["preferred_base"])
    ip_url = _mobile_app_url(urls["ip_base"])
    local_url = _mobile_app_url(urls["local_base"])
    public_https = urls.get("public_https") or ""
    current_host = request.url.hostname or ""
    warning_127 = current_host in {"127.0.0.1", "localhost"}
    ips = ", ".join(urls.get("lan_ips") or []) or "no detectada"
    # Esta página NO debe cachearse: si cambia Wi‑Fi/hotspot, cambia IP.
    html = f"""<!doctype html><html lang='es'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><meta http-equiv='Cache-Control' content='no-store'><title>System MAC · Acceso móvil beta</title><style>
body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;background:#080d14;color:#f4f7fb;margin:0;padding:18px}}
.card{{max-width:980px;margin:0 auto;background:#111a27;border:1px solid rgba(255,255,255,.14);border-radius:24px;padding:22px;text-align:center;box-shadow:0 16px 40px rgba(0,0,0,.35)}}
.brand{{font-size:16px;color:#f2c45b;text-transform:uppercase;letter-spacing:.12em;font-weight:900}}h1{{margin:8px 0 8px;font-size:34px}}h2{{margin:10px 0 8px}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}}.box{{background:#0b1320;border:1px solid rgba(212,166,74,.28);border-radius:18px;padding:14px}}.qr{{width:230px;max-width:78vw;background:#fff;border-radius:16px;padding:12px;margin:10px auto;display:block}}.url{{font-size:18px;font-weight:900;color:#f2c45b;word-break:break-all;margin:10px 0}}.btn{{display:inline-flex;align-items:center;justify-content:center;border-radius:14px;background:#f2c45b;color:#111;text-decoration:none;font-weight:900;padding:12px 14px;margin:6px;border:0;cursor:pointer}}.btn.alt{{background:#1f2a3a;color:#f5d58a;border:1px solid rgba(212,166,74,.45)}}.muted{{color:#c1cad8;max-width:760px;margin:8px auto;line-height:1.45}}.warn{{background:#35220c;border:1px solid #a56c1f;border-radius:16px;padding:12px;margin:12px 0;color:#ffe0a3;text-align:left}}.ok{{background:#0b2a18;border-color:#2a8f55;color:#d9ffe8}}code{{background:#050a12;border:1px solid #334155;border-radius:8px;padding:2px 5px;color:#fff}}@media(max-width:760px){{.grid{{grid-template-columns:1fr}}h1{{font-size:28px}}}}
</style></head><body><div class='card'><div class='brand'>System MAC</div><h1>Acceso móvil beta</h1>
<p class='muted'>Esta pantalla es solo para beta local. En la versión final se entrará por dominio/PWA/login, sin QR.</p>
"""
    if warning_127:
        html += "<div class='warn'><b>Importante:</b> estás viendo esta pantalla desde el Mac en <code>127.0.0.1</code>. El móvil nunca debe abrir 127.0.0.1. Escanea uno de los QR de abajo o usa la URL IP/.local.</div>"
    html += f"<div class='warn'><b>Si el QR no abre:</b> en iPhone prueba primero el QR <b>.local</b>. Si no funciona, usa el QR <b>IP</b>. Si Safari bloquea HTTP por ‘Solo HTTPS’, usa Chrome o desactiva esa opción para esta beta. IPs detectadas: <code>{ips}</code>.</div>"
    if public_https:
        html += f"<div class='warn ok'><b>HTTPS temporal activo:</b> usa preferentemente este enlace seguro para probar audio real: <code>{preferred}</code></div>"
    html += f"""
<div class='grid'>
  <div class='box'><h2>Opción recomendada: .local</h2><img class='qr' src='/mobile_qr.png?kind=local&t={id(request)}' alt='QR .local'><div class='url'>{local_url}</div><a class='btn' href='{local_url}'>Abrir .local</a><button class='btn alt' onclick="copyText('{local_url}')">Copiar</button></div>
  <div class='box'><h2>Opción alternativa: IP</h2><img class='qr' src='/mobile_qr.png?kind=ip&t={id(request)}' alt='QR IP'><div class='url'>{ip_url}</div><a class='btn' href='{ip_url}'>Abrir IP</a><button class='btn alt' onclick="copyText('{ip_url}')">Copiar</button></div>
</div>
<div class='box' style='margin-top:14px'><h2>Diagnóstico</h2><p id='diag' class='muted'>Comprobando servidor…</p><button class='btn alt' onclick='checkStatus()'>Revisar conexión</button><button class='btn alt' onclick='clearCaches()'>Limpiar caché / recargar</button><a class='btn' href='/mobile-beta'>Abrir panel móvil completo</a></div>
<script>
async function copyText(txt){{try{{await navigator.clipboard.writeText(txt);alert('Enlace copiado');}}catch(e){{prompt('Copia este enlace', txt);}}}}
async function checkStatus(){{try{{let r=await fetch('/api/mobile-beta/status',{{cache:'no-store'}});let j=await r.json();document.getElementById('diag').textContent='Servidor OK · URL app: '+j.url+' · Cliente: '+(j.client_ip||'')+' · IP LAN: '+(j.lan_ip||'');}}catch(e){{document.getElementById('diag').textContent='No pude comprobar. Mantén Terminal abierta y confirma misma red/hotspot.';}}}}
async function clearCaches(){{try{{if('serviceWorker' in navigator){{let regs=await navigator.serviceWorker.getRegistrations(); for(const reg of regs) await reg.unregister();}} if(window.caches){{let keys=await caches.keys(); for(const k of keys) await caches.delete(k);}} alert('Caché limpiada.'); location.reload();}}catch(e){{location.reload();}}}}
checkStatus();
</script></div></body></html>"""
    return HTMLResponse(html, headers={"Cache-Control":"no-store, no-cache, max-age=0"})

@app.get("/direction/monthly/print", response_class=HTMLResponse)
def print_monthly_direction_report(request: Request, center_id: Optional[int] = None, year: Optional[int] = None, month: Optional[int] = None, day: Optional[int] = None, start: Optional[str] = None, end: Optional[str] = None):
    """Informe imprimible mensual de dirección.

    Lectura pura: no modifica stock, pedidos, recetas ni inventario. Usa inventarios cerrados
    y agrupa desviaciones por proveedor, rubro y local.
    """
    try:
        report = build_monthly_direction_dashboard(center_id=center_id or None, year=year, month=month, day=day, start_date=start, end_date=end)
    except Exception as exc:
        report = {
            "period": "", "has_data": False, "total_lines": 0, "total_loss": 0,
            "total_surplus": 0, "total_net": 0, "critical_count": 0,
            "missing_supplier_count": 0, "missing_rubro_count": 0,
            "by_supplier_alpha": [], "by_rubro_alpha": [], "by_center_risk": [],
            "top_losses": [], "top_surpluses": [], "critical_lines": [],
            "recommendations": [f"Informe mensual no disponible: {exc}"],
        }
    centers, *_ = get_dashboard_data(center_id)
    selected_center_name = "Todos los locales"
    for c in centers:
        try:
            if center_id and int(c["id"]) == int(center_id):
                selected_center_name = c["name"]
                break
        except Exception:
            pass
    return templates.TemplateResponse(request, "reports/monthly_direction_inventory.html", {
        "request": request,
        "report": report,
        "center_id": center_id or 0,
        "selected_center_name": selected_center_name,
        "fmt_price": fmt_price,
        "BUILD_ID": BUILD_ID,
    })


@app.get("/direction/suppliers/print", response_class=HTMLResponse)
def print_monthly_supplier_report(request: Request, center_id: Optional[int] = None, year: Optional[int] = None, month: Optional[int] = None):
    """Informe imprimible mensual de proveedores/precios y recetas afectadas. Lectura pura."""
    try:
        report = build_monthly_supplier_dashboard(center_id=center_id or None, year=year, month=month)
    except Exception as exc:
        report = {
            "period": "", "has_data": False, "events_count": 0, "increase_count": 0,
            "decrease_count": 0, "missing_comparison_count": 0, "total_estimated_impact": 0,
            "suppliers_alpha": [], "suppliers_by_risk": [], "top_increases": [],
            "top_impact": [], "affected_recipes": [], "missing_comparison": [],
            "recommendations": [f"Informe de proveedores no disponible: {exc}"],
        }
    centers, *_ = get_dashboard_data(center_id)
    selected_center_name = "Todos los locales"
    for c in centers:
        try:
            if center_id and int(c["id"]) == int(center_id):
                selected_center_name = c["name"]
                break
        except Exception:
            pass
    return templates.TemplateResponse(request, "reports/monthly_supplier_direction.html", {
        "request": request,
        "report": report,
        "center_id": center_id or 0,
        "selected_center_name": selected_center_name,
        "fmt_price": fmt_price,
        "BUILD_ID": BUILD_ID,
    })


@app.get("/direction/recipe-sales/print", response_class=HTMLResponse)
def print_monthly_recipe_sales_report(request: Request, center_id: Optional[int] = None, year: Optional[int] = None, month: Optional[int] = None):
    """Informe imprimible mensual de ventas de platos. Lectura pura y TPV-neutral."""
    try:
        report = build_monthly_recipe_sales_dashboard(center_id=center_id or None, year=year, month=month)
    except Exception as exc:
        report = {
            "period": "", "has_data": False, "source_ready": False,
            "total_qty": 0, "total_net_sales": 0, "total_food_cost": 0,
            "gross_margin_value": 0, "gross_margin_pct": 0,
            "top_by_units": [], "top_by_sales": [], "top_margin_risk": [],
            "unlinked_sales": [], "by_channel": [], "by_business_type": [],
            "recommendations": [f"Informe de ventas de platos no disponible: {exc}"],
            "optional_improvements": [],
        }
    centers, *_ = get_dashboard_data(center_id)
    selected_center_name = "Todos los locales"
    for c in centers:
        try:
            if center_id and int(c["id"]) == int(center_id):
                selected_center_name = c["name"]
                break
        except Exception:
            pass
    return templates.TemplateResponse(request, "reports/monthly_recipe_sales.html", {
        "request": request,
        "report": report,
        "center_id": center_id or 0,
        "selected_center_name": selected_center_name,
        "fmt_price": fmt_price,
        "BUILD_ID": BUILD_ID,
    })


@app.get("/direction/recipe-modifiers/print", response_class=HTMLResponse)
def print_monthly_recipe_modifiers_report(request: Request, center_id: Optional[int] = None, year: Optional[int] = None, month: Optional[int] = None):
    """Informe imprimible de modificadores TPV. Lectura pura; no mueve stock."""
    try:
        report = build_monthly_modifier_dashboard(center_id=center_id or None, year=year, month=month)
    except Exception as exc:
        report = {
            "period": "", "has_data": False, "total_modifier_qty": 0,
            "mapped_count": 0, "unmapped_count": 0, "no_stock_count": 0,
            "top_modifiers": [], "consumption_deltas": [], "unmapped_modifiers": [],
            "no_stock_modifiers": [],
            "recommendations": [f"Informe de modificadores no disponible: {exc}"],
        }
    centers, *_ = get_dashboard_data(center_id)
    selected_center_name = "Todos los locales"
    for c in centers:
        try:
            if center_id and int(c["id"]) == int(center_id):
                selected_center_name = c["name"]
                break
        except Exception:
            pass
    return templates.TemplateResponse(request, "reports/monthly_recipe_modifiers.html", {
        "request": request,
        "report": report,
        "center_id": center_id or 0,
        "selected_center_name": selected_center_name,
        "fmt_price": fmt_price,
        "BUILD_ID": BUILD_ID,
    })

@app.get("/", response_class=HTMLResponse)
def home(request: Request, center_id: Optional[int] = None):
    page = request.query_params.get("page", "inicio")
    stock_q = (request.query_params.get("stock_q") or "").strip()
    show_archived_productions = (request.query_params.get("show_archived_productions") or "0") == "1"
    show_archived_orders = (request.query_params.get("show_archived_orders") or "0") == "1"
    show_archived_receipts = (request.query_params.get("show_archived_receipts") or "0") == "1"
    stock_item_id_q = request.query_params.get("stock_item_id") or ""
    stock_wh_id_q = request.query_params.get("stock_wh_id") or ""

    # Performance timers for diagnosing slow cold-starts / long handlers
    total_start = time.time()
    perf = {}
    def _mark(name, t0):
        elapsed = time.time() - t0
        try:
            print(f"[perf-home] {name} {elapsed:.3f}s path={request.url.path}")
        except Exception:
            pass
        perf[name] = elapsed

    if page not in {"inicio", "finanzas", "operativa", "stock", "inventario", "recetas", "producciones", "pedidos", "albaranes", "laboratorio", "admin", "mermas", "mermas_control"}:
        page = "inicio"

    rid_q = request.query_params.get("rid") or ""
    q_recipe = (request.query_params.get("q_recipe") or "").strip()
    new_q = request.query_params.get("new") or ""
    pid_q = request.query_params.get("pid") or ""
    oid_q = request.query_params.get("oid") or ""
    aid_q = request.query_params.get("aid") or ""
    minmax_item_q = request.query_params.get("minmax_item") or ""
    minmax_center_q = request.query_params.get("minmax_center") or ""
    minmax_wh_q = request.query_params.get("minmax_wh") or ""

    if page == "recetas" and new_q == "1":
        rid_q = ""

    # Dashboard global (needed early for pedidos/inventario helpers)
    # Catálogo/Admin debe cargar liviano: no hacemos CROSS JOIN stock x almacén x artículo
    # ni cálculos operativos que esta página no necesita. Las tablas grandes se cargan por API.
    if page == "admin":
        t0 = time.time()
        conn_light = db(); cur_light = conn_light.cursor(); ensure_columns(cur_light)
        centers = cur_light.execute("SELECT * FROM centers ORDER BY id").fetchall()
        warehouses = cur_light.execute("SELECT w.id,w.name,w.center_id,c.name center_name FROM warehouses w JOIN centers c ON c.id=w.center_id ORDER BY c.id,w.id").fetchall()
        items = cur_light.execute("SELECT *, COALESCE(stock_area,'') stock_area FROM items ORDER BY name COLLATE NOCASE LIMIT 60").fetchall()
        recipes = cur_light.execute("SELECT id,name,category,subcategory,is_subrecipe,produced_item_id,is_producible FROM recipes WHERE is_active=1 ORDER BY id LIMIT 120").fetchall()
        conn_light.close()
        stocks = []
        summary = {"centers": len(centers), "positions": 0, "below_min": 0}
        _mark('get_dashboard_data_admin', t0)
    else:
        t0 = time.time()
        centers, warehouses, items, stocks, summary, recipes = get_dashboard_data(center_id)
        _mark('get_dashboard_data', t0)
    warehouses_json = [{k: w[k] for k in w.keys()} for w in warehouses]
    # Producciones limpias para Producciones/Pedidos: no platos finales, no fotos, no ingredientes sueltos.
    production_recipe_groups = {k: [] for k in ['frio','caliente','postres','salsas','guarniciones','bases','masas','pasteleria','porcionados','otros']}
    t0 = time.time()
    try:
        for _r in recipes:
            _d = {k: _r[k] for k in _r.keys()} if hasattr(_r, 'keys') else dict(_r)
            if not _is_clean_production_candidate(_d.get('name') or '', _d.get('category') or '', _d.get('subcategory') or '', _d.get('is_subrecipe') or 0, _d.get('produced_item_id') or 0, _d.get('is_producible') or 0):
                continue
            for _fam in _production_inventory_families('', _d.get('name') or '', _d.get('subcategory') or '', _d.get('category') or ''):
                production_recipe_groups.setdefault(_fam, []).append(_d)
        for _fam in production_recipe_groups:
            production_recipe_groups[_fam].sort(key=lambda x: (x.get('name') or '').lower())
    except Exception:
        pass
    _mark('production_recipe_groups', t0)
    items_json = [{k: i[k] for k in i.keys()} for i in items]
    for it in items_json:
        it['stock_area'] = normalize_stock_area(it.get('stock_area') or '')
        it['stock_area_label'] = stock_area_label(it.get('stock_area'))
        it['order_category'] = _normalize_order_category(it.get('order_category') or '')


    # --- Detalle de receta ---
    recipe_detail = None
    if page == "recetas" and not rid_q and q_recipe:
        connx = db(); curx = connx.cursor()
        q_like = f"%{q_recipe}%"
        rows = curx.execute(
            """
            SELECT id, name FROM recipes
            WHERE COALESCE(is_active,1)=1 AND upper(name) LIKE upper(?)
            ORDER BY
              CASE WHEN upper(trim(name)) = upper(trim(?)) THEN 0 ELSE 1 END,
              CASE WHEN upper(name) LIKE upper(?) THEN 0 ELSE 1 END,
              LENGTH(name) ASC,
              name ASC
            LIMIT 25
            """,
            (q_like, q_recipe, f"{q_recipe}%")
        ).fetchall()
        chosen_id = None
        for row in rows:
            rd = recipe_with_calc(curx, int(row["id"]))
            if rd and recipe_visible_in_center(rd, center_id):
                chosen_id = int(row["id"])
                recipe_detail = rd
                break
        connx.close()
        if chosen_id is not None:
            rid_q = str(chosen_id)
    if recipe_detail is None and rid_q.isdigit():
        connx = db(); curx = connx.cursor()
        recipe_detail = recipe_with_calc(curx, int(rid_q))
        connx.close()
        if recipe_detail and not recipe_visible_in_center(recipe_detail, center_id):
            recipe_detail = None

    # --- Detalle de producción ---
    production_detail = None
    if pid_q.isdigit():
        connx = db(); curx = connx.cursor()
        production_detail = get_production_detail(curx, pid_q)
        connx.close()

    # --- Pedidos: selección segura de borrador ---
    # v8_7_291: no se crea ningún pedido automáticamente al entrar, refrescar o borrar.
    # Nuevo pedido solo nace desde POST /order/new_form. Esto evita que Borrar borrador
    # parezca aumentar el historial creando otro borrador vacío.
    if page == "pedidos" and (center_id or 0) > 0:
        connx = db(); curx = connx.cursor()
        selected_oid: Optional[int] = None
        if oid_q.isdigit():
            row = curx.execute("SELECT id,center_id,status FROM orders WHERE id=?", (int(oid_q),)).fetchone()
            if row and int(row["center_id"]) == int(center_id):
                selected_oid = int(row["id"])
        oid_q = str(selected_oid) if selected_oid is not None else ""
        connx.close()

    # --- Detalle de pedido ---
    order_detail = None
    if oid_q.isdigit():
        connx = db(); curx = connx.cursor(); ensure_columns(curx)
        order_detail = order_with_lines(curx, int(oid_q))
        if order_detail and hasattr(order_detail, 'keys'):
            order_detail = {k: order_detail[k] for k in order_detail.keys()}
        if order_detail:
            if hasattr(order_detail.get('lines'), '__iter__'):
                order_detail['lines'] = [({k: ln[k] for k in ln.keys()} if hasattr(ln, 'keys') else dict(ln)) for ln in (order_detail.get('lines') or [])]
            try:
                prod_rows = curx.execute(
                    """
                    SELECT p.id production_id, p.note production_note, p.warehouse_id, pl.item_id,
                           SUM(pl.qty_base) qty_base
                      FROM productions p
                      JOIN production_lines pl ON pl.production_id=p.id
                     WHERE p.center_id=? AND UPPER(COALESCE(p.status,''))='DRAFT' AND UPPER(COALESCE(pl.line_type,''))='OUT'
                     GROUP BY p.id, p.note, p.warehouse_id, pl.item_id
                    """,
                    (int(order_detail.get('center_id') or 0),),
                ).fetchall()
                prod_map = {}
                for rr in prod_rows:
                    key = (int(rr['warehouse_id'] or 0), int(rr['item_id'] or 0))
                    note = str(rr['production_note'] or '').strip()
                    title = note.split(' + ')[0].strip() if note else ''
                    title = title or f"Producción #{int(rr['production_id'])}"
                    prod_map.setdefault(key, []).append({
                        'production_id': int(rr['production_id'] or 0),
                        'title': title,
                        'qty_base': float(rr['qty_base'] or 0.0),
                    })
            except Exception:
                prod_map = {}
            for ln in (order_detail.get('lines') or []):
                key = (int(ln.get('warehouse_id') or 0), int(ln.get('item_id') or 0))
                srcs = sorted(prod_map.get(key, []), key=lambda x: (x['title'].lower(), x['production_id']))
                ln['production_sources'] = srcs
                ln['production_sources_count'] = len(srcs)
                ln['production_required_qty'] = sum(float(x.get('qty_base') or 0.0) for x in srcs)
                try:
                    current_stock_qty = float(ln.get('current_stock_qty') or 0.0)
                except Exception:
                    current_stock_qty = 0.0
                try:
                    target_max_qty = float(ln.get('target_max_qty') or 0.0)
                except Exception:
                    target_max_qty = 0.0
                ln['replenish_to_max_qty'] = max(0.0, target_max_qty - current_stock_qty) if target_max_qty > 0 else 0.0
                ln['calculated_shortage_qty'] = max(0.0, float(ln.get('production_required_qty') or 0.0) - current_stock_qty)
                try:
                    qty_base = float(ln.get('qty_base') or 0.0)
                except Exception:
                    qty_base = 0.0
                shortage_qty = float(ln.get('calculated_shortage_qty') or 0.0)
                repl_qty = float(ln.get('replenish_to_max_qty') or 0.0)
                reason = 'Manual'
                reason_details = []
                if shortage_qty > 0:
                    reason_details.append('Producciones')
                if repl_qty > 0:
                    reason_details.append('Stock máximo')
                if shortage_qty > 0 and repl_qty > 0:
                    reason = 'Producciones' if shortage_qty >= repl_qty else 'Stock máximo'
                elif shortage_qty > 0:
                    reason = 'Producciones'
                elif repl_qty > 0:
                    reason = 'Stock máximo'
                ln['primary_driver_label'] = reason
                ln['driver_labels'] = reason_details
                ln['is_manual_driver'] = (reason == 'Manual')
                ln['matches_production_need'] = shortage_qty > 0 and abs(qty_base - shortage_qty) <= 0.0001
                ln['matches_target_max'] = repl_qty > 0 and abs(qty_base - repl_qty) <= 0.0001
                if reason == 'Producciones':
                    ln['driver_badge_class'] = 'prod'
                elif reason == 'Stock máximo':
                    ln['driver_badge_class'] = 'max'
                else:
                    ln['driver_badge_class'] = 'manual'
            lines = list(order_detail.get('lines') or [])
            summary = {
                'total_lines': len(lines),
                'checked_lines': sum(1 for ln in lines if int(ln.get('is_checked') or 0) == 1),
                'prod_lines': sum(1 for ln in lines if (ln.get('primary_driver_label') or '') == 'Producciones'),
                'max_lines': sum(1 for ln in lines if (ln.get('primary_driver_label') or '') == 'Stock máximo'),
                'manual_lines': sum(1 for ln in lines if (ln.get('primary_driver_label') or 'Manual') == 'Manual'),
            }
            order_detail['line_driver_summary'] = summary
            warehouse_rows = [{k: w[k] for k in w.keys()} if hasattr(w, 'keys') else dict(w) for w in warehouses]
            center_whs = [w for w in warehouse_rows if int(w.get('center_id') or 0) == int(order_detail.get('center_id') or 0)]
            def _first_wh_id(fragment: str):
                frag = _norm_warehouse_name(fragment)
                for w in center_whs:
                    if frag in _norm_warehouse_name(w.get('name') or ''):
                        return int(w.get('id') or 0)
                return int(center_whs[0].get('id') or 0) if center_whs else 0
            first_center_wh_id = int(center_whs[0].get('id') or 0) if center_whs else 0
            order_detail['warehouse_map'] = {
                'fresh': _first_wh_id('camara'),
                'frozen': _first_wh_id('congel') or _first_wh_id('camara'),
                'dry': _first_wh_id('economato'),
                'clean': _first_wh_id('economato'),
                'free': first_center_wh_id,
                'fallback': first_center_wh_id,
            }
            try:
                grouped = {'fresh': [], 'frozen': [], 'dry': [], 'clean': [], 'free': []}
                fresh_groups = {'verduras': [], 'pescados': [], 'carnes': [], 'huevos': [], 'lacteos': []}
                target_center_id = int(order_detail.get('center_id') or 0)
                item_rows = []
                try:
                    item_rows = curx.execute("SELECT id,name,unit,COALESCE(stock_area,'') stock_area, COALESCE(item_type,'INSUMO') item_type FROM items ORDER BY name COLLATE NOCASE").fetchall()
                except Exception:
                    item_rows = []
                for raw_it in item_rows:
                    try:
                        iid = int(raw_it['id'] or 0)
                        if iid <= 0:
                            continue
                        name = str(raw_it['name'] or '').strip()
                        if not name:
                            continue
                        if str(raw_it['item_type'] or 'INSUMO').strip().upper() == 'PREPARACION':
                            # Las preparaciones/subrecetas no se compran como insumo manual.
                            # Se gestionan desde Producciones.
                            continue
                        unit = str(raw_it['unit'] or 'ud').strip() or 'ud'
                        stock_area = normalize_stock_area(raw_it['stock_area'] or '')
                        pref_sid = 0
                        pref_name = ''
                        try:
                            pref_sid = _suggest_supplier_id(curx, target_center_id, iid) or 0
                            if pref_sid:
                                srow = curx.execute('SELECT name FROM suppliers WHERE id=?', (int(pref_sid),)).fetchone()
                                pref_name = str(srow['name'] or '') if srow else ''
                        except Exception:
                            pref_sid = 0
                            pref_name = ''
                        fresh_group = _order_item_category(name, stock_area, '')
                        block_key = infer_order_block(stock_area=stock_area, name=name, explicit_group=fresh_group)
                        row = {
                            'id': iid,
                            'name': name,
                            'unit': unit,
                            'stock_area': stock_area,
                            'inventory_raw_family': _inventory_raw_family(name, stock_area),
                            'category': fresh_group,
                            'fresh_group': fresh_group,
                            'preferred_supplier_id': int(pref_sid or 0),
                            'preferred_supplier_name': pref_name,
                            'default_input_unit': _order_default_input_unit(unit),
                            'unit_choices': _order_unit_choices(unit),
                        }
                        grouped.setdefault(block_key, []).append(row)
                        if block_key == 'fresh':
                            fresh_groups.setdefault(fresh_group, []).append(row)
                    except Exception:
                        continue
                for key in list(grouped.keys()):
                    grouped[key] = sorted(grouped[key], key=lambda x: (x.get('name') or '').lower())
                for key in list(fresh_groups.keys()):
                    fresh_groups[key] = sorted(fresh_groups[key], key=lambda x: (x.get('name') or '').lower())
                order_detail['manual_block_items'] = grouped
                order_detail['manual_fresh_groups'] = fresh_groups
                try:
                    prod_required_rows = curx.execute(
                        """
                        SELECT p.warehouse_id, w.name warehouse_name, pl.item_id,
                               i.name item_name, i.unit base_unit, COALESCE(i.stock_area,'') stock_area,
                               SUM(pl.qty_base) required_qty
                          FROM productions p
                          JOIN production_lines pl ON pl.production_id=p.id
                          JOIN items i ON i.id=pl.item_id
                          LEFT JOIN warehouses w ON w.id=p.warehouse_id
                         WHERE p.center_id=? AND UPPER(COALESCE(p.status,''))='DRAFT' AND UPPER(COALESCE(pl.line_type,''))='OUT'
                         GROUP BY p.warehouse_id, w.name, pl.item_id, i.name, i.unit, COALESCE(i.stock_area,'')
                         ORDER BY i.name COLLATE NOCASE
                        """,
                        (int(order_detail.get('center_id') or 0),),
                    ).fetchall()
                    prod_rows = []
                    if prod_required_rows:
                        wh_ids = sorted({int(r['warehouse_id'] or 0) for r in prod_required_rows if int(r['warehouse_id'] or 0) > 0})
                        item_ids = sorted({int(r['item_id'] or 0) for r in prod_required_rows if int(r['item_id'] or 0) > 0})
                        stock_map = {}
                        if wh_ids and item_ids:
                            wh_ph = ','.join(['?'] * len(wh_ids))
                            item_ph = ','.join(['?'] * len(item_ids))
                            stock_rows = curx.execute(
                                f"""
                                SELECT warehouse_id, item_id,
                                       COALESCE(SUM(CASE WHEN movement_type IN ('ENTRADA','IN') THEN qty
                                                         WHEN movement_type IN ('SALIDA','OUT') THEN -qty ELSE -qty END),0) stock_qty
                                  FROM movements
                                 WHERE center_id=? AND warehouse_id IN ({wh_ph}) AND item_id IN ({item_ph})
                                 GROUP BY warehouse_id, item_id
                                """,
                                tuple([int(order_detail.get('center_id') or 0)] + wh_ids + item_ids),
                            ).fetchall()
                            stock_map = {(int(r['warehouse_id']), int(r['item_id'])): float(r['stock_qty'] or 0.0) for r in stock_rows}
                        for rr in prod_required_rows:
                            wid = int(rr['warehouse_id'] or 0)
                            iid = int(rr['item_id'] or 0)
                            required_qty = float(rr['required_qty'] or 0.0)
                            stock_qty = float(stock_map.get((wid, iid), 0.0))
                            shortage_qty = max(0.0, required_qty - stock_qty)
                            pref_sid = _suggest_supplier_id(curx, int(order_detail.get('center_id') or 0), iid) or 0
                            pref_name = ''
                            if pref_sid:
                                srow = curx.execute('SELECT name FROM suppliers WHERE id=?', (int(pref_sid),)).fetchone()
                                pref_name = str(srow['name'] or '') if srow else ''
                            prod_rows.append({
                                'warehouse_id': wid,
                                'warehouse_name': str(rr['warehouse_name'] or ''),
                                'item_id': iid,
                                'name': str(rr['item_name'] or '').strip(),
                                'unit': str(rr['base_unit'] or 'ud').strip() or 'ud',
                                'stock_area': normalize_stock_area(rr['stock_area'] or ''),
                                'category': _order_item_category(str(rr['item_name'] or '').strip(), str(rr['stock_area'] or '').strip(), ''),
                                'required_qty': required_qty,
                                'stock_qty': stock_qty,
                                'shortage_qty': shortage_qty,
                                'preferred_supplier_id': int(pref_sid or 0),
                                'preferred_supplier_name': pref_name,
                            })
                    # Añadir producciones reales disponibles por rubro aunque no haya faltante abierto.
                    # Solo con produced_item_id válido para que puedan entrar en pedido como línea revisable.
                    try:
                        existing_prod_items = {(int(x.get('item_id') or 0), int(x.get('warehouse_id') or 0)) for x in prod_rows}
                        wh_prod = _order_preferred_warehouse_id(curx, int(order_detail.get('center_id') or 0), 'fresh') or first_center_wh_id or 0
                        rec_prod_rows = curx.execute("""
                            SELECT r.id recipe_id, r.name, COALESCE(r.category,'') category, COALESCE(r.subcategory,'') subcategory,
                                   COALESCE(r.produced_item_id,0) produced_item_id, COALESCE(r.is_subrecipe,0) is_subrecipe, COALESCE(r.is_producible,0) is_producible,
                                   i.name item_name, i.unit base_unit
                              FROM recipes r
                              JOIN items i ON i.id=COALESCE(r.produced_item_id,0)
                             WHERE COALESCE(r.is_active,1)=1 AND COALESCE(r.produced_item_id,0)>0
                             ORDER BY r.name COLLATE NOCASE
                        """).fetchall()
                        for rr in rec_prod_rows:
                            nm = str(rr['name'] or rr['item_name'] or '').strip()
                            if not _is_clean_production_candidate(nm, rr['category'] or '', rr['subcategory'] or '', rr['is_subrecipe'] or 0, rr['produced_item_id'] or 0, rr['is_producible'] or 0):
                                continue
                            iid = int(rr['produced_item_id'] or 0)
                            wid = int(wh_prod or 0)
                            if (iid, wid) in existing_prod_items or wid <= 0:
                                continue
                            fams = _production_inventory_families('', nm, rr['subcategory'] or '', rr['category'] or '')
                            pref_sid = _suggest_supplier_id(curx, int(order_detail.get('center_id') or 0), iid) or 0
                            pref_name = ''
                            if pref_sid:
                                srow = curx.execute('SELECT name FROM suppliers WHERE id=?', (int(pref_sid),)).fetchone()
                                pref_name = str(srow['name'] or '') if srow else ''
                            prod_rows.append({
                                'warehouse_id': wid, 'warehouse_name': 'Producciones', 'item_id': iid, 'name': nm,
                                'unit': str(rr['base_unit'] or 'ud').strip() or 'ud',
                                'stock_area': 'PREPARACIONES', 'category': fams[0] if fams else 'otros', 'prod_families': fams,
                                'required_qty': 0.0, 'stock_qty': 0.0, 'shortage_qty': 0.0,
                                'preferred_supplier_id': int(pref_sid or 0), 'preferred_supplier_name': pref_name, 'is_catalog_production': 1,
                            })
                            existing_prod_items.add((iid, wid))
                    except Exception:
                        pass
                    order_detail['manual_prod_rows'] = prod_rows
                except Exception:
                    order_detail['manual_prod_rows'] = []

            except Exception:
                grouped = {'fresh': [], 'frozen': [], 'dry': [], 'clean': [], 'free': []}
                fresh_groups = {'verduras': [], 'pescados': [], 'carnes': [], 'huevos': [], 'lacteos': []}
                try:
                    item_rows_fb = curx.execute("SELECT * FROM items ORDER BY name COLLATE NOCASE").fetchall()
                except Exception:
                    item_rows_fb = []
                for raw_it in item_rows_fb:
                    try:
                        it = {k: raw_it[k] for k in raw_it.keys()} if hasattr(raw_it, 'keys') else dict(raw_it)
                        iid = int(it.get('id') or 0)
                        if iid <= 0:
                            continue
                        name = str(it.get('name') or '').strip()
                        if not name:
                            continue
                        if str(it.get('item_type') or 'INSUMO').strip().upper() == 'PREPARACION':
                            continue
                        unit = str(it.get('unit') or 'ud').strip() or 'ud'
                        stock_area = normalize_stock_area(it.get('stock_area') or '')
                        explicit_category = str(it.get('order_category') or '').strip()
                        row = {
                            'id': iid,
                            'name': name,
                            'unit': unit,
                            'stock_area': stock_area,
                            'inventory_raw_family': _inventory_raw_family(name, stock_area),
                            'category': _order_item_category(name, stock_area, explicit_category),
                            'preferred_supplier_id': 0,
                            'preferred_supplier_name': '',
                            'default_input_unit': _order_default_input_unit(unit),
                            'unit_choices': _order_unit_choices(unit),
                        }
                        if stock_area == 'FRESCOS':
                            bk = 'fresh'
                        elif stock_area == 'CONGELADOS':
                            bk = 'frozen'
                        elif stock_area == 'SECOS':
                            bk = 'dry'
                        elif stock_area == 'LIMPIEZA':
                            bk = 'clean'
                        else:
                            bk = _manual_block_key({'stock_area': stock_area, 'name': name, 'order_category': explicit_category})
                        grouped.setdefault(bk, []).append(row)
                        if bk == 'fresh':
                            fresh_groups.setdefault(row['category'], []).append(row)
                    except Exception:
                        continue
                for key in list(grouped.keys()):
                    grouped[key] = sorted(grouped[key], key=lambda x: (x.get('name') or '').lower())
                for key in list(fresh_groups.keys()):
                    fresh_groups[key] = sorted(fresh_groups[key], key=lambda x: (x.get('name') or '').lower())
                order_detail['manual_block_items'] = grouped
                order_detail['manual_fresh_groups'] = fresh_groups
                order_detail['manual_prod_rows'] = []
        connx.close()

    # Opciones de proveedor por línea de pedido
    if order_detail and (order_detail.get("center_id") is not None):
        try:
            cx = db(); curx = cx.cursor()
            c_id = int(order_detail.get("center_id"))
            for ln in (order_detail.get("lines") or []):
                try:
                    it_id = int(ln.get("item_id"))
                except Exception:
                    it_id = None
                ln["supplier_options"] = _supplier_options_for_item(curx, c_id, it_id) if it_id else []
            cx.close()
        except Exception:
            pass

    # Pre-confirmación resumen por proveedor
    preconfirm_summary = None
    if page == "pedidos" and order_detail and (request.query_params.get("preconfirm") == "1"):
        buckets = {}
        for ln in (order_detail.get("lines") or []):
            sup = (ln.get("supplier_name") or "(Sin asignar)").strip() or "(Sin asignar)"
            b = buckets.setdefault(sup, {"supplier_name": sup, "lines": [], "total_qty_base": 0.0})
            b["lines"].append(ln)
            try:
                b["total_qty_base"] += float(ln.get("qty_base") or 0)
            except Exception:
                pass
        preconfirm_summary = sorted(buckets.values(),
                                     key=lambda x: (x["supplier_name"] == "(Sin asignar)", x["supplier_name"].lower()))

    # Min/max item
    minmax_item = None
    if minmax_item_q.isdigit():
        connx = db(); curx = connx.cursor(); ensure_columns(curx)
        row = curx.execute("SELECT id,name,unit,min_qty,max_qty FROM items WHERE id=?",
                           (int(minmax_item_q),)).fetchone()
        if row:
            minmax_item = {k: row[k] for k in row.keys()}
            if minmax_center_q.isdigit() and minmax_wh_q.isdigit():
                pref = curx.execute(
                    "SELECT min_qty,max_qty FROM item_location_prefs WHERE item_id=? AND center_id=? AND warehouse_id=?",
                    (int(minmax_item_q), int(minmax_center_q), int(minmax_wh_q))).fetchone()
                minmax_item["center_id"] = int(minmax_center_q)
                minmax_item["warehouse_id"] = int(minmax_wh_q)
                if pref:
                    minmax_item["min_qty"] = pref["min_qty"]
                    minmax_item["max_qty"] = pref["max_qty"]
                wh = curx.execute(
                    "SELECT w.name warehouse_name, c.name center_name FROM warehouses w JOIN centers c ON c.id=w.center_id WHERE w.id=?",
                    (int(minmax_wh_q),)).fetchone()
                if wh:
                    minmax_item["warehouse_name"] = wh["warehouse_name"]
                    minmax_item["center_name"] = wh["center_name"]
            # Blindaje: si min/max quedó guardado en gramos pero el artículo ya opera en kg, mostrar kg reales.
            minmax_item["min_qty"] = normalize_minmax_qty_for_base(minmax_item.get("min_qty"), minmax_item.get("unit"))
            minmax_item["max_qty"] = normalize_minmax_qty_for_base(minmax_item.get("max_qty"), minmax_item.get("unit"))
        connx.close()

    # Dashboard mensual de dirección: lectura económica por inventarios cerrados.
    direction_year_q = request.query_params.get("direction_year") or ""
    direction_month_q = request.query_params.get("direction_month") or ""
    direction_day_q = request.query_params.get("direction_day") or ""
    direction_start_q = (request.query_params.get("direction_start") or "").strip()
    direction_end_q = (request.query_params.get("direction_end") or "").strip()
    direction_view = "range" if (direction_start_q or direction_end_q) else "month"
    # Dashboard diario de negocio: ventas, coste teórico, compras y sugerencias de salida.
    try:
        daily_business = build_daily_business_dashboard(center_id=center_id or None, start_date=direction_start_q or None, end_date=direction_end_q or None)
    except Exception as _dbexc:
        print(f"DAILY_BUSINESS_SKIP reason={_dbexc}")
        daily_business = {
            "period": "", "has_data": False,
            "areas": [],
            "total": {"sales": 0, "theoretical_cost": 0, "food_cost_pct": 0, "gross_margin": 0, "gross_margin_pct": 0, "waste": 0, "purchases": 0},
            "suggestions": [], "alerts": [],
            "notes": ["Dashboard diario no disponible en esta carga."],
        }

    # Dashboard financiero ejecutivo: capital, EBITDA y rendimiento por local.
    def _finance_q(name: str, default: float = 0.0) -> float:
        try:
            return float(str(request.query_params.get(name) or default).replace(',', '.'))
        except Exception:
            return default
    try:
        executive_finance = build_executive_finance_dashboard(
            center_id=center_id or None,
            start_date=direction_start_q or None,
            end_date=direction_end_q or None,
            own_capital=_finance_q('own_capital', 0.0),
            financed_capital=_finance_q('financed_capital', 0.0),
            interest_rate=_finance_q('interest_rate', 0.05),
            labor_liability=_finance_q('labor_liability', 0.0),
            labor_cost_daily=_finance_q('labor_cost_daily', 0.0),
            fixed_opex_daily=_finance_q('fixed_opex_daily', 0.0),
            cash_available=_finance_q('cash_available', 0.0),
        )
    except Exception as _efexc:
        print(f"EXECUTIVE_FINANCE_SKIP reason={_efexc}")
        executive_finance = {
            'period': '', 'rows': [], 'ranked_by_roic': [], 'ranked_by_ebitda': [], 'ranked_by_net': [], 'risk_rows': [],
            'portfolio': {'sales':0,'gross_profit':0,'ebitda_daily':0,'net_result_daily':0,'roic_annualized_pct':0,'cash_need_30':0,'invested_capital':0,'prime_cost_pct':0,'cash_coverage_days':0},
            'assumptions': {'own_capital':0,'financed_capital':0,'interest_rate': 0.05,'labor_liability':0,'labor_cost_daily':0,'fixed_opex_daily':0,'cash_available':0},
            'ceo_kpis': {'quick': [], 'strategic': [], 'board': []},
            'portfolio_recommendation': 'Dashboard financiero ejecutivo no disponible en esta carga.',
            'notes': ['Dashboard financiero ejecutivo no disponible en esta carga.']
        }


    try:
        direction_year = int(direction_year_q) if direction_year_q else None
    except Exception:
        direction_year = None
    try:
        direction_month = int(direction_month_q) if direction_month_q else None
    except Exception:
        direction_month = None
    try:
        direction_day = int(direction_day_q) if direction_day_q else None
    except Exception:
        direction_day = None
    if direction_view != "day":
        direction_day = None
    try:
        direction_monthly = build_monthly_direction_dashboard(center_id=center_id or None, year=direction_year, month=direction_month, day=direction_day, start_date=direction_start_q or None, end_date=direction_end_q or None)
    except Exception as _dmexc:
        print(f"DIRECTION_MONTHLY_SKIP reason={_dmexc}")
        direction_monthly = {
            "period": "", "has_data": False, "total_lines": 0, "total_loss": 0,
            "total_surplus": 0, "total_net": 0, "critical_count": 0,
            "missing_supplier_count": 0, "missing_rubro_count": 0,
            "by_supplier_alpha": [], "by_rubro_alpha": [], "by_center_risk": [],
            "top_losses": [], "top_surpluses": [], "critical_lines": [],
            "recommendations": ["Dashboard mensual no disponible en esta carga."],
        }

    # Dashboard mensual proveedores/precios: lectura pura de albaranes y recetas afectadas.
    try:
        direction_suppliers = build_monthly_supplier_dashboard(center_id=center_id or None, year=direction_year, month=direction_month)
    except Exception as _dsexc:
        print(f"DIRECTION_SUPPLIERS_SKIP reason={_dsexc}")
        direction_suppliers = {
            "period": "", "has_data": False, "events_count": 0, "increase_count": 0,
            "decrease_count": 0, "missing_comparison_count": 0, "total_estimated_impact": 0,
            "suppliers_alpha": [], "suppliers_by_risk": [], "top_increases": [],
            "top_impact": [], "affected_recipes": [], "missing_comparison": [],
            "recommendations": ["Dashboard mensual de proveedores no disponible en esta carga."],
        }

    # Ranking mensual de ventas de platos: apartado separado, preparado para TPV normalizado.
    try:
        direction_recipe_sales = build_monthly_recipe_sales_dashboard(center_id=center_id or None, year=direction_year, month=direction_month)
    except Exception as _rsexc:
        print(f"DIRECTION_RECIPE_SALES_SKIP reason={_rsexc}")
        direction_recipe_sales = {
            "period": "", "has_data": False, "source_ready": False,
            "total_qty": 0, "total_net_sales": 0, "total_food_cost": 0,
            "gross_margin_value": 0, "gross_margin_pct": 0,
            "top_by_units": [], "top_by_sales": [], "top_margin_risk": [],
            "unlinked_sales": [], "by_channel": [], "by_business_type": [],
            "recommendations": ["Ranking de ventas no disponible en esta carga."],
            "optional_improvements": [],
        }
    try:
        direction_recipe_modifiers = build_monthly_modifier_dashboard(center_id=center_id or None, year=direction_year, month=direction_month)
    except Exception as exc:
        direction_recipe_modifiers = {
            "period": "", "has_data": False, "total_modifier_qty": 0,
            "mapped_count": 0, "unmapped_count": 0, "no_stock_count": 0,
            "top_modifiers": [], "consumption_deltas": [], "unmapped_modifiers": [],
            "no_stock_modifiers": [],
            "recommendations": [f"Modificadores TPV no disponibles: {exc}"],
        }

    # Dashboard global (already loaded above for pedidos helpers)
    import unicodedata
    def _norm_stock_search(v: str) -> str:
        s = unicodedata.normalize('NFKD', str(v or ''))
        s = ''.join(ch for ch in s if not unicodedata.combining(ch))
        return s.lower().strip()
    stock_q_norm = _norm_stock_search(stock_q)
    filtered_stocks = []
    for s in stocks:
        s['stock_area'] = normalize_stock_area(s.get('stock_area') or '')
        s['stock_area_label'] = stock_area_label(s.get('stock_area'))
        s['_search_norm'] = _norm_stock_search(s.get('item_name') or '')
        inferred_family = _inventory_raw_family(s.get('item_name') or '', s.get('stock_area') or '')
        s['inventory_raw_family'] = inferred_family
        has_activity = bool((s.get('last_move_at') or '').strip()) or float(s.get('stock_qty') or 0) != 0
        default_wh = _default_warehouse_name_for_stock_area(s.get('stock_area') or '')
        wh_name_norm = _norm_warehouse_name(s.get('warehouse_name') or '')
        default_norm = _norm_warehouse_name(default_wh or '')
        preferred_names = _preferred_warehouse_names_for_raw_family(inferred_family)
        keep = has_activity or not default_wh or wh_name_norm == default_norm
        if preferred_names and wh_name_norm in preferred_names:
            keep = True
        if keep:
            filtered_stocks.append(s)
    stocks = filtered_stocks
    stock_groups = {
        'fresh': _collapse_stock_rows_for_operational_view(stocks, {'verduras','carnes','pescados','lacteos_huevos'}),
        'frozen': _collapse_stock_rows_for_operational_view(stocks, {'congelados'}),
        'dry': _collapse_stock_rows_for_operational_view(stocks, {'secos'}),
        'cleaning': _collapse_stock_rows_for_operational_view(stocks, {'limpieza'}),
        'unclassified': _collapse_stock_rows_for_operational_view([s for s in stocks if s.get('stock_area') == 'SIN_CLASIFICACION']),
        'unlocated': _collapse_stock_rows_for_operational_view([s for s in stocks if not s.get('stock_area')]),
        'current_all': _collapse_stock_rows_for_operational_view(stocks),
    }
    stock_section = (request.query_params.get('stock_section') or 'fresh').strip().lower()
    if stock_section not in {'fresh', 'productions', 'frozen', 'dry', 'cleaning', 'unclassified', 'unlocated', 'current_all'}:
        stock_section = 'fresh'

    t0 = time.time()
    connps = db(); curps = connps.cursor()
    production_stocks = get_production_stocks(curps, center_id if center_id else None)
    connps.close()
    _mark('get_production_stocks', t0)

    t0 = time.time()
    inventory_ctx = _build_inventory_context(
        center_id=center_id or 0,
        warehouses=warehouses,
        stocks=stocks,
        production_stocks=production_stocks,
        request=request,
    )
    _mark('build_inventory_context', t0)

    item_search = (request.query_params.get("item_search") or "").strip()
    ql = item_search.lower()
    items_pick = [it for it in items_json if ql in (it.get("name") or "").lower()][:60] if ql else items_json[:60]

    # Proveedores y precios
    conn2 = db(); cur2 = conn2.cursor()
    t1 = time.time()
    suppliers = cur2.execute("SELECT * FROM suppliers ORDER BY name").fetchall()
    _mark('suppliers_query', t1)
    if page == "admin":
        # Se carga bajo demanda con /api/admin/supplier_prices_page.
        supplier_prices = []
    else:
        t2 = time.time()
        supplier_prices = cur2.execute(
            """SELECT sp.id,sp.supplier_id,sp.item_id,sp.center_id,sp.price_per_purchase,sp.purchase_unit,
                      sp.purchase_to_base_factor,sp.is_preferred,sp.updated_at,s.name supplier_name,i.name item_name
                 FROM supplier_item_prices sp
                 JOIN suppliers s ON s.id=sp.supplier_id
                 JOIN items i ON i.id=sp.item_id
                 ORDER BY s.name,i.name""").fetchall()
        _mark('supplier_prices_query', t2)
    t3 = time.time()
    suppliers_json = [{k: s[k] for k in s.keys()} for s in suppliers]
    supplier_prices_json = [{k: p[k] for k in p.keys()} for p in supplier_prices]
    users_rows = cur2.execute("SELECT id,name,role,center_id,is_active FROM users WHERE COALESCE(is_active,1)=1 ORDER BY CASE WHEN UPPER(TRIM(name))='ADMIN GENERAL' THEN 1 ELSE 0 END, name").fetchall()
    _mark('users_query', t3)
    users_json = [{k: u[k] for k in u.keys()} for u in users_rows]
    try:
        t4 = time.time()
        recipe_modifiers_admin = list_recipe_modifiers_admin(cur2)
        _mark('recipe_modifiers_admin', t4)
    except Exception as _pm_admin_exc:
        print(f"POS_MODIFIERS_ADMIN_SKIP reason={_pm_admin_exc}")
        recipe_modifiers_admin = {"modifiers": [], "maps": [], "recipes": [], "items": [], "actions": [], "types": []}
    conn2.close()

    # Producciones
    t0 = time.time()
    connp = db(); curp = connp.cursor()
    production_group_filter = (request.query_params.get("prod_group") or "").strip()
    productions_json = list_productions(
        curp,
        center_id=center_id,
        show_archived=show_archived_productions,
        production_group_filter=production_group_filter,
    )
    connp.close()
    _mark('list_productions', t0)

    # Pedidos
    t0 = time.time()
    conno = db(); curo = conno.cursor()
    order_status_clause = "o.status='ARCHIVED'" if show_archived_orders else "COALESCE(o.status,'') <> 'ARCHIVED'"
    if center_id:
        orders = curo.execute(
            f"""SELECT o.id,o.status,o.created_at,o.note,c.name center_name
                 FROM orders o JOIN centers c ON c.id=o.center_id
                WHERE o.center_id=? AND {order_status_clause} ORDER BY o.id DESC""",
            (center_id,)).fetchall()
    else:
        orders = curo.execute(
            f"""SELECT o.id,o.status,o.created_at,o.note,c.name center_name
                 FROM orders o JOIN centers c ON c.id=o.center_id
                WHERE {order_status_clause} ORDER BY o.id DESC""").fetchall()
    orders_json = [{k: r[k] for k in r.keys()} for r in orders]
    conno.close()
    _mark('orders_query', t0)

    # Mermas / Control de mermas
    waste_status_filter = (request.query_params.get("waste_status") or "").strip().upper()
    waste_days = int(request.query_params.get("waste_days") or 30) if str(request.query_params.get("waste_days") or "30").isdigit() else 30
    t0 = time.time()
    try:
        waste_records = list_waste_records(center_id=center_id or 0, status=waste_status_filter, limit=160)
        waste_control = waste_analytics(center_id=center_id or 0, days=waste_days)
    except Exception as _wexc:
        print(f"WASTE_CONTEXT_SKIP reason={_wexc}")
        waste_records = []
        waste_control = {"days": waste_days, "total_records": 0, "confirmed_records": 0, "pending_records": 0, "total_loss": 0, "potential_loss": 0, "avg_loss": 0, "by_reason": [], "by_responsible": [], "by_center": [], "by_family": [], "top_items": [], "recent": []}
    _mark('waste_context', t0)


    # Operativa rápida: colas compartidas de pedidos/producciones/mermas
    t0 = time.time()
    try:
        operational_queue = list_operational_queue(center_id=center_id or 0)
    except Exception as _oexc:
        print(f"OPERATIVA_CONTEXT_SKIP reason={_oexc}")
        operational_queue = {"ORDER": [], "PRODUCTION": [], "WASTE": []}
    _mark('operational_queue', t0)
    t1 = time.time()
    try:
        ai_status = get_ai_status()
    except Exception as _aiex:
        print(f"AI_STATUS_SKIP reason={_aiex}")
        ai_status = {"configured": False, "ai_mode": "local", "stt_mode": "local", "ai_model": "local", "stt_model": "local", "status_label": "LOCAL / SIN IA EXTERNA", "warning": "No se pudo leer estado IA."}
    _mark('ai_status', t1)

    # Albaranes
    t0 = time.time()
    connr = db(); curr = connr.cursor()
    try:
        cleanup_receipt_photos(curr, int(center_id) if center_id else None)
        connr.commit()
    except Exception:
        pass
    receipt_status_clause = "r.status='ARCHIVED'" if show_archived_receipts else "COALESCE(r.status,'') <> 'ARCHIVED'"
    if center_id:
        receipts = curr.execute(
            f"""SELECT r.id,r.status,r.created_at,r.doc_number,r.doc_date,r.note,
                      c.name center_name,w.name warehouse_name,s.name supplier_name
                 FROM receipts r JOIN centers c ON c.id=r.center_id
                 JOIN warehouses w ON w.id=r.warehouse_id JOIN suppliers s ON s.id=r.supplier_id
                WHERE r.center_id=? AND {receipt_status_clause} ORDER BY r.id DESC""",
            (int(center_id),)).fetchall()
    else:
        receipts = curr.execute(
            f"""SELECT r.id,r.status,r.created_at,r.doc_number,r.doc_date,r.note,
                      c.name center_name,w.name warehouse_name,s.name supplier_name
                 FROM receipts r JOIN centers c ON c.id=r.center_id
                 JOIN warehouses w ON w.id=r.warehouse_id JOIN suppliers s ON s.id=r.supplier_id
                WHERE {receipt_status_clause} ORDER BY r.id DESC""").fetchall()
    receipts_json = [{k: r[k] for k in r.keys()} for r in receipts]

    # Detalle de albarán
    receipt_detail = None
    auto_ocr_meta = None
    if aid_q.isdigit():
        rh = curr.execute(
            """SELECT r.*, c.name center_name, w.name warehouse_name, s.name supplier_name
                 FROM receipts r JOIN centers c ON c.id=r.center_id
                 JOIN warehouses w ON w.id=r.warehouse_id JOIN suppliers s ON s.id=r.supplier_id
                WHERE r.id=?""", (int(aid_q),)).fetchone()
        if rh:
            lines = curr.execute(
                """SELECT rl.*, i.name item_name, i.unit base_unit
                     FROM receipt_lines rl JOIN items i ON i.id=rl.item_id
                    WHERE rl.receipt_id=? ORDER BY rl.id""", (int(aid_q),)).fetchall()
            photos = curr.execute(
                "SELECT id,file_path,created_at FROM receipt_photos WHERE receipt_id=? ORDER BY id",
                (int(aid_q),)).fetchall()
            photo_dicts = [{k: p[k] for k in p.keys()} for p in photos]
            for _p in photo_dicts:
                try:
                    _abs = __import__("pathlib").Path(UPLOADS_DIR) / str(_p.get("file_path") or "")
                    _p["exists"] = _abs.exists()
                except Exception:
                    _p["exists"] = False
            ocr_run = curr.execute("SELECT * FROM receipt_ocr_runs WHERE receipt_id=? ORDER BY id DESC LIMIT 1",
                                   (int(aid_q),)).fetchone()
            ocr_lines = []
            if ocr_run:
                ocr_lines = curr.execute("SELECT * FROM receipt_ocr_lines WHERE ocr_run_id=? ORDER BY id",
                                         (int(ocr_run["id"]),)).fetchall()
            receipt_detail = {k: rh[k] for k in rh.keys()}
            receipt_detail["lines"] = [{k: l[k] for k in l.keys()} for l in lines]
            receipt_detail["photos"] = photo_dicts
            valid_photo_count = sum(1 for _p in photo_dicts if _p.get("exists"))
            receipt_detail["ocr"] = ({k: ocr_run[k] for k in ocr_run.keys()}
                                     if (ocr_run and valid_photo_count > 0) else None)
            receipt_detail["photo_missing"] = bool(photo_dicts) and valid_photo_count == 0
            if receipt_detail["ocr"]:
                receipt_detail["ocr"]["lines"] = [{k: l[k] for k in l.keys()} for l in ocr_lines]
                for _ol in receipt_detail["ocr"]["lines"]:
                    _raw = re.sub(r"\s+", " ", str(_ol.get("item_name_raw") or "").strip())
                    _matched = re.sub(r"\s+", " ", str(_ol.get("matched_item_name") or "").strip())
                    _display = (_matched or _raw or "").upper()
                    if _display:
                        try:
                            _display = _ocr_postfix_product_cleanup(_display)
                        except Exception:
                            pass
                    _ol["display_name"] = _display
    connr.close()
    _mark('receipts_context', t0)

    t0 = time.time()
    ctx = {
        "request": request,
        "page": page,
        "centers": [{k: c[k] for k in c.keys()} for c in centers],
        "centers_json": [{k: c[k] for k in c.keys()} for c in centers],
        "warehouses": warehouses_json,
        "items": items_json,
        "items_pick": items_pick,
        "item_search": item_search,
        "stocks": stocks,
        "production_stocks": production_stocks,
        "summary": summary,
        "recipes": recipes,
        "suppliers": suppliers_json,
        "supplier_prices": supplier_prices_json,
        "users": users_json,
        "recipe_modifiers_admin": recipe_modifiers_admin,
        "selected_center_id": center_id or 0,
        "build_id": BUILD_ID,
        "categories": list(CATEGORY_CODES.keys()),
        "subcategories": SUBCATEGORIES,
        "allergens_ue": [{"code": c, "icon": i, "name": n} for c, i, n in ALLERGENS_UE],
        "recipe_detail": recipe_detail,
        "productions": productions_json,
        "production_group_filter": production_group_filter,
        "production_detail": production_detail,
        "production_groups": production_groups(),
        "production_units": production_units(),
        "production_recipe_groups": production_recipe_groups,
        "orders": orders_json,
        "order_detail": order_detail,
        "receipts": receipts_json,
        "receipt_detail": receipt_detail,
        "auto_ocr_meta": auto_ocr_meta,
        "preconfirm_summary": preconfirm_summary,
        "minmax_item": minmax_item,
        "stock_q": stock_q,
        "stock_item_id_q": stock_item_id_q,
        "stock_wh_id_q": stock_wh_id_q,
        "show_archived_productions": show_archived_productions,
        "show_archived_orders": show_archived_orders,
        "show_archived_receipts": show_archived_receipts,
        "stock_groups": stock_groups,
        "stock_section": stock_section,
        "stock_area_options": STOCK_AREAS,
        "order_category_options": ORDER_CATEGORY_OPTIONS,
        "waste_records": waste_records,
        "waste_control": waste_control,
        "waste_reasons": WASTE_REASONS,
        "waste_status_filter": waste_status_filter,
        "waste_days": waste_days,
        "operational_queue": operational_queue,
        "ai_status": ai_status,
        "daily_business": daily_business,
        "executive_finance": executive_finance,
        "direction_monthly": direction_monthly,
        "direction_suppliers": direction_suppliers,
        "direction_recipe_sales": direction_recipe_sales,
        "direction_recipe_modifiers": direction_recipe_modifiers,
        "direction_year": direction_year,
        "direction_month": direction_month,
        "direction_day": direction_day,
        "direction_start": direction_start_q,
        "direction_end": direction_end_q,
        "direction_view": direction_view,
        **inventory_ctx,
    }
    # Force Jinja2 render synchronously to measure and include render time in perf
    t_render = time.time()
    try:
        rendered_html = templates.env.get_template("index.html").render(ctx)
        _mark('template_render', t_render)
    except Exception:
        try:
            rendered_html = templates.env.get_template("index.html").render(ctx)
        except Exception:
            rendered_html = ""
        _mark('template_render', t_render)
    from fastapi.responses import HTMLResponse as _HTMLResponse
    resp = _HTMLResponse(rendered_html)
    _mark('template_response_prep', t0)
    total_elapsed = time.time() - total_start
    try:
        summary_str = ' '.join([f"{k}:{v:.3f}s" for k, v in perf.items()])
        # Include DB connection metrics if available
        try:
            from app.core import _DB_METRICS
            m = _DB_METRICS.get()
            db_count = int(m.get('count', 0))
            db_time = float(m.get('time', 0.0))
            summary_str = f"db_conns:{db_count} db_connect_time:{db_time:.3f}s " + summary_str
            try:
                resp.headers["X-DB-Conn-Count"] = str(db_count)
                resp.headers["X-DB-Conn-Time"] = f"{db_time:.3f}s"
            except Exception:
                pass
        except Exception:
            pass
        print(f"[perf-home] total {total_elapsed:.3f}s path={request.url.path} breakdown={summary_str}")
        try:
            resp.headers["X-Perf-Breakdown"] = summary_str
        except Exception:
            pass
    except Exception:
        pass
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp
