# ==============================================================================
# BLOQUE PRODUCCIONES · Crear, gestionar y confirmar producciones
# ==============================================================================
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core import db, production_with_lines
from app.services.productions_redirect_service import production_redirect_url
from app.services.productions_create_service import create_draft_production, load_recipe_into_production
from app.services.productions_lines_service import add_manual_line, update_line_qty, delete_line
from app.services.productions_confirm_service import (
    update_production_note, delete_draft_production, reopen_production,
    confirm_production, archive_production, restore_archived_production,
)
from app.services.productions_batch_service import create_batch_drafts
from app.services.productions_history_service import build_print_group_rows
from app.services.productions_print_service import render_group_print, render_single_production_print

router = APIRouter()


def _production_warehouse_belongs(cur, warehouse_id: int, center_id: int) -> bool:
    try:
        row = cur.execute("SELECT 1 FROM warehouses WHERE id=? AND center_id=?", (int(warehouse_id), int(center_id))).fetchone()
        return bool(row)
    except Exception:
        return False


def _production_detail_redirect(production_id: int, *, center_id=None, ok=None, err=None, warn=None, anchor=None):
    return RedirectResponse(
        url=production_redirect_url(center_id=center_id, production_id=production_id, ok=ok, err=err, anchor=anchor, extra=({'warn': warn} if warn else None)),
        status_code=303,
    )

@router.post("/production/new_form")
def production_new_form(
    center_id: int = Form(...),
    warehouse_id: int = Form(...),
    note: str = Form(""),
    production_group: str = Form("Otros"),
):
    conn = db(); cur = conn.cursor()
    if not _production_warehouse_belongs(cur, int(warehouse_id or 0), int(center_id or 0)):
        conn.close()
        return RedirectResponse(url=f'/?page=producciones&center_id={center_id}&err=1', status_code=303)
    pid = create_draft_production(cur, center_id=center_id, warehouse_id=warehouse_id, note=note, production_group=production_group)
    conn.commit(); conn.close()
    return RedirectResponse(url=production_redirect_url(center_id=center_id, production_id=pid), status_code=303)


@router.post("/production/{production_id}/add_line_form")
def production_add_line_form(
    production_id: int,
    line_type: str = Form(...),
    item_id: str = Form(""),
    item_query: str = Form(""),
    qty_value: str = Form(""),
    qty_unit: str = Form(""),
):
    conn = db(); cur = conn.cursor()
    result = add_manual_line(cur, production_id=production_id, line_type=line_type, item_id=item_id, item_query=item_query, qty_value=qty_value, qty_unit=qty_unit)
    if not result:
        conn.close()
        return RedirectResponse(url=f"/?page=producciones&pid={production_id}&err=1#productionDetailPanel", status_code=303)
    conn.commit(); conn.close()
    return RedirectResponse(url=production_redirect_url(center_id=result['center_id'], production_id=production_id), status_code=303)


@router.post("/production/{production_id}/update_note_form")
def production_update_note_form(production_id: int, note: str = Form("")):
    conn = db(); cur = conn.cursor()
    result = update_production_note(cur, production_id=production_id, note=note)
    if not result:
        conn.close()
        return _production_detail_redirect(production_id, err=1)
    conn.commit(); conn.close()
    return _production_detail_redirect(production_id, center_id=result['center_id'], ok=1)


@router.post("/production/{production_id}/delete_line/{line_id}")
def production_delete_line_form(production_id: int, line_id: int):
    conn = db(); cur = conn.cursor()
    result = delete_line(cur, production_id=production_id, line_id=line_id)
    if not result:
        conn.close()
        return _production_detail_redirect(production_id, err=1)
    conn.commit(); conn.close()
    return _production_detail_redirect(production_id, center_id=result['center_id'])


@router.post("/production/{production_id}/update_line/{line_id}")
def production_update_line_form(
    production_id: int, line_id: int,
    qty_value: str = Form(...), qty_unit: str = Form(...),
):
    conn = db(); cur = conn.cursor()
    result = update_line_qty(cur, production_id=production_id, line_id=line_id, qty_value=qty_value, qty_unit=qty_unit)
    if not result:
        conn.close()
        return _production_detail_redirect(production_id, err=1)
    conn.commit(); conn.close()
    return _production_detail_redirect(production_id, center_id=result['center_id'], ok=1)


@router.post("/production/{production_id}/delete_form")
def production_delete_form(production_id: int):
    conn = db(); cur = conn.cursor()
    result = delete_draft_production(cur, production_id=production_id)
    if not result:
        conn.close()
        return RedirectResponse(url=f"/?page=producciones&pid={production_id}&err=1#productionDetailPanel", status_code=303)
    conn.commit(); conn.close()
    return RedirectResponse(url=f"/?page=producciones&center_id={result['center_id']}&ok=1", status_code=303)


@router.post("/production/{production_id}/load_recipe_form")
def production_load_recipe_form(
    production_id: int,
    recipe_id: str = Form(""),
    recipe_query: str = Form(""),
    multiplier: str = Form("1"),
    target_unit: str = Form("lotes"),
):
    conn = db(); cur = conn.cursor()
    result = load_recipe_into_production(cur, production_id=production_id, recipe_id=recipe_id, recipe_query=recipe_query, multiplier=multiplier, target_unit=target_unit)
    if not result:
        conn.close()
        return _production_detail_redirect(production_id, err=1)
    conn.commit(); conn.close()
    return _production_detail_redirect(production_id, center_id=result['center_id'], ok=1)


@router.post("/production/{production_id}/reopen_form")
def production_reopen_form(production_id: int):
    conn = db(); cur = conn.cursor()
    result = reopen_production(cur, production_id=production_id)
    if not result:
        row = cur.execute("SELECT center_id,status FROM productions WHERE id=?", (production_id,)).fetchone()
        conn.close()
        if row and (row['status'] or '') == 'CONFIRMED':
            return _production_detail_redirect(production_id, center_id=row['center_id'], warn='reopen_locked')
        return _production_detail_redirect(production_id, err=1)
    conn.commit(); conn.close()
    return _production_detail_redirect(production_id, center_id=result['center_id'], ok=1)


@router.post("/production/{production_id}/confirm_form")
def production_confirm_form(production_id: int):
    conn = db(); cur = conn.cursor()
    result = confirm_production(cur, production_id=production_id)
    if not result:
        conn.close()
        return _production_detail_redirect(production_id, err=1)
    conn.commit(); conn.close()
    return _production_detail_redirect(production_id, center_id=result['center_id'], ok=1)


@router.post("/production/{production_id}/archive_form")
def production_archive_form(production_id: int):
    conn = db(); cur = conn.cursor()
    result = archive_production(cur, production_id=production_id)
    if not result:
        conn.close()
        return RedirectResponse(url=f"/?page=producciones&pid={production_id}&err=1#productionDetailPanel", status_code=303)
    conn.commit(); conn.close()
    return RedirectResponse(url=f"/?page=producciones&center_id={result['center_id']}&ok=1", status_code=303)


@router.post("/production/{production_id}/restore_form")
def production_restore_form(production_id: int):
    conn = db(); cur = conn.cursor()
    result = restore_archived_production(cur, production_id=production_id)
    if not result:
        conn.close()
        return RedirectResponse(url=f"/?page=producciones&pid={production_id}&err=1#productionDetailPanel", status_code=303)
    conn.commit(); conn.close()
    return RedirectResponse(url=f"/?page=producciones&center_id={result['center_id']}&show_archived_productions=1&ok=1#productionDetailPanel", status_code=303)


@router.get("/production/{production_id}/print", response_class=HTMLResponse)
def production_print(production_id: int, request: Request):
    conn = db(); cur = conn.cursor()
    pd = production_with_lines(cur, int(production_id))
    conn.close()
    if not pd:
        return HTMLResponse("Producción no encontrada", status_code=404)
    return HTMLResponse(render_single_production_print(pd))



# ==============================================================================
# BATCH PRODUCCIONES — crear múltiples borradores de golpe (v8.7.198)
# ==============================================================================

@router.post("/productions/batch_new_form")
def productions_batch_new_form(
    center_id: int = Form(...),
    warehouse_id: int = Form(...),
    batch_payload: str = Form(""),
    append_production_id: int = Form(0),
):
    conn = db(); cur = conn.cursor()
    if not _production_warehouse_belongs(cur, int(warehouse_id or 0), int(center_id or 0)):
        conn.close()
        return RedirectResponse(url=f'/?page=producciones&center_id={center_id}&err=1', status_code=303)
    created_ids = create_batch_drafts(cur, center_id=center_id, warehouse_id=warehouse_id, batch_payload=batch_payload, append_production_id=(append_production_id or None))
    conn.commit(); conn.close()
    if created_ids:
        target_pid = int(append_production_id) if int(append_production_id or 0) > 0 else int(created_ids[-1])
        return _production_detail_redirect(target_pid, center_id=center_id, ok=1)
    target_pid = int(append_production_id or 0)
    if target_pid > 0:
        return _production_detail_redirect(target_pid, center_id=center_id, warn='dup_batch')
    return RedirectResponse(url=f"/?page=producciones&center_id={center_id}&warn=dup_batch", status_code=303)


@router.get("/productions/print_group", response_class=HTMLResponse)
def productions_print_group(request: Request, center_id: int, production_group: str):
    conn = db(); cur = conn.cursor()
    rows = build_print_group_rows(cur, center_id=center_id, production_group=production_group)
    conn.close()
    return HTMLResponse(render_group_print(rows, production_group))
