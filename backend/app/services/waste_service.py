from __future__ import annotations

import os
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from app.core import db, ensure_columns, UPLOADS_DIR, normalize_stock_area, stock_area_label, get_table_columns_from_cursor, safe_insert_returning, db_truthy_sql
from app.services.units_service import to_base_qty

WASTE_REASONS = [
    'Mal estado', 'Caducado', 'Rotura', 'Error de producción', 'Quemado',
    'Sobrante no reutilizable', 'Contaminación cruzada', 'Devolución interna',
    'Prueba / test', 'Otro'
]

WASTE_STATUSES = {'DRAFT', 'REVIEW', 'CONFIRMED', 'CANCELLED'}
WASTE_ITEM_TYPES = {'article', 'production', 'recipe', 'subrecipe', 'unknown'}


def norm_text(value: str) -> str:
    txt = str(value or '').strip().lower()
    txt = unicodedata.normalize('NFKD', txt)
    txt = ''.join(ch for ch in txt if not unicodedata.combining(ch))
    txt = re.sub(r'[^a-z0-9ñ]+', ' ', txt)
    return re.sub(r'\s+', ' ', txt).strip()


def ensure_waste_schema(cur) -> None:
    # Schema creation for waste_records is managed by backend/migrate.py.
    # Avoid executing DDL at runtime; migrations should be run as a separate step.
    return



def _waste_preclean_voice(text: str) -> str:
    t = str(text or '')
    t = re.sub(r'\b(?:un|uno|una)?\s*kilo\s+y\s+medio\b', ' 1.5 kg', t, flags=re.I)
    t = re.sub(r'\b(?:un|uno|una)?\s*litro\s+y\s+medio\b', ' 1.5 l', t, flags=re.I)
    # Correcciones conservadoras de dictado móvil: no inventa, solo normaliza errores frecuentes.
    repl = {
        'mima': 'merma', 'mimar': 'merma', 'merna': 'merma',
        'so pedro': 'soy pedro', 'san pedro': 'soy pedro', 'saint pedro': 'soy pedro',
        'tomatoes': 'tomates', 'tomato': 'tomate',
        'pescado roca': 'pescado de roca', 'pescao roca': 'pescado de roca',
    }
    low = t.lower()
    for a,b in repl.items():
        low = re.sub(r'\b'+re.escape(a)+r'\b', b, low, flags=re.I)
    return low

def _row_to_dict(row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()} if row and hasattr(row, 'keys') else dict(row or {})


def default_warehouse_id(cur, center_id: int, item_type: str = 'article') -> int:
    center_id = int(center_id or 0)
    if center_id <= 0:
        row = cur.execute('SELECT id FROM warehouses ORDER BY id LIMIT 1').fetchone()
        return int(row['id']) if row else 0
    preferences = ['cocina'] if item_type in {'production', 'recipe', 'subrecipe'} else ['camara', 'cámara', 'cocina']
    rows = cur.execute('SELECT id,name FROM warehouses WHERE center_id=? ORDER BY id', (center_id,)).fetchall()
    picked = int(rows[0]['id']) if rows else 0
    for pref in preferences:
        for r in rows:
            if pref in norm_text(r['name'] or ''):
                return int(r['id'])
    return picked


def _candidate_score(query_norm: str, name_norm: str) -> int:
    if not query_norm or not name_norm:
        return 0
    if query_norm == name_norm:
        return 100
    qwords_all = query_norm.split()
    nwords_all = name_norm.split()
    # No aceptar nombres muy cortos como coincidencia parcial: evita SAL dentro de SALSA.
    if query_norm in name_norm and len(query_norm) >= 4:
        return 85
    if name_norm in query_norm and len(name_norm) >= 4 and any(name_norm == w or name_norm in w for w in qwords_all):
        return 85
    qwords = [w for w in qwords_all if len(w) >= 3]
    nwords = set(nwords_all)
    hits = sum(1 for w in qwords if w in nwords or any(len(w) >= 4 and w in nw for nw in nwords))
    return int((hits / max(1, len(qwords))) * 70)


def match_item_or_recipe(cur, text: str) -> dict[str, Any]:
    q = norm_text(text)
    best = {'item_type': 'unknown', 'article_id': 0, 'recipe_id': 0, 'name': '', 'unit': 'ud', 'current_price': 0.0, 'confidence': 0.0}
    if not q:
        return best
    rows = cur.execute('SELECT id,name,unit,current_price,stock_area FROM items ORDER BY LOWER(name)').fetchall()
    for r in rows:
        score = _candidate_score(q, norm_text(r['name'] or ''))
        if score > float(best['confidence'] or 0):
            best = {
                'item_type': 'article', 'article_id': int(r['id']), 'recipe_id': 0,
                'name': r['name'] or '', 'unit': r['unit'] or 'ud',
                'current_price': float(r['current_price'] or 0), 'confidence': float(score),
            }
    active_clause = db_truthy_sql('is_active', cur)
    recipes = cur.execute(f'SELECT id,name,is_subrecipe FROM recipes WHERE {active_clause} ORDER BY LOWER(name)').fetchall()
    for r in recipes:
        score = _candidate_score(q, norm_text(r['name'] or ''))
        if score > float(best['confidence'] or 0):
            # Si hay artículo con el mismo nombre de receta producida, se impactará el artículo producido.
            item = cur.execute('SELECT id,unit,current_price FROM items WHERE lower(trim(name))=lower(trim(?)) ORDER BY id LIMIT 1', (r['name'] or '',)).fetchone()
            best = {
                'item_type': 'subrecipe' if int(r['is_subrecipe'] or 0) else 'recipe',
                'article_id': int(item['id']) if item else 0,
                'recipe_id': int(r['id']), 'name': r['name'] or '',
                'unit': (item['unit'] if item else 'ud'),
                'current_price': float(item['current_price'] or 0) if item else 0.0,
                'confidence': float(score),
            }
    return best


def parse_voice_text(cur, text: str) -> dict[str, Any]:
    raw = text or ''
    cleaned_raw = _waste_preclean_voice(raw)
    # Motor IA/operativa como primera capa: entiende cantidad + producto + intención y resuelve contra candidatos reales.
    try:
        from app.services.operational_quick_service import interpret_operational_command
        op = interpret_operational_command(cleaned_raw or raw, 'WASTE')
        its = op.get('items') or []
        if its:
            it = its[0]
            matched_kind = str(it.get('matched_kind') or '')
            matched_id = int(it.get('matched_id') or 0)
            item_type = 'article' if matched_kind == 'items' else ('recipe' if matched_kind == 'recipes' else 'unknown')
            article_id = matched_id if matched_kind == 'items' else 0
            recipe_id = matched_id if matched_kind == 'recipes' else 0
            # Si la receta tiene artículo producido con el mismo nombre, vincular también artículo para poder impactar stock de elaborado.
            if recipe_id and not article_id:
                rr = cur.execute('SELECT name,is_subrecipe FROM recipes WHERE id=?', (recipe_id,)).fetchone()
                if rr:
                    item_type = 'subrecipe' if int(rr['is_subrecipe'] or 0) else 'recipe'
                    art = cur.execute('SELECT id,unit,current_price FROM items WHERE lower(trim(name))=lower(trim(?)) ORDER BY id LIMIT 1', (rr['name'] or '',)).fetchone()
                    if art:
                        article_id = int(art['id'])
            conf = float(op.get('confidence') or 0) * 100 if float(op.get('confidence') or 0) <= 1 else float(op.get('confidence') or 0)
            return {
                'item_type': item_type, 'article_id': article_id, 'recipe_id': recipe_id,
                'name': str(it.get('name') or it.get('raw_name') or '').strip().upper(),
                'unit': str(it.get('unit') or 'ud'), 'current_price': 0.0, 'confidence': conf,
                'qty': float(it.get('qty') or 0), 'reason': op.get('reason') or '',
                'responsible_name': op.get('responsible') or '', 'item_text': str(it.get('raw_name') or it.get('name') or '').strip(),
            }
    except Exception:
        pass
    n = norm_text(cleaned_raw or raw)
    # Normalización ligera de cantidades habladas frecuentes.
    word_nums = {'un': '1', 'una': '1', 'uno': '1', 'dos': '2', 'tres': '3', 'cuatro': '4', 'cinco': '5', 'seis': '6', 'siete': '7', 'ocho': '8', 'nueve': '9', 'diez': '10', 'once': '11', 'doce': '12'}
    for w, num in word_nums.items():
        n = re.sub(rf'\b{w}\b(?=\s*(kg|kilo|kilos|kilogramo|kilogramos|g|gr|gramo|gramos|ud|uds|unidad|unidades|racion|raciones|porcion|porciones|l|litro|litros))', num, n)
    qty = 0.0
    unit = ''
    qty_patterns = [
        r'(\d+(?:[\.,]\d+)?)\s*(kg|kilo|kilos|kilogramo|kilogramos|g|gr|gramo|gramos|ud|uds|unidad|unidades|racion|raciones|porcion|porciones|l|litro|litros)',
        r'(medio|media)\s*(kg|kilo|kilos|litro|litros)',
        r'(\d+(?:[\.,]\d+)?)\s+(huevo|huevos)',
    ]
    for pat in qty_patterns:
        m = re.search(pat, n)
        if m:
            if m.group(1) in {'medio', 'media'}:
                qty = 0.5
            else:
                qty = float(m.group(1).replace(',', '.'))
            unit_raw = m.group(2)
            if unit_raw in {'huevo','huevos'}:
                unit_raw = 'ud'
            unit_map = {
                'kilo': 'kg', 'kilos': 'kg', 'kilogramo': 'kg', 'kilogramos': 'kg',
                'gr': 'g', 'gramo': 'g', 'gramos': 'g',
                'uds': 'ud', 'unidad': 'ud', 'unidades': 'ud',
                'racion': 'racion', 'raciones': 'racion', 'porcion': 'racion', 'porciones': 'racion',
                'litro': 'l', 'litros': 'l'
            }
            unit = unit_map.get(unit_raw, unit_raw)
            break
    reason = ''
    for r in WASTE_REASONS:
        rn = norm_text(r)
        if rn and rn in n:
            reason = r
            break
    if not reason:
        if 'mal estado' in n or 'podrid' in n or 'pasad' in n:
            reason = 'Mal estado'
        elif 'caduc' in n:
            reason = 'Caducado'
        elif 'rota' in n or 'roto' in n or 'rotura' in n:
            reason = 'Rotura'
        elif 'quemad' in n:
            reason = 'Quemado'
        elif 'sobrant' in n:
            reason = 'Sobrante no reutilizable'
    responsible = ''
    m_resp = re.search(r'\b(?:soy|responsable|registrado por|lo registra|registra)\s+([a-zñáéíóú]+(?:\s+[a-zñáéíóú]+){0,2})', cleaned_raw or raw, re.I)
    if m_resp:
        responsible = m_resp.group(1).strip()
    # Quitar palabras operativas y cantidades para mejorar el matching.
    item_text = n
    item_text = re.sub(r'\b(hay|merma|apunta|apuntar|registrar|registro|de|del|por|para|porque|soy|responsable|registrado|registra|lo|la|el|una|un)\b', ' ', item_text)
    item_text = re.sub(r'\d+(?:[\.,]\d+)?\s*(kg|kilo|kilos|kilogramo|kilogramos|g|gr|gramo|gramos|ud|uds|unidad|unidades|racion|raciones|porcion|porciones|l|litro|litros)', ' ', item_text)
    for r in WASTE_REASONS:
        item_text = item_text.replace(norm_text(r), ' ')
    if responsible:
        item_text = item_text.replace(norm_text(responsible), ' ')
    # Evitar que cantidades residuales o palabras demasiado cortas contaminen el matching.
    item_text = re.sub(r'\b\d+(?:[\.,]\d+)?\b', ' ', item_text)
    item_text = ' '.join(w for w in re.sub(r'\s+', ' ', item_text).strip().split() if len(w) > 1)
    match = match_item_or_recipe(cur, item_text or raw)
    parsed = dict(match)
    parsed.update({
        'qty': qty, 'unit': unit or match.get('unit') or 'ud', 'reason': reason,
        'responsible_name': responsible, 'item_text': item_text,
    })
    return parsed


def _compute_base_and_cost(cur, article_id: int, qty: float, unit: str) -> tuple[float, str, float, float]:
    article_id = int(article_id or 0)
    qty = float(qty or 0)
    if article_id <= 0 or qty <= 0:
        return 0.0, unit or '', 0.0, 0.0
    item = cur.execute('SELECT unit,current_price FROM items WHERE id=?', (article_id,)).fetchone()
    if not item:
        return 0.0, unit or '', 0.0, 0.0
    base_unit = item['unit'] or unit or 'ud'
    qty_base = to_base_qty(qty, unit or base_unit, base_unit)
    if qty_base <= 0:
        qty_base = qty if (unit or base_unit) == base_unit else 0.0
    unit_cost = float(item['current_price'] or 0)
    total_cost = max(0.0, float(qty_base or 0) * unit_cost)
    return float(qty_base or 0), base_unit, unit_cost, total_cost


def create_waste_record(*, center_id: int, warehouse_id: int = 0, responsible_user_id: int = 0,
                        responsible_name: str = '', source_type: str = 'manual', item_type: str = 'unknown',
                        article_id: int = 0, recipe_id: int = 0, item_name_detected: str = '', qty: float = 0,
                        unit: str = 'ud', reason: str = '', notes: str = '', photo_path: str = '',
                        voice_text_raw: str = '', image_text_raw: str = '', confidence: float = 0,
                        status: str = 'REVIEW') -> int:
    conn = db(); cur = conn.cursor(); ensure_waste_schema(cur)
    item_type = item_type if item_type in WASTE_ITEM_TYPES else 'unknown'
    status = status if status in WASTE_STATUSES else 'REVIEW'
    if not warehouse_id:
        warehouse_id = default_warehouse_id(cur, int(center_id or 0), item_type)
    if article_id and not item_name_detected:
        row = cur.execute('SELECT name FROM items WHERE id=?', (int(article_id),)).fetchone()
        item_name_detected = row['name'] if row else ''
    qty_base, base_unit, unit_cost, total_cost = _compute_base_and_cost(cur, int(article_id or 0), float(qty or 0), unit or 'ud')
    if float(confidence or 0) < 80 or int(article_id or 0) <= 0 or float(qty or 0) <= 0:
        status = 'REVIEW'
        # Prefer RETURNING on Postgres for the new waste record id
        sqlite_sql = '''INSERT INTO waste_records(center_id,warehouse_id,responsible_user_id,responsible_name,source_type,item_type,
                article_id,recipe_id,item_name_detected,qty,unit,qty_base,base_unit,reason,notes,photo_path,
                voice_text_raw,image_text_raw,confidence,status,unit_cost_snapshot,total_cost_snapshot,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'''
        pg_sql = sqlite_sql.replace('?', '%s')
        wid = safe_insert_returning(
            cur,
            sqlite_sql,
            (
                int(center_id or 0), int(warehouse_id or 0), int(responsible_user_id or 0), responsible_name.strip(),
                source_type, item_type, int(article_id or 0), int(recipe_id or 0), item_name_detected.strip(),
                float(qty or 0), unit or 'ud', float(qty_base or 0), base_unit or '', reason.strip(), notes.strip(), photo_path or '',
                voice_text_raw or '', image_text_raw or '', float(confidence or 0), status,
                float(unit_cost or 0), float(total_cost or 0), datetime.now().isoformat(timespec='seconds')
            ),
            pg_sql=pg_sql,
        ) or 0
    conn.commit(); conn.close()
    return wid


def update_waste_record(record_id: int, **fields) -> None:
    allowed = {'center_id','warehouse_id','responsible_user_id','responsible_name','item_type','article_id','recipe_id',
               'item_name_detected','qty','unit','reason','notes','confidence','status'}
    conn = db(); cur = conn.cursor(); ensure_waste_schema(cur)
    current = cur.execute('SELECT * FROM waste_records WHERE id=?', (int(record_id),)).fetchone()
    if not current:
        conn.close(); raise LookupError('Merma no encontrada')
    data = _row_to_dict(current)
    for k, v in fields.items():
        if k in allowed:
            data[k] = v
    qty_base, base_unit, unit_cost, total_cost = _compute_base_and_cost(cur, int(data.get('article_id') or 0), float(data.get('qty') or 0), data.get('unit') or 'ud')
    data['qty_base'] = qty_base; data['base_unit'] = base_unit; data['unit_cost_snapshot'] = unit_cost; data['total_cost_snapshot'] = total_cost
    # Estados terminales/administrativos no deben reabrirse por faltar artículo o cantidad.
    # Bug corregido: Anular merma llamaba update_waste_record(status='CANCELLED'), pero
    # esta validación volvía a poner REVIEW si la merma estaba sin identificar o cantidad 0.
    if str(data.get('status') or '').upper() not in {'CANCELLED', 'CONFIRMED'}:
        if int(data.get('article_id') or 0) <= 0 or float(data.get('qty') or 0) <= 0:
            data['status'] = 'REVIEW'
    cur.execute('''
      UPDATE waste_records SET center_id=?,warehouse_id=?,responsible_user_id=?,responsible_name=?,item_type=?,article_id=?,recipe_id=?,
        item_name_detected=?,qty=?,unit=?,qty_base=?,base_unit=?,reason=?,notes=?,confidence=?,status=?,unit_cost_snapshot=?,total_cost_snapshot=?
       WHERE id=?
    ''', (int(data.get('center_id') or 0), int(data.get('warehouse_id') or 0), int(data.get('responsible_user_id') or 0), data.get('responsible_name') or '',
          data.get('item_type') or 'unknown', int(data.get('article_id') or 0), int(data.get('recipe_id') or 0), data.get('item_name_detected') or '',
          float(data.get('qty') or 0), data.get('unit') or 'ud', float(qty_base or 0), base_unit or '', data.get('reason') or '', data.get('notes') or '',
          float(data.get('confidence') or 0), data.get('status') or 'REVIEW', float(unit_cost or 0), float(total_cost or 0), int(record_id)))
    conn.commit(); conn.close()


def confirm_waste_record(record_id: int, confirmed_by: str = '') -> dict[str, Any]:
    conn = db(); cur = conn.cursor(); ensure_waste_schema(cur)
    r = cur.execute('SELECT * FROM waste_records WHERE id=?', (int(record_id),)).fetchone()
    if not r:
        conn.close(); return {'ok': False, 'error_code': 'waste_not_found', 'error': 'Merma no encontrada'}
    d = _row_to_dict(r)
    if d.get('status') == 'CONFIRMED':
        conn.close(); return {'ok': True, 'message': 'Ya estaba confirmada'}
    if int(d.get('center_id') or 0) <= 0:
        conn.close(); return {'ok': False, 'error_code': 'waste_local', 'error': 'Falta local concreto. Selecciona un local antes de confirmar la merma.'}
    if not str(d.get('responsible_name') or confirmed_by or '').strip():
        conn.close(); return {'ok': False, 'error_code': 'waste_responsible', 'error': 'Falta responsable. Indica quién registra o confirma la merma.'}
    if int(d.get('article_id') or 0) <= 0:
        conn.close(); return {'ok': False, 'error_code': 'waste_article', 'error': 'Falta artículo/elaboración vinculada. Selecciona un artículo real del catálogo/stock antes de confirmar.'}
    if float(d.get('qty') or 0) <= 0 or float(d.get('qty_base') or 0) <= 0:
        conn.close(); return {'ok': False, 'error_code': 'waste_qty', 'error': 'Falta cantidad válida o unidad compatible.'}
    wh = cur.execute('SELECT center_id FROM warehouses WHERE id=?', (int(d.get('warehouse_id') or 0),)).fetchone()
    if not wh or int(wh['center_id'] or 0) != int(d.get('center_id') or 0):
        conn.close(); return {'ok': False, 'error_code': 'waste_warehouse', 'error': 'El almacén no pertenece al local seleccionado.'}
    note = f"MERMA #{int(record_id)} · {d.get('reason') or 'Sin motivo'} · Resp: {d.get('responsible_name') or confirmed_by or 'Sin responsable'}"
    sqlite_sql = '''INSERT INTO movements(center_id,warehouse_id,item_id,movement_type,qty,unit,note,created_at) VALUES(?,?,?,?,?,?,?,?)'''
    pg_sql = sqlite_sql.replace('?', '%s')
    movement_id = safe_insert_returning(
        cur,
        sqlite_sql,
        (int(d['center_id']), int(d['warehouse_id']), int(d['article_id']), 'OUT', float(d['qty_base']), d.get('base_unit') or d.get('unit') or 'ud', note, datetime.now().isoformat(timespec='seconds')),
        pg_sql=pg_sql,
    ) or 0
    cur.execute('''UPDATE waste_records SET status='CONFIRMED', movement_id=?, confirmed_at=?, confirmed_by=? WHERE id=?''',
                (movement_id, datetime.now().isoformat(timespec='seconds'), confirmed_by or d.get('responsible_name') or '', int(record_id)))
    conn.commit(); conn.close()
    return {'ok': True, 'movement_id': movement_id}


def list_waste_records(center_id: int = 0, status: str = '', limit: int = 120) -> list[dict[str, Any]]:
    conn = db(); cur = conn.cursor(); ensure_waste_schema(cur)
    clauses = []
    params: list[Any] = []
    if int(center_id or 0) > 0:
        clauses.append('wr.center_id=?'); params.append(int(center_id))
    if status:
        clauses.append('wr.status=?'); params.append(status.upper())
    where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
    rows = cur.execute(f'''
      SELECT wr.*, c.name center_name, w.name warehouse_name, i.name article_name, i.stock_area
        FROM waste_records wr
        LEFT JOIN centers c ON c.id=wr.center_id
        LEFT JOIN warehouses w ON w.id=wr.warehouse_id
        LEFT JOIN items i ON i.id=wr.article_id
       {where}
       ORDER BY wr.id DESC LIMIT ?
    ''', (*params, int(limit))).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = _row_to_dict(r)
        d['display_name'] = d.get('article_name') or d.get('item_name_detected') or 'Sin identificar'
        d['stock_area_label'] = stock_area_label(d.get('stock_area') or '')
        out.append(d)
    return out


def waste_analytics(center_id: int = 0, days: int = 30) -> dict[str, Any]:
    days = int(days or 30)
    if days not in {7, 30, 90, 365}:
        days = 30
    since = (datetime.now() - timedelta(days=days)).isoformat(timespec='seconds')
    conn = db(); cur = conn.cursor(); ensure_waste_schema(cur)
    params: list[Any] = [since]
    center_clause = ''
    if int(center_id or 0) > 0:
        center_clause = ' AND wr.center_id=?'
        params.append(int(center_id))
    rows = cur.execute(f'''
      SELECT wr.*, c.name center_name, w.name warehouse_name, i.name article_name, i.stock_area
        FROM waste_records wr
        LEFT JOIN centers c ON c.id=wr.center_id
        LEFT JOIN warehouses w ON w.id=wr.warehouse_id
        LEFT JOIN items i ON i.id=wr.article_id
       WHERE wr.created_at>=? {center_clause}
       ORDER BY wr.created_at DESC
    ''', tuple(params)).fetchall()
    conn.close()
    data = [_row_to_dict(r) for r in rows]
    confirmed = [r for r in data if r.get('status') == 'CONFIRMED']
    pending = [r for r in data if r.get('status') in {'DRAFT','REVIEW'}]
    total_loss = sum(float(r.get('total_cost_snapshot') or 0) for r in confirmed)
    potential_loss = sum(float(r.get('total_cost_snapshot') or 0) for r in pending)

    def group_sum(key_fn):
        grouped: dict[str, dict[str, Any]] = {}
        for r in confirmed:
            key = key_fn(r) or 'Sin dato'
            g = grouped.setdefault(key, {'label': key, 'count': 0, 'qty': 0.0, 'loss': 0.0})
            g['count'] += 1
            g['qty'] += float(r.get('qty_base') or r.get('qty') or 0)
            g['loss'] += float(r.get('total_cost_snapshot') or 0)
        return sorted(grouped.values(), key=lambda x: x['loss'], reverse=True)

    by_reason = group_sum(lambda r: r.get('reason') or 'Sin motivo')
    by_responsible = group_sum(lambda r: r.get('responsible_name') or 'Sin responsable')
    by_center = group_sum(lambda r: r.get('center_name') or f"Centro {r.get('center_id') or 0}")
    by_item = group_sum(lambda r: r.get('article_name') or r.get('item_name_detected') or 'Sin identificar')
    by_family = group_sum(lambda r: stock_area_label(r.get('stock_area') or '') or 'Sin familia')
    top_items = by_item[:10]
    return {
        'days': days,
        'total_records': len(data),
        'confirmed_records': len(confirmed),
        'pending_records': len(pending),
        'total_loss': round(total_loss, 4),
        'potential_loss': round(potential_loss, 4),
        'avg_loss': round(total_loss / len(confirmed), 4) if confirmed else 0.0,
        'by_reason': by_reason[:12],
        'by_responsible': by_responsible[:12],
        'by_center': by_center[:12],
        'by_family': by_family[:12],
        'top_items': top_items,
        'recent': data[:30],
    }


def save_waste_photo(upload, center_id: int) -> str:
    folder = Path(UPLOADS_DIR) / 'mermas'
    folder.mkdir(parents=True, exist_ok=True)
    filename = Path(getattr(upload, 'filename', '') or 'foto_merma.jpg').name
    safe = re.sub(r'[^A-Za-z0-9_.-]+', '_', filename).strip('_') or 'foto_merma.jpg'
    dst_name = f"merma_c{int(center_id or 0)}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{safe}"
    dst = folder / dst_name
    content = upload.file.read()
    dst.write_bytes(content)
    return f"mermas/{dst_name}"
