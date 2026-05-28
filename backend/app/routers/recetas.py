# ==============================================================================
# BLOQUE RECETAS · Recetas, ingredientes, fotos, impresión
# ==============================================================================
from fastapi import APIRouter, Form, File, UploadFile, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from typing import Optional
import re
import sqlite3
import time
from datetime import datetime
from difflib import SequenceMatcher

from app.core import (
    db, _retry_db_write, _is_db_locked_error, _parse_float, _resolve_item_id, _resolve_item_id_strict,
    _unit_factor, _canonical_unit, _parse_scope, recipe_with_calc, next_recipe_code,
    CATEGORY_CODES, ALLERGENS_UE, SUBCATEGORIES, APP_DIR,
    fmt_num, fmt_dt, status_label, human_qty,
    _normalize_uploaded_image_bytes_to_jpeg,
    safe_insert_returning,
    db_truthy_sql,
)

from app.services.recipes_service import build_recipe_create_payload
from app.services.recipes_form_service import build_recipe_update_payload, recipe_page_url

router = APIRouter()


def _tax_mode_value(v: str) -> str:
    v = (v or "ex_vat").strip().lower()
    return v if v in ("ex_vat", "inc_vat") else "ex_vat"


@router.get("/api/recipes/search")
def api_recipes_search(q: str = "", limit: int = 8, subrecipes_only: int = 0):
    q = (q or "").strip()
    try:
        lim = max(1, min(int(limit or 8), 30))
    except Exception:
        lim = 8
    only_sub = int(subrecipes_only or 0) == 1
    conn = db(); cur = conn.cursor()
    where = [db_truthy_sql("is_active", cur)]
    params = []
    if only_sub:
        where.append("COALESCE(is_subrecipe,0)=1")
    sql = "SELECT id,code,name,category,subcategory,is_subrecipe,yield_final_unit FROM recipes WHERE " + " AND ".join(where) + " ORDER BY name LIMIT 900"
    all_rows = cur.execute(sql, tuple(params)).fetchall()
    conn.close()

    import unicodedata
    def norm(v):
        txt = str(v or '').strip().lower()
        txt = unicodedata.normalize('NFKD', txt)
        txt = ''.join(ch for ch in txt if not unicodedata.combining(ch))
        txt = re.sub(r'[^a-z0-9]+', ' ', txt)
        txt = re.sub(r'(.)\1{1,}', r'\1', txt)
        return ' '.join(txt.split())

    nq = norm(q)
    scored = []
    for r in all_rows:
        name = (r['name'] or '').strip()
        hay = norm(f"{r['code'] or ''} {name} {r['category'] or ''} {r['subcategory'] or ''}")
        if not nq:
            score = 1.0
        else:
            qtok = set(nq.split()); htok = set(hay.split())
            token_score = len(qtok & htok) / max(len(qtok), 1)
            ratio = SequenceMatcher(None, nq, hay).ratio()
            contains = 1.0 if nq in hay or hay in nq else 0.0
            score = max(token_score, ratio, contains)
        if not nq or score >= 0.32:
            scored.append((score, name.lower(), r))
    scored.sort(key=lambda x: (-x[0], x[1]))
    rows = [x[2] for x in scored[:lim]]
    return JSONResponse({"items":[{
        "id": int(r["id"]),
        "code": (r["code"] or ""),
        "name": (r["name"] or "").strip(),
        "category": (r["category"] or ""),
        "subcategory": (r["subcategory"] or ""),
        "is_subrecipe": int(r["is_subrecipe"] or 0),
        "yield_unit": (r["yield_final_unit"] or "g"),
    } for r in rows]})


# ==============================================================================
# IMPRIMIR RECETA
# ==============================================================================

@router.get("/recipe/{recipe_id}/print", response_class=HTMLResponse)
def recipe_print(recipe_id: int, request: Request, mode: str = "staff"):
    conn = db()
    cur = conn.cursor()
    rd = recipe_with_calc(cur, int(recipe_id))
    conn.commit()
    conn.close()
    if not rd:
        return HTMLResponse("Receta no encontrada", status_code=404)

    rec = rd
    calc = (rd.get("calc") or {})
    ingredients = rec.get("ingredients") or []
    # For printing an existing recipe we already have `recipe_id` and `rd`.
    # Ensure `rid` is set for downstream rendering; do not run DDL/insert here.
    rid = int(recipe_id or 0)
    def cost_line_str(ing):
        lc = float(ing.get("line_cost") or 0)
        if lc <= 0 and float(ing.get("unit_cost") or 0) <= 0:
            return "<span class='warn-text'>0,00 €</span>"
        return f"{lc:.2f} €"

    missing_price_count = sum(1 for i in ingredients if float(i.get("unit_cost") or 0) <= 0)
    ing_rows = "".join(
        f"<tr><td>{esc(i.get('item_name',''))}</td><td class='right'>{ing_qty_str(i)}</td><td class='right'>{price_used_str(i)}</td><td class='right'><b>{cost_line_str(i)}</b></td></tr>"
        for i in ingredients)
    missing_price_notice = ""
    if missing_price_count:
        missing_price_notice = f"<div class='price-warning'>Aviso: hay {missing_price_count} ingrediente(s) sin precio. El coste total puede estar incompleto.</div>"
    steps = esc(rec.get("prep_steps") or "").replace("\n", "<br>")
    allergens_txt = esc(rec.get("allergens") or "")
    title = esc(rec.get("name") or "Receta")
    code = esc(rec.get("code") or "")
    cat = esc(rec.get("category") or "")
    sub = esc(rec.get("subcategory") or "")
    photo_path = (rec.get("recipe_photo_path") or "").strip()
    photo_block = ""
    if photo_path:
        photo_src = photo_path if photo_path.startswith(("http://", "https://", "/")) else f"/{photo_path.lstrip('/')}"
        photo_block = f"<div class='recipe-photo-wrap'><img class='recipe-photo' src='{esc(photo_src)}' alt='Foto receta'></div>"

    labor_block = ""
    labor_total_min = float(calc.get('production_time_total_min',0) or 0)
    labor_people = float(calc.get('labor_people',0) or 0)
    labor_hourly = float(calc.get('labor_hourly_cost',0) or 0)
    if labor_total_min or labor_people or labor_hourly:
        labor_block = f"""
        <h2>Tiempo y mano de obra</h2>
        <table class='meta-table'>
          <tr><td><b>Preparación</b></td><td class='right'>{float(calc.get('prep_time_min',0)):.0f} min</td></tr>
          <tr><td><b>Cocción</b></td><td class='right'>{float(calc.get('cook_time_min',0)):.0f} min</td></tr>
          <tr><td><b>Reposo / enfriado</b></td><td class='right'>{float(calc.get('rest_time_min',0)):.0f} min</td></tr>
          <tr><td><b>Tiempo total</b></td><td class='right'>{labor_total_min:.0f} min</td></tr>
          <tr><td><b>Personas</b></td><td class='right'>{labor_people:.2f}</td></tr>
          <tr><td><b>Coste hora</b></td><td class='right'>{labor_hourly:.2f} €/h</td></tr>
          <tr><td><b>Coste mano de obra</b></td><td class='right'>{float(calc.get('labor_cost_total',0)):.2f} €</td></tr>
          <tr><td><b>Mano de obra/ración</b></td><td class='right'>{float(calc.get('labor_cost_per_portion',0)):.2f} €</td></tr>
        </table>
        <div class='muted' style='margin-top:4px;'>La mano de obra es informativa y no modifica el food cost.</div>"""

    costs_block = ""
    if (mode or "").lower() in ("costs", "cost", "full"):
        costs_block = f"""
        <h2>Resumen económico</h2>
        <table class='meta-table'>
          <tr><td><b>Coste materia prima</b></td><td class='right'>{float(calc.get('cost_base',0)):.2f} €</td></tr>
          <tr><td><b>Coste + contingencia</b></td><td class='right'>{float(calc.get('cost_adjusted',0)):.2f} €</td></tr>
          <tr><td><b>Raciones</b></td><td class='right'>{float(calc.get('yield_portions',1)):.2f}</td></tr>
          <tr><td><b>Coste por ración</b></td><td class='right'>{float(calc.get('cost_per_portion',0)):.2f} €</td></tr>
          <tr><td><b>Food cost real</b></td><td class='right'>{float(calc.get('food_cost_real_pct',0)):.2f} %</td></tr>
          <tr><td><b>PVP sugerido sin IVA</b></td><td class='right'>{float(calc.get('suggested_ex_vat',0)):.2f} €</td></tr>
          <tr><td><b>PVP sugerido con IVA</b></td><td class='right'>{float(calc.get('suggested_inc_vat',0)):.2f} €</td></tr>
          <tr><td><b>Coste operativo estimado</b></td><td class='right'>{float(calc.get('operating_cost_total',0)):.2f} €</td></tr>
        </table><div class='muted' style='margin-top:4px;'>Food cost = solo materia prima. Mano de obra se muestra separada.</div>"""

    html = f"""<!doctype html><html><head><meta charset='utf-8'><title>{title}</title>
<style>
  @page {{ size: A4; margin: 14mm; }}
  body {{ font-family: -apple-system,BlinkMacSystemFont,Arial,sans-serif; font-size: 12px; }}
  h1 {{ font-size: 18px; margin: 0 0 6px 0; }} h2 {{ font-size: 14px; margin: 14px 0 6px; }}
  .meta {{ margin: 0 0 10px 0; color: #333; }}
  .meta-header {{ display:flex; gap:10mm; align-items:flex-start; justify-content:space-between; }}
  .meta-main {{ flex:1 1 auto; min-width:0; }}
  .recipe-photo-wrap {{ flex:0 0 42mm; width:42mm; text-align:right; }}
  .recipe-photo {{ width:42mm; height:42mm; object-fit:cover; border:1px solid #999; border-radius:6px; display:block; margin-left:auto; }}
  .tag {{ display:inline-block; padding:2px 6px; border:1px solid #999; border-radius:10px; font-size:11px; margin-right:6px; }}
  table {{ width:100%; border-collapse:collapse; }} th,td {{ border:1px solid #999; padding:6px; }}
  th {{ background:#f2f2f2; text-align:left; }} .right {{ text-align:right; }} .muted {{ color:#666; }}
  .meta-table td {{ border:none; padding:3px 0; }} .warn-text {{ color:#9b2c2c; font-weight:700; }} .price-warning {{ margin:6px 0 0; padding:6px 8px; border:1px solid #d6a54a; background:#fff7df; color:#5d4310; border-radius:6px; font-weight:700; }}
  @media print {{ .print-footer {{ display:block; position:fixed; right:10mm; bottom:6mm; font-size:9px; color:#666; }} }}
  .print-footer {{ display:none; }}
</style></head><body>
  <div class='meta-header'>
    <div class='meta-main'>
      <h1>{title}</h1>
      <div class='meta'>
        <div class='muted'>Código: <b>{code}</b></div>
        <div><span class='tag'>{cat}</span><span class='tag'>{sub}</span></div>
        <div style='margin-top:6px;'><b>Alérgenos:</b> {allergens_txt if allergens_txt else "<span class='muted'>Sin declarar</span>"}</div>
      </div>
    </div>
    {photo_block}
  </div>
  <h2>Ingredientes</h2>
  <table><thead><tr><th>Ingrediente</th><th class='right'>Cantidad</th><th class='right'>Precio usado</th><th class='right'>Coste</th></tr></thead><tbody>{ing_rows}</tbody></table>{missing_price_notice}
  <h2>Elaboración</h2>
  <div style='border:1px solid #999; padding:8px; min-height:40mm;'>{steps}</div>
  {labor_block}
  {costs_block}
  <div class='print-footer'>F&amp;B MAC System · Created by Mauro Ciccarelli</div>
  <div class='muted' style='margin-top:10mm;'>Imprimir / Guardar como PDF (A4)</div>
  <script>window.onload=()=>{{window.print();}}</script>
</body></html>"""
    return HTMLResponse(html)


# ==============================================================================
# CREAR / EDITAR RECETA
# ==============================================================================

@router.post("/recipe/create_form")
def create_recipe_form(
    name: str = Form(...),
    category: str = Form("Otros"),
    is_subrecipe: int = Form(0),
    subcategory: str = Form("Sin definir"),
    yield_final_qty: str = Form("0"),
    yield_final_unit: str = Form("g"),
    waste_pct: float = Form(0),
    contingency_pct: float = Form(5),
    prep_steps: str = Form(""),
    allergens_list: list[str] = Form(default=[]),
    target_food_cost_pct: float = Form(30),
    target_margin_pct: float = Form(70),
    manual_price: float = Form(0),
    prep_time_min: str = Form("0"),
    cook_time_min: str = Form("0"),
    rest_time_min: str = Form("0"),
    labor_people: str = Form("0"),
    labor_hourly_cost: str = Form("0"),
    indirect_sales_base: str = Form("0"),
    indirect_rent_amount: str = Form("0"),
    indirect_rent_tax_mode: str = Form("ex_vat"),
    indirect_services_amount: str = Form("0"),
    indirect_services_tax_mode: str = Form("ex_vat"),
    indirect_admin_amount: str = Form("0"),
    indirect_admin_tax_mode: str = Form("ex_vat"),
    indirect_marketing_amount: str = Form("0"),
    indirect_marketing_tax_mode: str = Form("ex_vat"),
    indirect_other_amount: str = Form("0"),
    indirect_other_tax_mode: str = Form("ex_vat"),
    salary_cost_amount: str = Form("0"),
    cost_supplier_id: str = Form("0"),
    scope_global: Optional[str] = Form(None),
    scope_centers: list[str] = Form(default=[]),
    center_id: int = Form(0),
):
    name = (name or "").strip().upper()
    if not name:
        return RedirectResponse(url=recipe_page_url(center_id=center_id, new=True, err='name', anchor='newRecipePanel'),
                                status_code=303)
    conn = db()
    cur = conn.cursor()
    payload = build_recipe_create_payload(
        cur, name=name, category=category, is_subrecipe=is_subrecipe, subcategory=subcategory,
        yield_final_qty=yield_final_qty, yield_final_unit=yield_final_unit,
        waste_pct=waste_pct, contingency_pct=contingency_pct, prep_steps=prep_steps,
        allergens_list=allergens_list, target_food_cost_pct=target_food_cost_pct,
        target_margin_pct=target_margin_pct, manual_price=manual_price, cost_supplier_id=cost_supplier_id,
        scope_global=scope_global, scope_centers=scope_centers
    )
    dup = cur.execute(f"SELECT id FROM recipes WHERE lower(trim(name))=lower(trim(?)) AND {db_truthy_sql('is_active', cur)}",
                      (name,)).fetchone()
    if dup:
        conn.close()
        return RedirectResponse(url=recipe_page_url(center_id=center_id, new=True, err='dup', anchor='newRecipePanel'),
                                status_code=303)
    sqlite_sql = """INSERT INTO recipes(code,name,category,subcategory,is_subrecipe,yield_final_qty,yield_final_unit,
               waste_pct,contingency_pct,prep_steps,allergens,target_food_cost_pct,target_margin_pct,
               manual_price,suggested_price,cost_supplier_id,scope_global,scope_centers,
               prep_time_min,cook_time_min,rest_time_min,labor_people,labor_hourly_cost,
               indirect_sales_base,indirect_rent_amount,indirect_rent_tax_mode,
               indirect_services_amount,indirect_services_tax_mode,indirect_admin_amount,indirect_admin_tax_mode,
               indirect_marketing_amount,indirect_marketing_tax_mode,indirect_other_amount,indirect_other_tax_mode,
               salary_cost_amount,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"""
    pg_sql = """INSERT INTO recipes(code,name,category,subcategory,is_subrecipe,yield_final_qty,yield_final_unit,
               waste_pct,contingency_pct,prep_steps,allergens,target_food_cost_pct,target_margin_pct,
               manual_price,suggested_price,cost_supplier_id,scope_global,scope_centers,
               prep_time_min,cook_time_min,rest_time_min,labor_people,labor_hourly_cost,
               indirect_sales_base,indirect_rent_amount,indirect_rent_tax_mode,
               indirect_services_amount,indirect_services_tax_mode,indirect_admin_amount,indirect_admin_tax_mode,
               indirect_marketing_amount,indirect_marketing_tax_mode,indirect_other_amount,indirect_other_tax_mode,
               salary_cost_amount,created_at,updated_at)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP) RETURNING id"""
    params = (
        payload['code'], payload['name'], payload['category'], payload['subcategory'], payload['is_subrecipe'],
        payload['yield_final_qty'], payload['yield_final_unit'], payload['waste_pct'], payload['contingency_pct'],
        payload['prep_steps'], payload['allergens'], payload['target_food_cost_pct'],
        payload['target_margin_pct'], payload['manual_price'], 0.0, payload['cost_supplier_id'], payload['scope_global'], payload['scope_centers'],
        _parse_float(prep_time_min,0.0), _parse_float(cook_time_min,0.0), _parse_float(rest_time_min,0.0),
        _parse_float(labor_people,0.0), _parse_float(labor_hourly_cost,0.0),
        _parse_float(indirect_sales_base,0.0), _parse_float(indirect_rent_amount,0.0), _tax_mode_value(indirect_rent_tax_mode),
        _parse_float(indirect_services_amount,0.0), _tax_mode_value(indirect_services_tax_mode),
        _parse_float(indirect_admin_amount,0.0), _tax_mode_value(indirect_admin_tax_mode),
        _parse_float(indirect_marketing_amount,0.0), _tax_mode_value(indirect_marketing_tax_mode),
        _parse_float(indirect_other_amount,0.0), _tax_mode_value(indirect_other_tax_mode),
        _parse_float(salary_cost_amount,0.0)
    )
    rid = safe_insert_returning(cur, sqlite_sql, params, pg_sql=pg_sql) or 0
    conn.commit()
    conn.close()
    return RedirectResponse(url=recipe_page_url(center_id=center_id, recipe_id=rid),
                            status_code=303)


@router.post("/recipe/{recipe_id}/update_form")
def update_recipe_form(
    recipe_id: int,
    name: str = Form(...),
    is_subrecipe: int = Form(0),
    category: str = Form(""),
    subcategory: str = Form(""),
    yield_portions: str = Form("1.0"),
    yield_final_qty: str = Form("0"),
    yield_final_unit: str = Form("g"),
    waste_pct: str = Form("0.0"),
    contingency_pct: str = Form("0.0"),
    prep_steps: str = Form(""),
    allergens_list: list[str] = Form(default=[]),
    target_food_cost_pct: str = Form("0.0"),
    target_margin_pct: str = Form("0.0"),
    manual_price: str = Form("0.0"),
    prep_time_min: str = Form("0"),
    cook_time_min: str = Form("0"),
    rest_time_min: str = Form("0"),
    labor_people: str = Form("0"),
    labor_hourly_cost: str = Form("0"),
    indirect_sales_base: str = Form("0"),
    indirect_rent_amount: str = Form("0"),
    indirect_rent_tax_mode: str = Form("ex_vat"),
    indirect_services_amount: str = Form("0"),
    indirect_services_tax_mode: str = Form("ex_vat"),
    indirect_admin_amount: str = Form("0"),
    indirect_admin_tax_mode: str = Form("ex_vat"),
    indirect_marketing_amount: str = Form("0"),
    indirect_marketing_tax_mode: str = Form("ex_vat"),
    indirect_other_amount: str = Form("0"),
    indirect_other_tax_mode: str = Form("ex_vat"),
    salary_cost_amount: str = Form("0"),
    cost_supplier_id: str = Form("0"),
    scope_global: Optional[str] = Form(None),
    scope_centers: list[str] = Form(default=[]),
    center_id: int = Form(0),
):
    payload = build_recipe_update_payload(
        name=name, is_subrecipe=is_subrecipe, category=category, subcategory=subcategory,
        yield_portions=yield_portions, yield_final_qty=yield_final_qty, yield_final_unit=yield_final_unit,
        waste_pct=waste_pct, contingency_pct=contingency_pct, prep_steps=prep_steps,
        allergens_list=allergens_list, target_food_cost_pct=target_food_cost_pct,
        target_margin_pct=target_margin_pct, manual_price=manual_price, cost_supplier_id=cost_supplier_id,
        scope_global=scope_global, scope_centers=scope_centers
    )
    if not payload['name']:
        return RedirectResponse(
            url=recipe_page_url(center_id=center_id, recipe_id=recipe_id, err='name'),
            status_code=303)

    def _writer(connx, curx):
        curx.execute(
            """UPDATE recipes SET name=?,category=?,subcategory=?,yield_portions=?,yield_final_qty=?,
               yield_final_unit=?,waste_pct=?,contingency_pct=?,prep_steps=?,allergens=?,
               target_food_cost_pct=?,target_margin_pct=?,manual_price=?,is_subrecipe=?,
               cost_supplier_id=?,scope_global=?,scope_centers=?,prep_time_min=?,cook_time_min=?,
               rest_time_min=?,labor_people=?,labor_hourly_cost=?,
               indirect_sales_base=?,indirect_rent_amount=?,indirect_rent_tax_mode=?,
               indirect_services_amount=?,indirect_services_tax_mode=?,indirect_admin_amount=?,indirect_admin_tax_mode=?,
               indirect_marketing_amount=?,indirect_marketing_tax_mode=?,indirect_other_amount=?,indirect_other_tax_mode=?,
               salary_cost_amount=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (payload['name'], payload['category'], payload['subcategory'], payload['yield_portions'], payload['yield_final_qty'], payload['yield_final_unit'],
             payload['waste_pct'], payload['contingency_pct'], payload['prep_steps'], payload['allergens'],
             payload['target_food_cost_pct'], payload['target_margin_pct'], payload['manual_price'],
             payload['is_subrecipe'], payload['cost_supplier_id'], payload['scope_global'], payload['scope_centers'],
             _parse_float(prep_time_min,0.0), _parse_float(cook_time_min,0.0), _parse_float(rest_time_min,0.0),
             _parse_float(labor_people,0.0), _parse_float(labor_hourly_cost,0.0),
             _parse_float(indirect_sales_base,0.0), _parse_float(indirect_rent_amount,0.0), _tax_mode_value(indirect_rent_tax_mode),
             _parse_float(indirect_services_amount,0.0), _tax_mode_value(indirect_services_tax_mode),
             _parse_float(indirect_admin_amount,0.0), _tax_mode_value(indirect_admin_tax_mode),
             _parse_float(indirect_marketing_amount,0.0), _tax_mode_value(indirect_marketing_tax_mode),
             _parse_float(indirect_other_amount,0.0), _tax_mode_value(indirect_other_tax_mode),
             _parse_float(salary_cost_amount,0.0), recipe_id))

    try:
        _retry_db_write(_writer, attempts=8, delay=0.45)
    except Exception as exc:
        if _is_db_locked_error(exc):
            return RedirectResponse(
                url=recipe_page_url(center_id=center_id, recipe_id=recipe_id, err='dblock'),
                status_code=303)
        raise
    return RedirectResponse(
        url=recipe_page_url(center_id=center_id, recipe_id=recipe_id),
        status_code=303)


@router.post("/recipe/{recipe_id}/delete_form")
def delete_recipe_form(recipe_id: int, center_id: int = Form(0)):
    def _writer(connx, curx):
        curx.execute("DELETE FROM recipe_ingredients WHERE recipe_id=?", (int(recipe_id),))
        curx.execute("DELETE FROM recipes WHERE id=?", (int(recipe_id),))
    try:
        _retry_db_write(_writer, attempts=8, delay=0.45)
    except Exception as exc:
        if _is_db_locked_error(exc):
            return RedirectResponse(
                url=f"/?page=recetas&center_id={int(center_id or 0)}&err=dblock#newRecipePanel", status_code=303)
        raise
    return RedirectResponse(
        url=f"/?page=recetas&center_id={int(center_id or 0)}&del_ok=1#newRecipePanel", status_code=303)


# ==============================================================================
# FOTO DE RECETA
# ==============================================================================

@router.post("/recipe/{recipe_id}/upload_photo")
async def upload_recipe_photo(recipe_id: int, request: Request, photo: UploadFile = File(...)):
    form = await request.form()
    center_id = int(form.get("center_id") or request.query_params.get("center_id") or 0)
    if not photo or not (photo.filename or "").strip():
        return RedirectResponse(
            url=f"/?page=recetas&center_id={center_id}&rid={recipe_id}&err=photo#recipePanel", status_code=303)
    uploads_dir = APP_DIR / "static" / "uploads" / "recipes"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    out_name = f"recipe_{int(recipe_id)}_{int(time.time()*1000)}.jpg"
    out_path = uploads_dir / out_name
    old_rel = None
    try:
        data = await photo.read()
        src_name = (photo.filename or "recipe.jpg").strip()
        jpg_name, jpg_bytes = _normalize_uploaded_image_bytes_to_jpeg(src_name, data, quality=90, max_side=1800)
        out_path.write_bytes(jpg_bytes)
    except Exception:
        try:
            if out_path.exists():
                out_path.unlink()
        except Exception:
            pass
        return RedirectResponse(
            url=f"/?page=recetas&center_id={center_id}&rid={recipe_id}&err=photo#recipePanel", status_code=303)
    rel = f"/static/uploads/recipes/{out_name}"

    def _writer(connx, curx):
        nonlocal old_rel
        row = curx.execute("SELECT recipe_photo_path FROM recipes WHERE id=?", (int(recipe_id),)).fetchone()
        old_rel = (row[0] if row else None) or None
        curx.execute("UPDATE recipes SET recipe_photo_path=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (rel, int(recipe_id)))

    try:
        _retry_db_write(_writer, attempts=8, delay=0.45)
    except Exception as exc:
        try:
            if out_path.exists():
                out_path.unlink()
        except Exception:
            pass
        if _is_db_locked_error(exc):
            return RedirectResponse(
                url=f"/?page=recetas&center_id={center_id}&rid={recipe_id}&err=dblock#recipePanel", status_code=303)
        raise
    try:
        if old_rel and str(old_rel).startswith("/static/uploads/recipes/") and str(old_rel) != rel:
            old_path = APP_DIR / str(old_rel).lstrip("/")
            if old_path.exists():
                old_path.unlink()
    except Exception:
        pass
    return RedirectResponse(
        url=f"/?page=recetas&center_id={center_id}&rid={recipe_id}&ok=photo#recipePanel", status_code=303)


@router.post("/recipe/{recipe_id}/remove_photo")
def remove_recipe_photo(recipe_id: int, center_id: int = Form(0)):
    old_rel = None

    def _writer(connx, curx):
        nonlocal old_rel
        row = curx.execute("SELECT recipe_photo_path FROM recipes WHERE id=?", (int(recipe_id),)).fetchone()
        old_rel = (row[0] if row else None) or None
        curx.execute("UPDATE recipes SET recipe_photo_path=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?", (int(recipe_id),))

    try:
        _retry_db_write(_writer, attempts=8, delay=0.45)
    except Exception as exc:
        if _is_db_locked_error(exc):
            return RedirectResponse(
                url=f"/?page=recetas&center_id={int(center_id or 0)}&rid={recipe_id}&err=dblock#recipePanel",
                status_code=303)
        raise
    try:
        if old_rel and str(old_rel).startswith("/static/uploads/recipes/"):
            fpath = APP_DIR / str(old_rel).lstrip("/")
            if fpath.exists():
                fpath.unlink()
    except Exception:
        pass
    return RedirectResponse(
        url=f"/?page=recetas&center_id={int(center_id or 0)}&rid={recipe_id}#recipePanel", status_code=303)


# ==============================================================================
# INGREDIENTES
# ==============================================================================

@router.post("/recipe/{recipe_id}/ingredient/add_form")
def add_recipe_ingredient_form(
    recipe_id: int,
    component_type: str = Form("item"),
    item_id: str = Form(""),
    item_query: str = Form(""),
    subrecipe_id: str = Form(""),
    subrecipe_query: str = Form(""),
    qty_value: str = Form(""),
    qty_unit: str = Form(""),
    waste_pct: str = Form("0"),
    draft_name: str = Form(""),
    draft_category: str = Form(""),
    draft_subcategory: str = Form(""),
    draft_yield_portions: str = Form(""),
    draft_yield_final_qty: str = Form(""),
    draft_yield_final_unit: str = Form("g"),
    draft_waste_pct: str = Form(""),
    draft_contingency_pct: str = Form(""),
    draft_target_food_cost_pct: str = Form(""),
    draft_food_cost_target_pct: str = Form(""),
    draft_target_margin_pct: str = Form(""),
    draft_margin_target_pct: str = Form(""),
    draft_manual_price: str = Form(""),
    draft_price_manual: str = Form(""),
    draft_is_subrecipe: str = Form("0"),
    draft_prep_steps: str = Form(""),
    draft_steps: str = Form(""),
    draft_allergens: str = Form(""),
):
    qty_val = _parse_float(qty_value, 0.0)
    waste_raw = (waste_pct or "").strip()
    w_pct = _parse_float(waste_raw, 0.0)
    if qty_val <= 0:
        return RedirectResponse(url=f"/?page=recetas&rid={recipe_id}&err=qty#recipePanel", status_code=303)

    conn = db()
    cur = conn.cursor()
    item = None
    subrecipe = None
    raw_query = (item_query or "").strip()
    raw_id = str(item_id or "").strip()
    raw_sub_id = str(subrecipe_id or "").strip()
    m = re.search(r"\[#(\d+)\]", raw_query or "")
    parsed_item_id = int(m.group(1)) if m else 0
    clean_query = re.sub(r"\s*\[#\d+\]\s*$", "", raw_query or "").strip()
    component_type = (component_type or "item").strip().lower()

    if component_type == "subrecipe":
        raw_sub_query = str(subrecipe_query or "").strip()
        if raw_sub_id.isdigit() and int(raw_sub_id) > 0:
            subrecipe = cur.execute("SELECT * FROM recipes WHERE id=?", (int(raw_sub_id),)).fetchone()
        if not subrecipe and raw_sub_query:
            subrecipe = cur.execute("SELECT * FROM recipes WHERE is_subrecipe=1 AND lower(name)=lower(?)",
                                    (raw_sub_query,)).fetchone()
        if not subrecipe and raw_sub_query:
            subrecipe = cur.execute(
                "SELECT * FROM recipes WHERE is_subrecipe=1 AND lower(name) LIKE lower(?) ORDER BY name LIMIT 1",
                (f"%{raw_sub_query}%",)).fetchone()
        conn.close()
        if not subrecipe:
            return RedirectResponse(url=f"/?page=recetas&rid={recipe_id}&err=subrecipe#recipePanel", status_code=303)
        yield_unit = (subrecipe["yield_final_unit"] if "yield_final_unit" in subrecipe.keys() else None) or "g"
        base_unit = _canonical_unit(yield_unit)
        # La subreceta entra en la receta final como ingrediente neto ya elaborado.
        # No debe añadir merma del ingrediente ni inflar coste por bruto adicional.
        w_pct = 0.0
        try:
            factor = _unit_factor(qty_unit or (yield_unit or base_unit), base_unit)
        except Exception:
            return RedirectResponse(url=f"/?page=recetas&rid={recipe_id}&err=unit#recipePanel", status_code=303)
        qty_net_input = float(qty_val) * float(factor)
    else:
        if raw_id.isdigit() and int(raw_id) > 0:
            item = cur.execute("SELECT * FROM items WHERE id=?", (int(raw_id),)).fetchone()
        if not item and parsed_item_id > 0:
            item = cur.execute("SELECT * FROM items WHERE id=?", (parsed_item_id,)).fetchone()
        if not item and clean_query:
            item = cur.execute("SELECT * FROM items WHERE lower(name)=lower(?)", (clean_query,)).fetchone()
        if not item and clean_query:
            item = cur.execute("SELECT * FROM items WHERE lower(name) LIKE lower(?) ORDER BY name LIMIT 1",
                               (f"%{clean_query}%",)).fetchone()
        conn.close()
        if not item:
            return RedirectResponse(url=f"/?page=recetas&rid={recipe_id}&err=item#recipePanel", status_code=303)
        resolved_item_unit = _canonical_unit(item["unit"] or "ud")
        try:
            factor = _unit_factor(qty_unit or (item["unit"] or resolved_item_unit), resolved_item_unit)
        except Exception:
            return RedirectResponse(url=f"/?page=recetas&rid={recipe_id}&err=unit#recipePanel", status_code=303)
        if waste_raw == "":
            w_pct = _parse_float(item["waste_default_pct"] if ("waste_default_pct" in item.keys()) else 0, 0.0)
        qty_net_input = float(qty_val) * float(factor)

    waste_factor = max(0.0001, 1 - float(w_pct or 0.0) / 100.0)
    qty_base = qty_net_input / waste_factor if float(w_pct or 0.0) > 0 else qty_net_input
    qty_net = qty_net_input
    if component_type == "subrecipe":
        qty_base = qty_net_input
        qty_net = qty_net_input
        w_pct = 0.0

    def _writer(connx, curx):
        if (draft_name or "").strip():
            yp = _parse_float(draft_yield_portions, 1.0)
            yfq2 = _parse_float(draft_yield_final_qty, 0.0)
            yfu2 = (draft_yield_final_unit or "g").strip().lower() or "g"
            if yfu2 == "kg":
                yfq2 = float(yfq2 or 0) * 1000.0
                yfu2 = "g"
            elif yfu2 not in {"g", "ud"}:
                yfu2 = "g"
            w2 = _parse_float(draft_waste_pct, 0.0)
            cont2 = _parse_float(draft_contingency_pct, 0.0)
            tfc2 = _parse_float(draft_target_food_cost_pct or draft_food_cost_target_pct, 0.0)
            tm2 = _parse_float(draft_target_margin_pct or draft_margin_target_pct, 0.0)
            mp2 = _parse_float(draft_manual_price or draft_price_manual, 0.0)
            steps2 = (draft_prep_steps or draft_steps or "")
            draft_is_sub = 1 if str(draft_is_subrecipe or "0").strip() in {"1", "true", "on", "yes"} else 0
            curx.execute(
                """UPDATE recipes SET name=?,category=?,subcategory=?,yield_portions=?,yield_final_qty=?,
                   yield_final_unit=?,waste_pct=?,contingency_pct=?,prep_steps=?,allergens=?,
                   target_food_cost_pct=?,target_margin_pct=?,manual_price=?,is_subrecipe=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (((draft_name or "").strip().upper()), draft_category, draft_subcategory,
                 float(yp or 1), float(yfq2 or 0), yfu2, float(w2 or 0), float(cont2 or 0),
                 steps2, (draft_allergens or ""), float(tfc2 or 0), float(tm2 or 0),
                 float(mp2 or 0), draft_is_sub, recipe_id))

        if component_type == "subrecipe" and subrecipe is not None:
            curx.execute(
                """INSERT INTO recipe_ingredients(recipe_id,item_id,subrecipe_id,item_name,qty_gross,qty_net,unit,input_unit,waste_pct_ing)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (recipe_id, None, int(subrecipe["id"]), subrecipe["name"],
                 qty_base, qty_net, base_unit, qty_unit or (yield_unit or base_unit), w_pct))
            curx.execute("UPDATE recipes SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (recipe_id,))
        else:
            curx.execute(
                """INSERT INTO recipe_ingredients(recipe_id,item_id,item_name,qty_gross,qty_net,unit,input_unit,waste_pct_ing)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (recipe_id, int(item["id"]), item["name"], qty_base, qty_net,
                 resolved_item_unit, qty_unit or item["unit"] or resolved_item_unit, w_pct))
        curx.execute("UPDATE recipes SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (recipe_id,))

    try:
        _retry_db_write(_writer, attempts=8, delay=0.45)
    except Exception as exc:
        if _is_db_locked_error(exc):
            return RedirectResponse(url=f"/?page=recetas&rid={recipe_id}&err=dblock#recipePanel", status_code=303)
        raise
    return RedirectResponse(url=f"/?page=recetas&rid={recipe_id}&ing_ok=1#recipePanel", status_code=303)


@router.post("/recipe/{recipe_id}/ingredient/{ing_id}/delete_form")
def delete_recipe_ingredient_form(recipe_id: int, ing_id: int):
    def _writer(connx, curx):
        curx.execute("DELETE FROM recipe_ingredients WHERE id=? AND recipe_id=?", (ing_id, recipe_id))
        curx.execute("UPDATE recipes SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (recipe_id,))
    try:
        _retry_db_write(_writer, attempts=8, delay=0.45)
    except Exception as exc:
        if _is_db_locked_error(exc):
            return RedirectResponse(url=f"/?page=recetas&rid={recipe_id}&err=dblock#recipePanel", status_code=303)
        raise
    return RedirectResponse(url=f"/?page=recetas&rid={recipe_id}&ing_ok=1#recipePanel", status_code=303)


@router.post("/recipe/{recipe_id}/ingredient/{ing_id}/update_form")
def update_recipe_ingredient_form(
    recipe_id: int,
    ing_id: int,
    qty_value: str = Form(...),
    qty_unit: str = Form(...),
    waste_pct: str = Form("0"),
):
    qty_val = _parse_float(qty_value, 0.0)
    waste_raw = (waste_pct or "").strip()
    w_pct = _parse_float(waste_raw, 0.0)
    if qty_val <= 0:
        return RedirectResponse(url=f"/?page=recetas&rid={recipe_id}&err=qty#recipePanel", status_code=303)

    conn = db()
    cur = conn.cursor()
    ing = cur.execute(
        "SELECT id,item_id,item_name,unit,subrecipe_id FROM recipe_ingredients WHERE id=? AND recipe_id=?",
        (ing_id, recipe_id)).fetchone()
    if not ing:
        conn.close()
        return RedirectResponse(url=f"/?page=recetas&rid={recipe_id}&err=ing#recipePanel", status_code=303)

    item_id = ing["item_id"]
    item = None
    if item_id is not None:
        item = cur.execute("SELECT id,unit,waste_default_pct FROM items WHERE id=?", (item_id,)).fetchone()
    if not item:
        by_name = (ing["item_name"] or "").strip()
        if by_name:
            item = cur.execute("SELECT id,unit,waste_default_pct FROM items WHERE lower(name)=lower(?)",
                               (by_name,)).fetchone()
    conn.close()

    resolved_item_id = int(item["id"]) if item and item["id"] is not None else None
    if ing["subrecipe_id"]:
        resolved_unit = _canonical_unit(ing["unit"] or qty_unit or "ud")
    else:
        resolved_unit = _canonical_unit(item["unit"] if item and item["unit"] else (ing["unit"] or qty_unit or "ud"))
    try:
        factor = _unit_factor(qty_unit, resolved_unit)
    except Exception:
        return RedirectResponse(url=f"/?page=recetas&rid={recipe_id}&err=unit#recipePanel", status_code=303)

    if waste_raw == "" and item is not None and not ing["subrecipe_id"]:
        w_pct = _parse_float(item["waste_default_pct"] if "waste_default_pct" in item.keys() else 0, 0.0)
    qty_net_input = float(qty_val) * float(factor)
    waste_factor = max(0.0001, 1 - float(w_pct or 0.0) / 100.0)
    qty_base = qty_net_input / waste_factor if float(w_pct or 0.0) > 0 else qty_net_input
    qty_net = qty_net_input
    if ing["subrecipe_id"]:
        # La subreceta editada debe seguir comportándose como ingrediente neto ya elaborado.
        qty_base = qty_net_input
        qty_net = qty_net_input
        w_pct = 0.0

    def _writer(connx, curx):
        if resolved_item_id is not None:
            curx.execute("UPDATE recipe_ingredients SET item_id=? WHERE id=? AND recipe_id=?",
                         (resolved_item_id, ing_id, recipe_id))
        curx.execute(
            "UPDATE recipe_ingredients SET qty_gross=?,qty_net=?,unit=?,input_unit=?,waste_pct_ing=? WHERE id=? AND recipe_id=?",
            (qty_base, qty_net, resolved_unit, qty_unit, w_pct, ing_id, recipe_id))
        curx.execute("UPDATE recipes SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (recipe_id,))

    try:
        _retry_db_write(_writer, attempts=8, delay=0.45)
    except Exception as exc:
        if _is_db_locked_error(exc):
            return RedirectResponse(url=f"/?page=recetas&rid={recipe_id}&err=dblock#recipePanel", status_code=303)
        raise
    return RedirectResponse(url=f"/?page=recetas&rid={recipe_id}&ing_ok=1#recipePanel", status_code=303)


# ==============================================================================
# API RECETAS
# ==============================================================================

@router.post("/api/recipe/create")
@router.post("/api/recipe/new")
def create_recipe_api(
    name: str = Form(...),
    category: str = Form("Otros"),
    subcategory: str = Form("Sin definir"),
    waste_pct: float = Form(0),
    contingency_pct: float = Form(0),
    prep_steps: str = Form(""),
    allergens: str = Form(""),
    target_food_cost_pct: float = Form(30),
    target_margin_pct: float = Form(70),
    manual_price: float = Form(0),
):
    name = (name or "").strip()
    if not name:
        return JSONResponse({"ok": False, "error": "Nombre requerido"}, status_code=400)
    conn = db()
    cur = conn.cursor()
    code = next_recipe_code(cur, category)
    sqlite_sql = """INSERT INTO recipes(code,name,category,subcategory,waste_pct,contingency_pct,
           target_food_cost_pct,target_margin_pct,manual_price,suggested_price,prep_steps,allergens,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"""
    pg_sql = """INSERT INTO recipes(code,name,category,subcategory,waste_pct,contingency_pct,
           target_food_cost_pct,target_margin_pct,manual_price,suggested_price,prep_steps,allergens,created_at,updated_at)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP) RETURNING id"""
    params = (code, name, category, subcategory, waste_pct, contingency_pct, target_food_cost_pct, target_margin_pct, manual_price, 0, prep_steps, allergens)
    rid = safe_insert_returning(cur, sqlite_sql, params, pg_sql=pg_sql) or 0
    conn.commit()
    recipe = recipe_with_calc(cur, int(rid))
    conn.close()
    return {"ok": True, "message": f"Receta creada: {code}", "recipe_id": rid, "code": code, "recipe": recipe}


@router.get("/api/recipe/{recipe_id}")
def get_recipe(recipe_id: int):
    conn = db()
    cur = conn.cursor()
    payload = recipe_with_calc(cur, recipe_id)
    conn.close()
    if not payload:
        return JSONResponse({"ok": False, "error": "Receta no encontrada"}, status_code=404)
    return {"ok": True, "recipe": payload}


@router.post("/api/recipe/{recipe_id}/ingredient")
def add_recipe_ingredient_api(
    recipe_id: int,
    item_id: Optional[str] = Form(None),
    item_query: str = Form(""),
    qty: str = Form(...),
    unit: str = Form(...),
    waste_pct: str = Form("0"),
):
    qty_val = _parse_float(qty, 0.0)
    w_pct = _parse_float(waste_pct, 0.0)
    conn = db()
    cur = conn.cursor()
    resolved_item_id = _resolve_item_id_strict(cur, item_id, item_query)
    if not resolved_item_id:
        conn.close()
        return JSONResponse({"ok": False, "error": "Selecciona un artículo válido"}, status_code=422)
    item = cur.execute("SELECT id,name,unit FROM items WHERE id=?", (int(resolved_item_id),)).fetchone()
    if not item:
        conn.close()
        return JSONResponse({"ok": False, "error": "Artículo no encontrado"}, status_code=404)
    factor = _unit_factor(unit, item["unit"])
    qty_net_input = float(qty_val) * float(factor)
    waste_factor = max(0.0001, 1 - float(w_pct or 0.0) / 100.0)
    qty_base = qty_net_input / waste_factor if float(w_pct or 0.0) > 0 else qty_net_input
    cur.execute(
        "INSERT INTO recipe_ingredients(recipe_id,item_id,item_name,qty_gross,qty_net,unit,input_unit,waste_pct_ing) VALUES(?,?,?,?,?,?,?,?)",
        (recipe_id, int(resolved_item_id), item["name"], qty_base, qty_net_input, item["unit"], unit, float(w_pct)))
    cur.execute("UPDATE recipes SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (recipe_id,))
    conn.commit()
    payload = recipe_with_calc(cur, recipe_id)
    conn.close()
    return {"ok": True, "recipe": payload}


@router.post("/api/recipe/{recipe_id}/pricing")
def update_recipe_pricing(
    recipe_id: int,
    contingency_pct: float = Form(...),
    target_food_cost_pct: float = Form(...),
    target_margin_pct: float = Form(...),
    manual_price: float = Form(...),
):
    conn = db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE recipes SET contingency_pct=?,target_food_cost_pct=?,target_margin_pct=?,manual_price=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (contingency_pct, target_food_cost_pct, target_margin_pct, manual_price, recipe_id))
    conn.commit()
    payload = recipe_with_calc(cur, recipe_id)
    conn.close()
    return {"ok": True, "message": "Costes/venta actualizados", "recipe": payload}
