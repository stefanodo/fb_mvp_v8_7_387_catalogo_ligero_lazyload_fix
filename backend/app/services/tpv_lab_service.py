from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Dict, List

from app.core import db, ensure_columns, _norm_text, get_unit_factor, get_table_columns_from_cursor, safe_insert_returning, db_truthy_sql


def _now() -> str:
    return datetime.utcnow().isoformat(timespec='seconds')


def _j(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        txt = str(value if value is not None else '').replace(',', '.').strip()
        if txt == '':
            return default
        return float(txt)
    except Exception:
        return default

def _format_preview_qty(value: Any, unit: str = '') -> str:
    try:
        v = float(value or 0.0)
    except Exception:
        return f"{value or 0} {unit}".strip()
    u = (unit or '').strip().lower()
    if abs(v) >= 100:
        txt = f"{v:.0f}"
    elif u in {'ud', 'unidad', 'unidades'}:
        txt = f"{v:.2f}".rstrip('0').rstrip('.')
    elif abs(v) >= 10:
        txt = f"{v:.1f}".rstrip('0').rstrip('.')
    else:
        txt = f"{v:.3f}".rstrip('0').rstrip('.')
    return f"{txt} {unit}".strip()


def _unique_lab_id(prefix: str) -> str:
    return f"{prefix}-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"


def ensure_tpv_lab_schema(cur) -> None:
    # Schema creation for TPV is now managed by backend/migrate.py.
    # This function is intentionally a no-op at runtime to avoid executing
    # DDL during app operation — migrations should be run as a separate step.
    return


def _default_source(cur) -> int:
    row = cur.execute("SELECT id FROM tpv_sources WHERE name='TPV LAB MANUAL' LIMIT 1").fetchone()
    if row:
        return int(row['id'])
    now = _now()
    sqlite_sql = "INSERT INTO tpv_sources(name,type,provider_name,api_mode,active,config_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)"
    pg_sql = sqlite_sql.replace('?', '%s')
    return safe_insert_returning(
        cur,
        sqlite_sql,
        ('TPV LAB MANUAL','manual','System MAC LAB','manual_test',1,'{}',now,now),
        pg_sql=pg_sql,
    ) or 0


def _normalize_name(value: str) -> str:
    try:
        return _norm_text(value or '').strip().lower()
    except Exception:
        return re.sub(r'\s+', ' ', (value or '').strip().lower())


def _find_mapping(cur, source_id: int, name: str, code: str = '') -> Dict[str, Any]:
    norm = _normalize_name(name)
    row = cur.execute('''SELECT * FROM tpv_product_mappings
                         WHERE active=1 AND tpv_source_id=?
                           AND lower(trim(product_name_raw))=lower(trim(?))
                         ORDER BY confidence DESC, id DESC LIMIT 1''', (source_id, name)).fetchone()
    if row:
        return {'recipe_id': row['matched_recipe_id'], 'item_id': row['matched_item_id'], 'confidence': float(row['confidence'] or 0), 'status': 'MAPPED_RULE'}
    active_clause = db_truthy_sql("is_active", cur)
    recipes = cur.execute(f"SELECT id,name FROM recipes WHERE {active_clause} ORDER BY name").fetchall()
    best = None
    for r in recipes:
        rn = _normalize_name(r['name'])
        score = 0
        if rn == norm:
            score = 98
        elif norm and (norm in rn or rn in norm):
            score = 82
        elif norm and all(tok in rn for tok in norm.split()[:3]):
            score = 70
        if score and (not best or score > best['confidence']):
            best = {'recipe_id': int(r['id']), 'item_id': None, 'confidence': score, 'status': 'AUTO_RECIPE'}
    items = cur.execute("SELECT id,name FROM items ORDER BY name").fetchall()
    for it in items:
        inn = _normalize_name(it['name'])
        score = 0
        if inn == norm:
            score = 95
        elif norm and (norm in inn or inn in norm):
            score = 78
        if score and (not best or score > best['confidence']):
            best = {'recipe_id': None, 'item_id': int(it['id']), 'confidence': score, 'status': 'AUTO_ITEM'}
    return best or {'recipe_id': None, 'item_id': None, 'confidence': 0, 'status': 'PENDING_MAPPING'}


def _interpret_modifier(text: str) -> Dict[str, Any]:
    raw = text or ''
    n = _normalize_name(raw)
    if not n:
        return {'name': '', 'type': 'nota_libre', 'action': 'sin_modificador', 'affects_stock': 'no', 'confidence': 0, 'review_status': 'ignorado'}
    rules = [
        (['sin pan'], 'quitar', 'restar pan de esta venta', 'pendiente', 72),
        (['sin tomate'], 'quitar', 'restar tomate de esta venta', 'pendiente', 72),
        (['extra queso', 'mas queso', 'más queso'], 'extra', 'sumar queso si hay regla de gramos', 'pendiente', 70),
        (['salsa aparte'], 'nota_libre', 'no afecta stock salvo regla específica', 'no', 45),
        (['poco hecho', 'muy hecho', 'al punto'], 'punto_coccion', 'no afecta stock', 'no', 80),
        (['sin guarnicion', 'sin guarnición'], 'quitar', 'restar guarnición base si está definida', 'pendiente', 58),
        (['patatas por ensalada'], 'sustitucion', 'restar patatas y sumar ensalada si hay regla', 'pendiente', 62),
        (['alergia', 'sin gluten', 'frutos secos'], 'nota_libre', 'alerta alimentaria: revisión obligatoria', 'no', 88),
        (['como siempre'], 'nota_libre', 'modificador ambiguo: revisión manual', 'pendiente', 20),
    ]
    for keys, typ, action, affects, conf in rules:
        if any(k in n for k in keys):
            return {'name': raw.strip(), 'type': typ, 'action': action, 'affects_stock': affects, 'confidence': conf, 'review_status': 'pendiente_revision' if affects == 'pendiente' or conf < 75 else 'automatico'}
    return {'name': raw.strip(), 'type': 'otro', 'action': 'modificador no enseñado: revisión manual', 'affects_stock': 'pendiente', 'confidence': 25, 'review_status': 'pendiente_revision'}


def _recipe_consumption_preview(cur, recipe_id: int, qty: float, consumption_mode: str = 'lote', fallback_yield_portions: float = 0.0) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    mode = (consumption_mode or 'lote').strip().lower()
    sale_qty = float(qty or 1)
    scale_factor = sale_qty
    portion_info = {'mode': mode, 'requested_qty': sale_qty, 'scale_factor': scale_factor}
    try:
        rec = cur.execute("SELECT id,name,COALESCE(yield_portions,0) yield_portions,COALESCE(yield_final_qty,0) yield_final_qty,COALESCE(yield_final_unit,'') yield_final_unit FROM recipes WHERE id=?", (int(recipe_id),)).fetchone()
        if rec and mode in {'racion', 'ración', 'porcion', 'porción', 'portion', 'serving'}:
            yp = float(rec['yield_portions'] or 0.0)
            if yp <= 0:
                try:
                    yp = float(fallback_yield_portions or 0.0)
                except Exception:
                    yp = 0.0
            if yp > 0:
                scale_factor = sale_qty / yp
                portion_info = {'mode': 'racion', 'requested_qty': sale_qty, 'yield_portions': yp, 'scale_factor': scale_factor, 'yield_source': 'receta' if float(rec['yield_portions'] or 0.0) > 0 else 'fallback_lab'}
            else:
                portion_info = {'mode': 'racion_sin_rendimiento', 'requested_qty': sale_qty, 'yield_portions': 0, 'scale_factor': sale_qty}
    except Exception:
        pass
    cols = get_table_columns_from_cursor(cur, "recipe_ingredients")
    qty_expr = "COALESCE(ri.qty_gross, ri.qty_net, 0)"
    unit_expr = "COALESCE(NULLIF(ri.input_unit,''), NULLIF(ri.unit,''), i.unit, '')"
    if 'qty_gross' not in cols and 'qty' in cols:
        qty_expr = "COALESCE(ri.qty,0)"
    elif 'qty_gross' not in cols:
        qty_expr = "COALESCE(ri.qty_net,0)"
    if 'input_unit' not in cols:
        unit_expr = "COALESCE(NULLIF(ri.unit,''), i.unit, '')"
    sql = f"""SELECT ri.item_id, {qty_expr} AS ingredient_qty, {unit_expr} AS ingredient_unit,
                    i.name item_name, COALESCE(i.unit,'') base_unit, COALESCE(i.current_price,0) current_price
             FROM recipe_ingredients ri JOIN items i ON i.id=ri.item_id
             WHERE ri.recipe_id=? ORDER BY ri.id"""
    ing = cur.execute(sql, (int(recipe_id),)).fetchall()
    for r in ing:
        recipe_qty = float(r['ingredient_qty'] or 0) * scale_factor
        ingredient_unit = r['ingredient_unit'] or r['base_unit'] or ''
        base_unit = r['base_unit'] or ingredient_unit
        factor = get_unit_factor(ingredient_unit, base_unit)
        qty_for_cost = recipe_qty * float(factor or 1.0)
        cost = qty_for_cost * float(r['current_price'] or 0)
        rows.append({'item_id': int(r['item_id'] or 0), 'item_name': r['item_name'], 'qty_theoretical': recipe_qty, 'unit': ingredient_unit, 'qty_display': _format_preview_qty(recipe_qty, ingredient_unit), 'qty_for_cost': qty_for_cost, 'cost_unit': base_unit, 'cost_amount': cost, 'source': 'recipe_base_preview', 'confidence': 90, 'review_status': 'preview', 'conversion_applied': f"{ingredient_unit}->{base_unit} x {factor}", 'portion_info': portion_info})
    return rows

def simulate_tpv_sale(payload: Dict[str, Any]) -> Dict[str, Any]:
    conn = db(); cur = conn.cursor(); ensure_tpv_lab_schema(cur)
    now = _now(); source_id = _default_source(cur)
    product_name = (payload.get('product_name') or payload.get('name') or '').strip() or 'VENTA TPV SIN NOMBRE'
    qty = _safe_float(payload.get('quantity'), 1.0) or 1.0
    unit_price = _safe_float(payload.get('unit_price'), 0.0)
    total = _safe_float(payload.get('total'), qty * unit_price)
    status = (payload.get('line_status') or payload.get('sale_status') or 'vendida').strip().lower()
    modifiers_raw = payload.get('modifiers') or ''
    if isinstance(modifiers_raw, str):
        modifiers = [m.strip() for m in re.split(r'[,;\n]+', modifiers_raw) if m.strip()]
    else:
        modifiers = [str(m).strip() for m in modifiers_raw if str(m).strip()]
    normalized = {
        'source': 'TPV LAB MANUAL',
        'external_sale_id': payload.get('external_sale_id') or _unique_lab_id('LAB'),
        'ticket_id': payload.get('external_ticket_id') or _unique_lab_id('TICKET-LAB'),
        'restaurant_id': int(payload.get('restaurant_id') or payload.get('center_id') or 0),
        'datetime': payload.get('sale_datetime') or now,
        'channel': payload.get('channel') or 'sala',
        'waiter': payload.get('waiter_name') or payload.get('responsible') or '',
        'table': payload.get('table_number') or '',
        'total': total,
        'lines': [{'external_line_id': payload.get('external_line_id') or '1', 'name': product_name, 'code': payload.get('product_code') or '', 'qty': qty, 'unit_price': unit_price, 'total': total, 'modifiers': modifiers, 'status': status}],
    }
    h = hashlib.sha256(_j(normalized).encode('utf-8')).hexdigest()
    duplicate = cur.execute('SELECT id FROM tpv_sales_raw WHERE hash_deduplication=?', (h,)).fetchone()
    if duplicate:
        conn.close()
        return {'ok': True, 'duplicate': True, 'message': 'Venta TPV duplicada detectada. No se vuelve a importar.', 'raw_id': int(duplicate['id']), 'normalized': normalized, 'alerts': ['Duplicado por hash.']}
    # Insert raw payload and obtain id in a DB-agnostic way
    sqlite_sql = 'INSERT INTO tpv_sales_raw(tpv_source_id,raw_payload_json,received_at,import_status,error_message,hash_deduplication,created_at) VALUES(?,?,?,?,?,?,?)'
    pg_sql = sqlite_sql.replace('?', '%s')
    raw_id = safe_insert_returning(
        cur,
        sqlite_sql,
        (source_id, _j(normalized), now, 'preview', '', h, now),
        pg_sql=pg_sql,
    ) or 0
    # Insert sale header and obtain id in a DB-agnostic way
    sqlite_sql = '''INSERT INTO tpv_sales(tpv_source_id,external_sale_id,external_ticket_id,restaurant_id,sale_datetime,business_date,shift,channel,table_number,waiter_name,total_amount,payment_method,sale_status,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'''
    pg_sql = sqlite_sql.replace('?', '%s')
    sale_id = safe_insert_returning(
        cur,
        sqlite_sql,
        (source_id, normalized['external_sale_id'], normalized['ticket_id'], normalized['restaurant_id'], normalized['datetime'], str(normalized['datetime'])[:10], payload.get('shift') or 'otro', normalized['channel'], normalized['table'], normalized['waiter'], total, payload.get('payment_method') or '', status, now, now),
        pg_sql=pg_sql,
    ) or 0
    mapping = _find_mapping(cur, source_id, product_name, payload.get('product_code') or '')
    mapping_status = mapping['status'] if mapping['confidence'] >= 80 else 'PENDING_MAPPING'
    # Insert sale line and obtain id in a DB-agnostic way
    sqlite_sql = '''INSERT INTO tpv_sale_lines(tpv_sale_id,external_line_id,product_name_raw,product_code_raw,matched_recipe_id,matched_item_id,quantity,unit_price,discount_amount,tax_rate,total_line_amount,line_status,mapping_status,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'''
    pg_sql = sqlite_sql.replace('?', '%s')
    line_id = safe_insert_returning(
        cur,
        sqlite_sql,
        (sale_id, '1', product_name, payload.get('product_code') or '', int(mapping.get('recipe_id') or 0), int(mapping.get('item_id') or 0), qty, unit_price, _safe_float(payload.get('discount_amount'), 0.0), _safe_float(payload.get('tax_rate'), 0.0), total, status, mapping_status, now, now),
        pg_sql=pg_sql,
    ) or 0
    interpreted_mods = []
    for m in modifiers:
        im = _interpret_modifier(m)
        interpreted_mods.append(im)
        cur.execute('''INSERT INTO tpv_modifiers(tpv_sale_line_id,modifier_text_raw,modifier_name,modifier_type,interpreted_action,affects_stock,linked_item_id,linked_recipe_id,qty_delta,unit,confidence,review_status,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (line_id, m, im['name'], im['type'], im['action'], im['affects_stock'], 0, 0, 0, '', im['confidence'], im['review_status'], now, now))
    consumption = []
    alerts = ['TPV LAB en modo PREVIEW: no conecta TPV real y no descuenta stock definitivo.']
    if status in {'anulada', 'devuelta', 'corregida'}:
        alerts.append('Línea anulada/devuelta/corregida: no se crea consumo normal. Queda en revisión.')
    elif mapping.get('recipe_id'):
        consumption = _recipe_consumption_preview(cur, int(mapping['recipe_id']), qty, payload.get('consumption_mode') or payload.get('quantity_mode') or 'lote', _safe_float(payload.get('fallback_yield_portions'), 0.0))
        if not consumption:
            alerts.append('Receta vinculada sin ingredientes suficientes para calcular consumo teórico.')
        for ev in consumption:
            cur.execute('''INSERT INTO tpv_consumption_events(tpv_sale_id,tpv_sale_line_id,recipe_id,item_id,production_id,qty_theoretical,unit,cost_amount,source,confidence,review_status,movement_id,created_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (sale_id, line_id, int(mapping.get('recipe_id') or 0), int(ev['item_id'] or 0), None, ev['qty_theoretical'], ev['unit'], ev['cost_amount'], ev['source'], ev['confidence'], 'preview', None, now))
    elif mapping.get('item_id'):
        alerts.append('Artículo vinculado directamente. Consumo teórico simple en PREVIEW.')
        consumption = [{'item_id': mapping['item_id'], 'item_name': product_name, 'qty_theoretical': qty, 'unit': 'ud', 'cost_amount': 0, 'source': 'direct_item', 'confidence': 75, 'review_status': 'preview'}]
    else:
        alerts.append('Producto TPV pendiente de mapeo a receta o artículo.')
    for im in interpreted_mods:
        if im.get('review_status') == 'pendiente_revision':
            alerts.append(f"Modificador en revisión: {im.get('name')}")
    conn.commit(); conn.close()
    return {'ok': True, 'duplicate': False, 'mode': 'PREVIEW', 'raw_id': raw_id, 'sale_id': sale_id, 'line_id': line_id, 'normalized': normalized, 'quantity_mode': payload.get('consumption_mode') or payload.get('quantity_mode') or 'lote', 'mapping': mapping, 'modifiers': interpreted_mods, 'consumption_preview': consumption, 'alerts': alerts, 'message': 'Venta TPV simulada. No toca stock definitivo.'}


def get_tpv_lab_summary(limit: int = 8) -> Dict[str, Any]:
    conn = db(); cur = conn.cursor(); ensure_tpv_lab_schema(cur)
    imports = cur.execute('''SELECT r.id,r.received_at,r.import_status,r.error_message,r.raw_payload_json
                             FROM tpv_sales_raw r ORDER BY r.id DESC LIMIT ?''', (int(limit),)).fetchall()
    pending_maps = cur.execute("SELECT COUNT(*) c FROM tpv_sale_lines WHERE COALESCE(mapping_status,'')='PENDING_MAPPING'").fetchone()
    pending_mods = cur.execute("SELECT COUNT(*) c FROM tpv_modifiers WHERE COALESCE(review_status,'')='pendiente_revision'").fetchone()
    preview_events = cur.execute("SELECT COUNT(*) c FROM tpv_consumption_events WHERE COALESCE(review_status,'')='preview'").fetchone()
    recent = []
    for r in imports:
        try:
            raw = json.loads(r['raw_payload_json'] or '{}')
            first = (raw.get('lines') or [{}])[0]
        except Exception:
            raw = {}; first = {}
        recent.append({'id': int(r['id']), 'received_at': r['received_at'], 'status': r['import_status'], 'ticket': raw.get('ticket_id',''), 'local': raw.get('restaurant_id',''), 'product': first.get('name',''), 'total': raw.get('total',0), 'error': r['error_message']})
    conn.close()
    return {'ok': True, 'imports': recent, 'pending_mappings': int((pending_maps or {'c': 0})['c'] or 0), 'pending_modifiers': int((pending_mods or {'c': 0})['c'] or 0), 'preview_events': int((preview_events or {'c': 0})['c'] or 0), 'sections': ['Importaciones TPV','Mapeo TPV','Modificadores','Consumo teórico PREVIEW']}


def recipe_component_check(recipe_id: int) -> Dict[str, Any]:
    conn = db(); cur = conn.cursor()
    try:
        ensure_tpv_lab_schema(cur)
        recipe = cur.execute('SELECT id,name,yield_final_qty,yield_final_unit FROM recipes WHERE id=?', (int(recipe_id),)).fetchone()
        if not recipe:
            return {'ok': False, 'message': 'Receta no encontrada.'}
        components = _recipe_consumption_preview(cur, int(recipe_id), 1.0, 'racion', 10.0)
        missing = []
        if not components:
            missing.append('Receta sin ingredientes vinculados a artículos de catálogo.')
        for c in components:
            if float(c.get('cost_amount') or 0) <= 0:
                missing.append(f"Sin coste o coste cero: {c.get('item_name') or 'ingrediente'}")
        return {'ok': True, 'mode': 'PREVIEW', 'message': 'Componentes revisados. Cálculo teórico; no toca stock.', 'recipe': {'id': int(recipe['id']), 'name': recipe['name'], 'yield_final_qty': recipe['yield_final_qty'], 'yield_final_unit': recipe['yield_final_unit']}, 'consumption_preview': components, 'missing': missing, 'ready_for_preview': len(missing) == 0, 'alerts': missing}
    except Exception as exc:
        return {'ok': False, 'mode': 'PREVIEW', 'message': f'Error revisando receta: {exc}', 'alerts': ['No se tocó stock definitivo.']}
    finally:
        conn.close()
