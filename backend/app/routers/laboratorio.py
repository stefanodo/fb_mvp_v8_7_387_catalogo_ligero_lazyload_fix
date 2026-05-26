# ==============================================================================
# BLOQUE LABORATORIO · Artículos y proveedores (alta, edición)
# ==============================================================================
from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from datetime import datetime

from app.core import db, ensure_columns, _provider_has_links, _provider_archive_name, display_price_from_base, fmt_num


def _item_has_links(cur, item_id: int) -> bool:
    checks = (
        ("recipe_ingredients", "item_id"),
        ("movements", "item_id"),
        ("supplier_item_prices", "item_id"),
        ("production_lines", "item_id"),
        ("order_lines", "item_id"),
        ("receipt_lines", "item_id"),
        ("inventory_counts", "item_id"),
    )
    for table, col in checks:
        try:
            row = cur.execute(f"SELECT COUNT(*) c FROM {table} WHERE {col}=?", (int(item_id),)).fetchone()
            if row and int(row["c"] or 0) > 0:
                return True
        except Exception:
            continue
    return False

from app.services.laboratory_service import normalize_item_payload, normalize_supplier_payload

router = APIRouter()


# ==============================================================================
# ARTÍCULOS
# ==============================================================================



@router.get("/api/admin/items_page")
def api_admin_items_page(q: str = "", limit: int = 50, offset: int = 0):
    """Catálogo ligero: devuelve solo el tramo necesario para no renderizar todo el HTML inicial."""
    limit = max(1, min(int(limit or 50), 120))
    offset = max(0, int(offset or 0))
    q_clean = (q or "").strip()
    conn = db(); cur = conn.cursor(); ensure_columns(cur)
    where = ""
    params: list = []
    if q_clean:
        where = "WHERE lower(COALESCE(name,'')) LIKE lower(?)"
        params.append(f"%{q_clean}%")
    total_row = cur.execute(f"SELECT COUNT(*) c FROM items {where}", params).fetchone()
    rows = cur.execute(
        f"""
        SELECT id,name,unit,current_price,waste_default_pct,COALESCE(stock_area,'') stock_area,
               COALESCE(order_category,'') order_category,COALESCE(item_type,'INSUMO') item_type,
               COALESCE(price_status,'') price_status,COALESCE(price_confidence,'') price_confidence
          FROM items
          {where}
         ORDER BY name COLLATE NOCASE
         LIMIT ? OFFSET ?
        """,
        params + [limit, offset],
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = {k: r[k] for k in r.keys()}
        try:
            d["display_price"] = display_price_from_base(float(d.get("current_price") or 0), d.get("unit") or "")
        except Exception:
            d["display_price"] = 0
        try:
            d["current_price_fmt"] = fmt_num(float(d.get("current_price") or 0), 5)
        except Exception:
            d["current_price_fmt"] = str(d.get("current_price") or "0")
        out.append(d)
    return JSONResponse({"ok": True, "items": out, "total": int(total_row["c"] or 0), "limit": limit, "offset": offset})


@router.get("/api/admin/supplier_prices_page")
def api_admin_supplier_prices_page(q: str = "", limit: int = 80, offset: int = 0):
    """Comparativa proveedores ligera. No se incrusta toda la tabla en la página."""
    limit = max(1, min(int(limit or 80), 200))
    offset = max(0, int(offset or 0))
    q_clean = (q or "").strip()
    where = ""
    params: list = []
    if q_clean:
        where = "WHERE lower(COALESCE(s.name,'')) LIKE lower(?) OR lower(COALESCE(i.name,'')) LIKE lower(?)"
        like = f"%{q_clean}%"
        params.extend([like, like])
    conn = db(); cur = conn.cursor(); ensure_columns(cur)
    total = cur.execute(
        f"""SELECT COUNT(*) c FROM supplier_item_prices sp
              JOIN suppliers s ON s.id=sp.supplier_id
              JOIN items i ON i.id=sp.item_id {where}""",
        params,
    ).fetchone()
    rows = cur.execute(
        f"""
        SELECT sp.id,sp.supplier_id,sp.item_id,sp.center_id,sp.price_per_purchase,sp.purchase_unit,
               sp.purchase_to_base_factor,sp.is_preferred,sp.updated_at,s.name supplier_name,i.name item_name
          FROM supplier_item_prices sp
          JOIN suppliers s ON s.id=sp.supplier_id
          JOIN items i ON i.id=sp.item_id
          {where}
         ORDER BY s.name COLLATE NOCASE,i.name COLLATE NOCASE
         LIMIT ? OFFSET ?
        """,
        params + [limit, offset],
    ).fetchall()
    conn.close()
    return JSONResponse({"ok": True, "prices": [{k: r[k] for k in r.keys()} for r in rows], "total": int(total["c"] or 0), "limit": limit, "offset": offset})

@router.post("/item/create_form")
def item_create_form(
    name: str = Form(...),
    unit: str = Form(...),
    current_price: str = Form("0"),
    current_price_unit: str = Form(""),
    waste_default_pct: str = Form(""),
    stock_area: str = Form(""),
    order_category: str = Form(""),
    item_type: str = Form("INSUMO"),
    supplier_id: int = Form(0),
    return_page: str = Form("admin"),
    lab_note: str = Form(""),
):
    # En edición masiva, los campos 0 se muestran vacíos para no obligar a borrar.
    # Vacío en edición significa 0 explícito, no sugerencia automática.
    if (current_price or "").strip() == "":
        current_price = "0"
    if (waste_default_pct or "").strip() == "":
        waste_default_pct = "0"
    payload = normalize_item_payload(name, unit, current_price, current_price_unit, waste_default_pct, stock_area, order_category, item_type)

    conn = db(); cur = conn.cursor(); ensure_columns(cur)
    dup = cur.execute("SELECT id FROM items WHERE lower(trim(name))=lower(trim(?)) AND unit=?",
                      (payload["name"], payload["unit"])).fetchone()
    if dup:
        conn.close()
        return RedirectResponse(url="/?page=admin&err=item_dup", status_code=303)

    cur.execute("INSERT INTO items(name,unit,min_qty,max_qty,current_price,waste_default_pct,stock_area,order_category,item_type,price_status,price_source,price_confidence,price_reference_year,price_operational_unit,price_operational_value,price_notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (payload["name"], payload["unit"], 0, 0, payload["current_price"], payload["waste_default_pct"], payload["stock_area"], payload["order_category"], payload["item_type"], 'PRECIO_MANUAL_PENDIENTE_CONFIRMAR', 'MANUAL', 'media', 'manual', payload["unit"], float(payload["current_price"] or 0), 'Alta manual: revisar si el precio está confirmado por proveedor/albarán.'))
    item_id = int(cur.lastrowid or 0)

    if int(supplier_id or 0) > 0 and item_id > 0:
        now = datetime.utcnow().isoformat()
        try:
            cur.execute(
                """INSERT INTO supplier_item_prices(supplier_id,item_id,center_id,price_per_purchase,
                   purchase_unit,purchase_to_base_factor,is_preferred,updated_at) VALUES(?,?,?,?,?,?,?,?)""",
                (int(supplier_id), int(item_id), None, payload["current_price"],
                 payload["current_price_unit"], 1.0, 1, now))
        except Exception:
            pass

    conn.commit(); conn.close()
    page_target = "laboratorio" if (return_page or "").strip().lower() == "laboratorio" else "admin"
    ok_qs = "lab=item_created" if page_target == "laboratorio" else "ok=1"
    return RedirectResponse(url=f"/?page={page_target}&{ok_qs}", status_code=303)


@router.post("/item/{item_id}/update_form")
def item_update_form(
    request: Request,
    item_id: int,
    name: str = Form(...),
    unit: str = Form(...),
    current_price: str = Form("0"),
    current_price_unit: str = Form(""),
    waste_default_pct: str = Form(""),
    stock_area: str = Form(""),
    order_category: str = Form(""),
    item_type: str = Form("INSUMO"),
    ajax: int = Form(0),
    return_query: str = Form(""),
):
    # En edición masiva, los campos 0 se muestran vacíos para no obligar a borrar.
    # Vacío en edición significa 0 explícito, no sugerencia automática.
    if (current_price or "").strip() == "":
        current_price = "0"
    if (waste_default_pct or "").strip() == "":
        waste_default_pct = "0"
    payload = normalize_item_payload(name, unit, current_price, current_price_unit, waste_default_pct, stock_area, order_category, item_type)

    conn = db(); cur = conn.cursor(); ensure_columns(cur)
    dup = cur.execute("SELECT id FROM items WHERE lower(trim(name))=lower(trim(?)) AND unit=? AND id<>?",
                      (payload["name"], payload["unit"], item_id)).fetchone()
    if dup:
        conn.close()
        if int(ajax or 0):
            return JSONResponse({"ok": False, "error": "item_dup"}, status_code=409)
        return RedirectResponse(url="/?page=admin&err=item_dup", status_code=303)

    cur.execute("UPDATE items SET name=?,unit=?,current_price=?,waste_default_pct=?,stock_area=?,order_category=?,item_type=?,price_status=COALESCE(NULLIF(price_status,''),'PRECIO_MANUAL_PENDIENTE_CONFIRMAR'),price_operational_unit=?,price_operational_value=? WHERE id=?",
                (payload["name"], payload["unit"], payload["current_price"], payload["waste_default_pct"], payload["stock_area"], payload["order_category"], payload["item_type"], payload["unit"], float(payload["current_price"] or 0), item_id))
    conn.commit(); conn.close()
    if int(ajax or 0):
        return JSONResponse({"ok": True, "item_id": int(item_id), "stock_area": payload["stock_area"], "name": payload["name"]})
    q = (return_query or '').strip()
    if q:
        return RedirectResponse(url=f"/?page=admin&{q}&ok=1#item-{int(item_id)}", status_code=303)
    return RedirectResponse(url=f"/?page=admin&ok=1#item-{int(item_id)}", status_code=303)


# ==============================================================================
# PROVEEDORES
# ==============================================================================

@router.post("/supplier/create_form")
def supplier_create_form(
    name: str = Form(...),
    phone: str = Form(""),
    email: str = Form(""),
    tax_id: str = Form(""),
    address: str = Form(""),
    postal_code: str = Form(""),
    city: str = Form(""),
    health_registry_code: str = Form(""),
    payment_terms: str = Form(""),
    payment_frequency: str = Form(""),
    payment_day_rule: str = Form(""),
    payment_method: str = Form(""),
    iban: str = Form(""),
    accounting_email: str = Form(""),
):
    payload = normalize_supplier_payload(name, phone, email)
    conn = db(); cur = conn.cursor(); ensure_columns(cur)
    cur.execute("""INSERT INTO suppliers(name,phone,email,is_active,tax_id,address,postal_code,city,health_registry_code,payment_terms,payment_frequency,payment_day_rule,payment_method,iban,accounting_email,requires_payment_approval)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                (payload["name"], payload["phone"], payload["email"], 1, tax_id.strip(), address.strip(), postal_code.strip(), city.strip(), health_registry_code.strip(), payment_terms.strip(), payment_frequency.strip(), payment_day_rule.strip(), payment_method.strip(), iban.strip(), accounting_email.strip()))
    conn.commit(); conn.close()
    return RedirectResponse(url="/?page=admin&ok=1#tab-proveedores", status_code=303)


@router.post("/supplier/{supplier_id}/update_form")
def supplier_update_form(
    supplier_id: int,
    name: str = Form(...),
    phone: str = Form(""),
    email: str = Form(""),
    is_active: int = Form(1),
    tax_id: str = Form(""),
    address: str = Form(""),
    postal_code: str = Form(""),
    city: str = Form(""),
    health_registry_code: str = Form(""),
    payment_terms: str = Form(""),
    payment_frequency: str = Form(""),
    payment_day_rule: str = Form(""),
    payment_method: str = Form(""),
    iban: str = Form(""),
    accounting_email: str = Form(""),
):
    payload = normalize_supplier_payload(name, phone, email)
    conn = db(); cur = conn.cursor(); ensure_columns(cur)
    cur.execute("""UPDATE suppliers SET name=?,phone=?,email=?,is_active=?,tax_id=?,address=?,postal_code=?,city=?,health_registry_code=?,payment_terms=?,payment_frequency=?,payment_day_rule=?,payment_method=?,iban=?,accounting_email=?,requires_payment_approval=1 WHERE id=?""",
                (payload["name"], payload["phone"], payload["email"], 1 if int(is_active) else 0, tax_id.strip(), address.strip(), postal_code.strip(), city.strip(), health_registry_code.strip(), payment_terms.strip(), payment_frequency.strip(), payment_day_rule.strip(), payment_method.strip(), iban.strip(), accounting_email.strip(), supplier_id))
    conn.commit(); conn.close()
    return RedirectResponse(url="/?page=admin&ok=1#tab-proveedores", status_code=303)


@router.post("/supplier/{supplier_id}/delete_form")
def supplier_delete_form(supplier_id: int):
    conn = db(); cur = conn.cursor()
    cur.execute("UPDATE suppliers SET is_active=0 WHERE id=?", (supplier_id,))
    conn.commit(); conn.close()
    return RedirectResponse(url="/?page=admin&ok=1", status_code=303)


@router.post("/provider/{provider_id}/delete_form")
def provider_delete_form(provider_id: int, center_id: int = Form(0)):
    conn = db(); cur = conn.cursor()
    sup = cur.execute("SELECT id,name FROM suppliers WHERE id=?", (int(provider_id),)).fetchone()
    if not sup:
        conn.close()
        return RedirectResponse(url=f"/?page=admin&center_id={int(center_id)}&provider_err=not_found",
                                status_code=303)
    try:
        if _provider_has_links(cur, int(provider_id)):
            cur.execute("UPDATE suppliers SET name=?,is_active=0 WHERE id=?",
                        (_provider_archive_name(sup["name"]), int(provider_id)))
            conn.commit(); conn.close()
            return RedirectResponse(url=f"/?page=admin&center_id={int(center_id)}&provider_archived=1",
                                    status_code=303)
        cur.execute("DELETE FROM suppliers WHERE id=?", (int(provider_id),))
        conn.commit(); conn.close()
        return RedirectResponse(url=f"/?page=admin&center_id={int(center_id)}&provider_deleted=1",
                                status_code=303)
    except Exception:
        conn.close()
        return RedirectResponse(url=f"/?page=admin&center_id={int(center_id)}&provider_err=delete_failed",
                                status_code=303)


# ==============================================================================
# API PROVEEDORES / PRECIOS
# ==============================================================================

@router.post("/api/suppliers")
def api_create_supplier(name: str = Form(...), phone: str = Form(""), email: str = Form("")):
    payload = normalize_supplier_payload(name, phone, email)
    if not payload["name"]:
        return JSONResponse({"ok": False, "error": "Nombre requerido"}, status_code=400)
    conn = db(); cur = conn.cursor()
    cur.execute("INSERT INTO suppliers(name,phone,email,is_active) VALUES(?,?,?,1)",
                (payload["name"], payload["phone"], payload["email"]))
    conn.commit(); conn.close()
    return {"ok": True, "message": "Proveedor creado"}


@router.post("/api/item/{item_id}/supplier_price")
def api_set_supplier_price(
    item_id: int,
    supplier_id: int = Form(...),
    price_per_purchase: float = Form(...),
    purchase_unit: str = Form(...),
    purchase_to_base_factor: float = Form(...),
    is_preferred: int = Form(0),
    center_id: int = Form(0),
):
    if price_per_purchase < 0 or purchase_to_base_factor <= 0:
        return JSONResponse({"ok": False, "error": "Precio/factor inválidos"}, status_code=400)
    conn = db(); cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    c_id = None if int(center_id) == 0 else int(center_id)
    if int(is_preferred) == 1:
        cur.execute("UPDATE supplier_item_prices SET is_preferred=0 WHERE item_id=? AND COALESCE(center_id,0)=COALESCE(?,0)",
                    (item_id, c_id))
    cur.execute(
        """INSERT INTO supplier_item_prices(supplier_id,item_id,center_id,price_per_purchase,
           purchase_unit,purchase_to_base_factor,is_preferred,updated_at) VALUES(?,?,?,?,?,?,?,?)""",
        (supplier_id, item_id, c_id, price_per_purchase, purchase_unit,
         purchase_to_base_factor, int(is_preferred), now))
    conn.commit(); conn.close()
    return {"ok": True, "message": "Precio guardado"}


@router.post("/item/{item_id}/delete_form")
def item_delete_form(item_id: int):
    conn = db(); cur = conn.cursor()
    item = cur.execute("SELECT id,name FROM items WHERE id=?", (int(item_id),)).fetchone()
    if not item:
        conn.close()
        return RedirectResponse(url="/?page=admin&err=item_not_found", status_code=303)
    if _item_has_links(cur, int(item_id)):
        conn.close()
        return RedirectResponse(url=f"/?page=admin&err=item_has_links#item-{int(item_id)}", status_code=303)
    cur.execute("DELETE FROM item_location_prefs WHERE item_id=?", (int(item_id),))
    cur.execute("DELETE FROM items WHERE id=?", (int(item_id),))
    conn.commit(); conn.close()
    return RedirectResponse(url="/?page=admin&ok=1", status_code=303)

# ==============================================================================
# LABORATORIO · TPV / CONTINUIDAD / CONCILIACIÓN DOCUMENTAL
# ============================================================================== 
from app.services.tpv_lab_service import get_tpv_lab_summary, simulate_tpv_sale, recipe_component_check
from app.services.continuity_service import continuity_summary, simulate_offline_case, sync_offline_events
from app.services.accounting_lab_service import accounting_summary, simulate_reconciliation


@router.get('/api/lab/tpv/summary')
def api_lab_tpv_summary():
    return JSONResponse(get_tpv_lab_summary())


@router.post('/api/lab/tpv/simulate')
async def api_lab_tpv_simulate(request: Request):
    payload = {}
    try:
        ctype = (request.headers.get('content-type') or '').lower()
        if 'application/json' in ctype:
            payload = await request.json()
        else:
            form = await request.form()
            payload = dict(form)
    except Exception:
        payload = {}
    return JSONResponse(simulate_tpv_sale(payload))


@router.get('/api/lab/tpv/components/{recipe_id}')
def api_lab_tpv_components(recipe_id: int):
    return JSONResponse(recipe_component_check(int(recipe_id)))


@router.get('/api/lab/continuity/summary')
def api_lab_continuity_summary():
    return JSONResponse(continuity_summary())


@router.post('/api/lab/continuity/simulate')
def api_lab_continuity_simulate(case: str = Form('merma')):
    return JSONResponse(simulate_offline_case(case))


@router.post('/api/lab/continuity/sync')
def api_lab_continuity_sync():
    return JSONResponse(sync_offline_events())


@router.get('/api/lab/accounting/summary')
def api_lab_accounting_summary():
    return JSONResponse(accounting_summary())


@router.post('/api/lab/accounting/simulate')
def api_lab_accounting_simulate():
    return JSONResponse(simulate_reconciliation())

@router.get('/manual/system-mac', response_class=HTMLResponse)
def manual_system_mac_html():
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / 'docs' / 'manual' / 'MANUAL_USUARIO_SYSTEM_MAC_IMPRIMIBLE.html'
    return HTMLResponse(path.read_text(encoding='utf-8'))

@router.get('/manual/system-mac.md', response_class=HTMLResponse)
def manual_system_mac_md():
    from pathlib import Path
    import html
    path = Path(__file__).resolve().parents[1] / 'docs' / 'manual' / 'MANUAL_USUARIO_SYSTEM_MAC.md'
    return HTMLResponse('<pre style="white-space:pre-wrap;font-family:ui-monospace,Menlo,monospace">' + html.escape(path.read_text(encoding='utf-8')) + '</pre>')

# ==============================================================================
# COCTELERÍA / BARRA LAB · DEMO NO PRODUCTIVO
# ==============================================================================
from app.services.cocktail_bar_service import load_cocktail_bar_demo, get_bar_summary, get_cocktail_detail, search_cocktails, get_bar_editor_options, save_cocktail, save_cocktail_line, delete_cocktail_line, save_cocktail_steps, simulate_consolidated_bar_kitchen_order, get_consolidated_order_summary, load_bar_beverage_demo, get_bar_beverage_summary, get_bar_beverage_detail, simulate_bar_beverage_sale, simulate_bar_beverage_receipt, get_bar_receipt_summary, load_bar_mixer_container_demo, get_bar_mixer_container_summary, simulate_single_shared_supplier_receipt, get_shared_supplier_receipt_summary, get_bar_stock_summary, get_bar_inventory_summary

@router.post('/api/lab/bar/load-demo')
def api_lab_bar_load_demo():
    base = load_cocktail_bar_demo()
    bev = load_bar_beverage_demo()
    if base.get('ok') and bev.get('ok'):
        base['beverage_services'] = bev
    return JSONResponse(base)

@router.get('/api/lab/bar/summary')
def api_lab_bar_summary():
    return JSONResponse(get_bar_summary())

@router.get('/api/lab/bar/cocktail/{recipe_id}')
def api_lab_bar_cocktail_detail(recipe_id: int):
    return JSONResponse(get_cocktail_detail(recipe_id))



@router.get('/api/lab/bar/cocktails/search')
def api_lab_bar_cocktails_search(q: str = ''):
    return JSONResponse(search_cocktails(q))

@router.get('/api/lab/bar/editor-options')
def api_lab_bar_editor_options():
    return JSONResponse(get_bar_editor_options())

@router.post('/api/lab/bar/cocktail/save')
def api_lab_bar_cocktail_save(
    id: int = Form(0), code: str = Form(''), name: str = Form(''), category: str = Form('clásico'),
    cocktail_type: str = Form(''), glass_type: str = Form(''), serving_size_ml: str = Form('0'),
    yield_qty: str = Form('1'), yield_unit: str = Form('copa'), difficulty: str = Form(''),
    preparation_time_minutes: str = Form('0'), seasonality: str = Form(''), sale_price: str = Form('0'),
    target_margin_percent: str = Form('80'), contingency_percent: str = Form('5'), photo_path: str = Form('pendiente_subir'),
    notes: str = Form(''), status: str = Form('activo')
):
    return JSONResponse(save_cocktail(locals()))

@router.post('/api/lab/bar/cocktail/{recipe_id}/line/save')
def api_lab_bar_cocktail_line_save(recipe_id: int, line_id: int = Form(0), origin: str = Form('stock_bar'), ingredient_name: str = Form(''), qty_net: str = Form('0'), unit: str = Form('ml'), waste_percent: str = Form('0'), cost_unit_2026: str = Form('')):
    return JSONResponse(save_cocktail_line(recipe_id, locals()))

@router.post('/api/lab/bar/cocktail/{recipe_id}/line/{line_id}/delete')
def api_lab_bar_cocktail_line_delete(recipe_id: int, line_id: int):
    return JSONResponse(delete_cocktail_line(recipe_id, line_id))

@router.post('/api/lab/bar/cocktail/{recipe_id}/steps/save')
def api_lab_bar_cocktail_steps_save(recipe_id: int, steps_text: str = Form('')):
    return JSONResponse(save_cocktail_steps(recipe_id, steps_text))


@router.post('/api/lab/bar/beverages/load-demo')
def api_lab_bar_beverages_load_demo():
    return JSONResponse(load_bar_beverage_demo())

@router.get('/api/lab/bar/stock/summary')
def api_lab_bar_stock_summary():
    return JSONResponse(get_bar_stock_summary())

@router.get('/api/lab/bar/inventory/summary')
def api_lab_bar_inventory_summary():
    return JSONResponse(get_bar_inventory_summary())

@router.get('/api/lab/bar/beverages/summary')
def api_lab_bar_beverages_summary():
    return JSONResponse(get_bar_beverage_summary())

@router.post('/api/lab/bar/beverages/simulate')
def api_lab_bar_beverage_simulate(service_code: str = Form('BAR-SVC-VODKA-REDBULL-001'), billing_mode: str = Form('')):
    return JSONResponse(simulate_bar_beverage_sale(service_code, billing_mode))

@router.get('/api/lab/bar/beverages/{service_id}')
def api_lab_bar_beverage_detail(service_id: int):
    return JSONResponse(get_bar_beverage_detail(service_id))




@router.post('/api/lab/bar/receipts/simulate')
def api_lab_bar_receipts_simulate(receipt_variant: str = Form('beverages')):
    return JSONResponse(simulate_bar_beverage_receipt(receipt_variant))

@router.get('/api/lab/bar/receipts/summary')
def api_lab_bar_receipts_summary():
    return JSONResponse(get_bar_receipt_summary())

@router.post('/api/lab/bar/mixers/load-demo')
def api_lab_bar_mixers_load_demo():
    return JSONResponse(load_bar_mixer_container_demo())

@router.get('/api/lab/bar/mixers/summary')
def api_lab_bar_mixers_summary():
    return JSONResponse(get_bar_mixer_container_summary())


@router.post('/api/lab/bar/shared-receipts/simulate')
def api_lab_bar_shared_receipts_simulate(receipt_variant: str = Form('pedido_previo')):
    return JSONResponse(simulate_single_shared_supplier_receipt(receipt_variant))

@router.get('/api/lab/bar/shared-receipts/summary')
def api_lab_bar_shared_receipts_summary():
    return JSONResponse(get_shared_supplier_receipt_summary())

@router.post('/api/lab/bar/orders/simulate')
def api_lab_bar_orders_simulate(receipt_variant: str = Form('match')):
    return JSONResponse(simulate_consolidated_bar_kitchen_order(receipt_variant))

@router.get('/api/lab/bar/orders/summary')
def api_lab_bar_orders_summary():
    return JSONResponse(get_consolidated_order_summary())

# ==============================================================================
# LAB · Flujos críticos móvil + OÍDO ALFI (sin tocar stock productivo)
# ==============================================================================
from app.services.critical_mobile_alfi_service import (
    simulate_all_critical_flows,
    list_critical_flow_summary,
    confirm_critical_draft,
    alfi_critical_preview,
)


@router.get("/api/lab/critical/summary")
def api_lab_critical_summary():
    return JSONResponse(list_critical_flow_summary())


@router.post("/api/lab/critical/simulate")
def api_lab_critical_simulate():
    return JSONResponse(simulate_all_critical_flows())


@router.post("/api/lab/critical/confirm")
def api_lab_critical_confirm(draft_id: int = Form(...), actor: str = Form("Sistema Demo"), note: str = Form("Confirmación LAB")):
    return JSONResponse(confirm_critical_draft(draft_id, actor=actor, note=note))


@router.post("/api/lab/critical/alfi-preview")
def api_lab_critical_alfi_preview(text: str = Form(""), actor: str = Form("ALFI LAB")):
    return JSONResponse(alfi_critical_preview(text, actor=actor))
