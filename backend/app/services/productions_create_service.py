from datetime import datetime
from collections import OrderedDict

from app.core import _parse_float, _resolve_recipe_id, _canonical_unit, _convert_qty, _collect_recipe_production_inputs, _merge_or_insert_production_line, _unit_factor


def _parse_charge_summary(note: str = "") -> OrderedDict[str, int]:
    out: OrderedDict[str, int] = OrderedDict()
    for raw in [x.strip() for x in str(note or '').split(' + ') if x.strip()]:
        if '·' in raw:
            name, rhs = [x.strip() for x in raw.split('·', 1)]
            m = rhs.lower()
            digits = ''.join(ch for ch in m if (ch.isdigit() or ch == '.'))
            try:
                qty = int(float(digits)) if digits else 1
            except Exception:
                qty = 1
            out[name] = max(1, int(qty))
        else:
            out[raw] = out.get(raw, 0) + 1
    return out


def _build_charge_summary(parts: OrderedDict[str, int]) -> str:
    pieces = []
    for name, qty in parts.items():
        n = max(1, int(qty or 1))
        suffix = 'carga' if n == 1 else 'cargas'
        pieces.append(f"{name} · {n} {suffix}")
    return ' + '.join(pieces)


def create_draft_production(cur, center_id: int, warehouse_id: int, note: str = "", production_group: str = "Otros") -> int:
    wh = cur.execute("SELECT center_id FROM warehouses WHERE id=?", (int(warehouse_id),)).fetchone()
    if not wh or int(wh['center_id'] or 0) != int(center_id or 0):
        raise ValueError(f'warehouse_id={warehouse_id} no pertenece a center_id={center_id}')
    now = datetime.utcnow().isoformat()
    cur.execute(
        "INSERT INTO productions(center_id,warehouse_id,status,created_at,note,production_group) VALUES(?,?,'DRAFT',?,?,?)",
        (center_id, warehouse_id, now, (note or "").strip(), (production_group or "Otros").strip() or "Otros"),
    )
    return int(cur.lastrowid)


def load_recipe_into_production(cur, production_id: int, recipe_id: str = "", recipe_query: str = "", multiplier: str = "1", target_unit: str = "lotes", append_note: bool = True) -> dict | None:
    p = cur.execute("SELECT status,center_id,note FROM productions WHERE id=?", (production_id,)).fetchone()
    if not p or p["status"] != "DRAFT":
        return None

    mult = _parse_float(multiplier, 1.0)
    if mult <= 0:
        mult = 1.0

    resolved_recipe_id = _resolve_recipe_id(cur, recipe_id, recipe_query)
    rec = cur.execute(
        "SELECT id,name,code,yield_portions,yield_final_qty,yield_final_unit,COALESCE(produced_item_id,0) produced_item_id FROM recipes WHERE id=?",
        (int(resolved_recipe_id or 0),),
    ).fetchone() if resolved_recipe_id else None
    if not rec:
        return None

    rec_yield_portions = float(rec["yield_portions"] or 0.0)
    rec_yield_final_qty = float(rec["yield_final_qty"] or 0.0)
    rec_yield_final_unit = (rec["yield_final_unit"] or "").strip().lower()
    rec_yield_canonical_unit = _canonical_unit(rec_yield_final_unit) if rec_yield_final_unit else ""
    rec_yield_final_canonical = 0.0
    if rec_yield_final_qty > 0 and rec_yield_final_unit:
        try:
            rec_yield_final_canonical = float(_convert_qty(rec_yield_final_qty, rec_yield_final_unit, rec_yield_canonical_unit))
        except Exception:
            rec_yield_final_canonical = 0.0

    raw_target_unit = (target_unit or "lotes").strip().lower() or "lotes"
    target_unit_canon = _canonical_unit(raw_target_unit)
    objective_label = f"{mult:g} {raw_target_unit}"

    if raw_target_unit == "lotes":
        scale_factor = float(mult)
    elif raw_target_unit in {"racion", "raciones", "porcion", "porciones"}:
        scale_factor = float(mult) / rec_yield_portions if rec_yield_portions > 0 else float(mult)
    elif raw_target_unit in {"g", "kg", "ud"}:
        if rec_yield_final_canonical > 0 and rec_yield_canonical_unit:
            desired_canonical = float(_convert_qty(mult, raw_target_unit, rec_yield_canonical_unit))
            scale_factor = desired_canonical / rec_yield_final_canonical
        else:
            scale_factor = float(mult)
    elif rec_yield_portions > 1:
        scale_factor = float(mult) / rec_yield_portions
        objective_label = f"{mult:g} raciones"
    elif rec_yield_final_canonical > 0 and rec_yield_canonical_unit in {"g", "kg"}:
        entry_unit = "kg" if rec_yield_canonical_unit == "g" and rec_yield_final_canonical >= 1000 else (
            "kg" if rec_yield_final_canonical >= 1000 else "g"
        )
        desired_canonical = float(_convert_qty(mult, entry_unit, rec_yield_canonical_unit))
        scale_factor = desired_canonical / rec_yield_final_canonical if rec_yield_final_canonical > 0 else float(mult)
        objective_label = f"{mult:g} {entry_unit}"
    else:
        scale_factor = float(mult)

    if scale_factor <= 0:
        scale_factor = 1.0

    collected_lines, _ = _collect_recipe_production_inputs(cur, int(resolved_recipe_id), float(scale_factor))
    added = 0
    for ln in collected_lines:
        _merge_or_insert_production_line(
            cur, production_id, "OUT", int(ln["item_id"]), float(ln["qty_base"]), str(ln["input_unit"] or "ud"), float(ln["qty_input"]),
        )
        added += 1

    # Salida del elaborado: primero usar el vínculo formal recipes.produced_item_id.
    # Si no existe, caer al nombre de receta para mantener compatibilidad con bases antiguas.
    result_item = None
    try:
        produced_item_id = int(rec["produced_item_id"] or 0)
    except Exception:
        produced_item_id = 0
    if produced_item_id > 0:
        result_item = cur.execute("SELECT id,unit FROM items WHERE id=?", (produced_item_id,)).fetchone()
    if not result_item:
        result_item = cur.execute(
            "SELECT id,unit FROM items WHERE lower(trim(name))=lower(trim(?)) ORDER BY id LIMIT 1",
            ((rec["name"] or '').strip(),),
        ).fetchone()
    explicit_output_units = {"g", "kg", "ud", "racion", "raciones", "porcion", "porciones"}
    if raw_target_unit in explicit_output_units:
        result_qty = float(mult)
        result_unit = raw_target_unit
    else:
        result_qty = float(rec["yield_final_qty"] or 0.0) * float(scale_factor)
        result_unit = (rec["yield_final_unit"] or '').strip() or (result_item["unit"] if result_item else '')
    if result_item and result_qty > 0 and result_unit:
        result_base_unit = (result_item["unit"] or 'ud').strip() or 'ud'
        result_factor = _unit_factor(result_unit, result_base_unit)
        result_qty_base = result_qty * result_factor if result_factor else result_qty
        result_qty_input = result_qty
        _merge_or_insert_production_line(cur, production_id, "IN", int(result_item["id"]), result_qty_base, result_unit, result_qty_input)

    if added <= 0:
        return None

    recipe_name = (rec["name"] or "").strip()
    clean_note = (p["note"] or "").strip()
    if append_note and recipe_name:
        parts = _parse_charge_summary(clean_note)
        parts[recipe_name] = int(parts.get(recipe_name, 0)) + 1
        clean_note = _build_charge_summary(parts)

    cur.execute("UPDATE productions SET note=? WHERE id=?", (clean_note, production_id))
    return {"center_id": p["center_id"], "recipe_id": int(rec["id"]), "added": added, "note": clean_note}
