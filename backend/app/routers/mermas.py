from __future__ import annotations

from fastapi import APIRouter, Form, UploadFile, File
from fastapi.responses import RedirectResponse, JSONResponse
from typing import Optional

from app.core import db, ensure_columns
from app.services.waste_service import (
    WASTE_REASONS, ensure_waste_schema, parse_voice_text, match_item_or_recipe,
    create_waste_record, update_waste_record, confirm_waste_record, save_waste_photo,
    default_warehouse_id,
)

router = APIRouter()


def _waste_url(center_id: int = 0, **params):
    q = {'page': 'mermas', 'center_id': int(center_id or 0)}
    q.update({k: v for k, v in params.items() if v is not None and v != ''})
    return '/?' + '&'.join(f"{k}={v}" for k, v in q.items())


def _control_url(center_id: int = 0, **params):
    q = {'page': 'mermas_control', 'center_id': int(center_id or 0)}
    q.update({k: v for k, v in params.items() if v is not None and v != ''})
    return '/?' + '&'.join(f"{k}={v}" for k, v in q.items())


def _resolve_responsible(cur, responsible_user_id: int, responsible_name: str) -> tuple[int, str]:
    rid = int(responsible_user_id or 0)
    name = (responsible_name or '').strip()
    if rid > 0:
        row = cur.execute('SELECT id,name FROM users WHERE id=? AND COALESCE(is_active,1)=1', (rid,)).fetchone()
        if row:
            return int(row['id']), (row['name'] or '').strip()
    return 0, name


@router.post('/waste/manual')
def waste_manual(center_id: int = Form(...), warehouse_id: int = Form(0), responsible_user_id: int = Form(0),
                 responsible_name: str = Form(''), item_type: str = Form('article'), article_id: int = Form(0),
                 item_name_detected: str = Form(''), qty: float = Form(0), unit: str = Form('kg'),
                 reason: str = Form(''), notes: str = Form('')):
    conn = db(); cur = conn.cursor(); ensure_waste_schema(cur)
    rid, rname = _resolve_responsible(cur, responsible_user_id, responsible_name)
    if not article_id and item_name_detected:
        match = match_item_or_recipe(cur, item_name_detected)
        article_id = int(match.get('article_id') or 0)
        item_type = match.get('item_type') or item_type
        if not article_id:
            item_name_detected = item_name_detected.strip()
    if not warehouse_id:
        warehouse_id = default_warehouse_id(cur, int(center_id), item_type)
    conn.close()
    status = 'REVIEW' if not rname or not article_id or float(qty or 0) <= 0 else 'DRAFT'
    wid = create_waste_record(center_id=center_id, warehouse_id=warehouse_id, responsible_user_id=rid,
                              responsible_name=rname, source_type='manual', item_type=item_type,
                              article_id=article_id, item_name_detected=item_name_detected, qty=qty,
                              unit=unit, reason=reason, notes=notes, confidence=100 if article_id else 25,
                              status=status)
    return RedirectResponse(_waste_url(center_id, wid=wid, ok=1), status_code=303)


@router.post('/waste/from_voice')
def waste_from_voice(center_id: int = Form(...), warehouse_id: int = Form(0), responsible_user_id: int = Form(0),
                     responsible_name: str = Form(''), voice_text: str = Form(''), photo_note: str = Form(''),
                     photo: Optional[UploadFile] = File(None)):
    conn = db(); cur = conn.cursor(); ensure_waste_schema(cur)
    parsed = parse_voice_text(cur, voice_text)
    rid, rname = _resolve_responsible(cur, responsible_user_id, responsible_name or parsed.get('responsible_name') or '')
    item_type = parsed.get('item_type') or 'unknown'
    if not warehouse_id:
        warehouse_id = default_warehouse_id(cur, int(center_id), item_type)
    conn.close()
    photo_path = ''
    if photo is not None and getattr(photo, 'filename', ''):
        try:
            photo_path = save_waste_photo(photo, int(center_id or 0))
        except Exception:
            photo_path = ''
    notes = 'Creado desde voz; revisar antes de confirmar.'
    if photo_note:
        notes += ' Foto/nota opcional: ' + photo_note.strip()
    wid = create_waste_record(center_id=center_id, warehouse_id=warehouse_id, responsible_user_id=rid,
                              responsible_name=rname, source_type='voice_photo' if photo_path else 'voice', item_type=item_type,
                              article_id=int(parsed.get('article_id') or 0), recipe_id=int(parsed.get('recipe_id') or 0),
                              item_name_detected=parsed.get('name') or parsed.get('item_text') or '',
                              qty=float(parsed.get('qty') or 0), unit=parsed.get('unit') or 'kg',
                              reason=parsed.get('reason') or '', notes=notes, photo_path=photo_path,
                              voice_text_raw=voice_text, image_text_raw=photo_note or '',
                              confidence=float(parsed.get('confidence') or 0), status='REVIEW')
    return RedirectResponse(_waste_url(center_id, wid=wid, ok_voice=1), status_code=303)


@router.post('/waste/from_photo')
def waste_from_photo(center_id: int = Form(...), warehouse_id: int = Form(0), responsible_user_id: int = Form(0),
                     responsible_name: str = Form(''), photo_note: str = Form(''), qty: float = Form(0),
                     unit: str = Form('kg'), reason: str = Form(''), photo: UploadFile = File(...)):
    conn = db(); cur = conn.cursor(); ensure_waste_schema(cur)
    rid, rname = _resolve_responsible(cur, responsible_user_id, responsible_name)
    photo_path = save_waste_photo(photo, int(center_id or 0))
    # Reconocimiento seguro inicial: usa texto de apoyo/nombre de archivo. La foto queda como evidencia.
    probe = ' '.join([photo_note or '', getattr(photo, 'filename', '') or '']).strip()
    match = match_item_or_recipe(cur, probe)
    item_type = match.get('item_type') or 'unknown'
    if not warehouse_id:
        warehouse_id = default_warehouse_id(cur, int(center_id), item_type)
    conn.close()
    wid = create_waste_record(center_id=center_id, warehouse_id=warehouse_id, responsible_user_id=rid,
                              responsible_name=rname, source_type='photo', item_type=item_type,
                              article_id=int(match.get('article_id') or 0), recipe_id=int(match.get('recipe_id') or 0),
                              item_name_detected=match.get('name') or photo_note or '', qty=float(qty or 0),
                              unit=unit or match.get('unit') or 'kg', reason=reason, notes=photo_note,
                              photo_path=photo_path, image_text_raw=f"filename={getattr(photo, 'filename', '')}; note={photo_note}",
                              confidence=float(match.get('confidence') or 0), status='REVIEW')
    return RedirectResponse(_waste_url(center_id, wid=wid, ok_photo=1), status_code=303)


@router.post('/waste/{record_id}/update')
def waste_update(record_id: int, center_id: int = Form(...), warehouse_id: int = Form(0), responsible_user_id: int = Form(0),
                 responsible_name: str = Form(''), item_type: str = Form('article'), article_id: int = Form(0),
                 item_name_detected: str = Form(''), qty: float = Form(0), unit: str = Form('kg'),
                 reason: str = Form(''), notes: str = Form(''), status: str = Form('REVIEW')):
    conn = db(); cur = conn.cursor(); ensure_waste_schema(cur)
    rid, rname = _resolve_responsible(cur, responsible_user_id, responsible_name)
    if not warehouse_id:
        warehouse_id = default_warehouse_id(cur, int(center_id), item_type)
    if article_id and not item_name_detected:
        row = cur.execute('SELECT name FROM items WHERE id=?', (int(article_id),)).fetchone()
        if row:
            item_name_detected = row['name']
    if not article_id and item_name_detected:
        match = match_item_or_recipe(cur, item_name_detected)
        article_id = int(match.get('article_id') or 0)
        if article_id:
            item_type = match.get('item_type') or item_type
            item_name_detected = match.get('name') or item_name_detected
    conn.close()
    update_waste_record(record_id, center_id=center_id, warehouse_id=warehouse_id, responsible_user_id=rid,
                        responsible_name=rname, item_type=item_type, article_id=article_id,
                        item_name_detected=item_name_detected, qty=qty, unit=unit, reason=reason,
                        notes=notes, status=status)
    return RedirectResponse(_waste_url(center_id, wid=record_id, ok=1), status_code=303)


@router.post('/waste/{record_id}/confirm')
def waste_confirm(record_id: int, center_id: int = Form(0), confirmed_by: str = Form('')):
    res = confirm_waste_record(record_id, confirmed_by=confirmed_by)
    return RedirectResponse(_waste_url(center_id, wid=record_id, confirmed=1 if res.get('ok') else '', err='' if res.get('ok') else (res.get('error_code') or 'waste_confirm')), status_code=303)


@router.post('/waste/{record_id}/cancel')
def waste_cancel(record_id: int, center_id: int = Form(0)):
    # Cancelación administrativa directa: no exige artículo, cantidad ni responsable.
    # Debe funcionar también para registros creados por voz/foto que están sin identificar.
    conn = db(); cur = conn.cursor(); ensure_waste_schema(cur)
    try:
        cur.execute("UPDATE waste_records SET status='CANCELLED' WHERE id=? AND COALESCE(status,'')!='CONFIRMED'", (int(record_id),))
        conn.commit()
    finally:
        conn.close()
    return RedirectResponse(_waste_url(center_id, wid=record_id, cancelled=1), status_code=303)


@router.get('/api/waste/search')
def waste_search(q: str = '', limit: int = 20):
    conn = db(); cur = conn.cursor(); ensure_waste_schema(cur)
    ql = f"%{(q or '').strip()}%"
    rows = cur.execute('SELECT id,name,unit,current_price,stock_area FROM items WHERE name LIKE ? ORDER BY name COLLATE NOCASE LIMIT ?', (ql, int(limit or 20))).fetchall()
    recipes = cur.execute('SELECT id,name,is_subrecipe FROM recipes WHERE COALESCE(is_active,1)=1 AND name LIKE ? ORDER BY name COLLATE NOCASE LIMIT ?', (ql, int(limit or 20))).fetchall()
    conn.close()
    return JSONResponse({
        'items': [{k: r[k] for k in r.keys()} for r in rows],
        'recipes': [{k: r[k] for k in r.keys()} for r in recipes],
    })
