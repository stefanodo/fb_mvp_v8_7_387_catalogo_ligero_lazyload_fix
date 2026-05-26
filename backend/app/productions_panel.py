from __future__ import annotations
from app.services.productions_create_service import create_draft_production
from datetime import datetime


def create_batch_productions(cur, center_id: int, warehouse_id: int,
                              recipe_ids: list[int], batch_specs: dict[int, dict]) -> list[int]:
    """
    Crea borradores de producción en lote, uno por receta seleccionada.
    Carga automáticamente los ingredientes de cada receta según la cantidad
    y unidad especificadas (raciones, kg, lotes, etc.).
    """
    from app.core import (
        _parse_float, _canonical_unit, _convert_qty,
        _collect_recipe_production_inputs, _merge_or_insert_production_line,
        _unit_factor,
    )

    created_ids: list[int] = []

    for recipe_id in recipe_ids:
        rec = cur.execute(
            "SELECT id,name,yield_portions,yield_final_qty,yield_final_unit FROM recipes WHERE id=?",
            (int(recipe_id),)
        ).fetchone()
        if not rec:
            continue

        spec  = batch_specs.get(int(recipe_id), {}) or {}
        qty   = float(spec.get("qty") or 1.0)
        unit  = (spec.get("unit") or "lotes").strip() or "lotes"
        group = (spec.get("group") or "Otros").strip() or "Otros"

        # Calcular scale_factor igual que load_recipe_form
        raw_target_unit = (unit or 'lotes').strip().lower() or 'lotes'
        target_unit = _canonical_unit(raw_target_unit)
        rec_yield_portions   = float(rec["yield_portions"]   or 0.0)
        rec_yield_final_qty  = float(rec["yield_final_qty"]  or 0.0)
        rec_yield_final_unit = (rec["yield_final_unit"] or "").strip().lower()
        rec_yield_canonical  = _canonical_unit(rec_yield_final_unit) if rec_yield_final_unit else ""
        rec_yield_canonical_qty = 0.0
        if rec_yield_final_qty > 0 and rec_yield_final_unit:
            try:
                rec_yield_canonical_qty = float(_convert_qty(rec_yield_final_qty, rec_yield_final_unit, rec_yield_canonical))
            except Exception:
                rec_yield_canonical_qty = 0.0

        if raw_target_unit == "lotes":
            scale_factor = float(qty)
        elif raw_target_unit in {"racion", "raciones", "porcion", "porciones"}:
            scale_factor = float(qty) / rec_yield_portions if rec_yield_portions > 0 else float(qty)
        elif target_unit in {"g", "kg", "ud"}:
            if rec_yield_canonical_qty > 0 and rec_yield_canonical:
                desired = float(_convert_qty(qty, target_unit, rec_yield_canonical))
                scale_factor = desired / rec_yield_canonical_qty
            else:
                scale_factor = float(qty)
        else:
            scale_factor = float(qty)

        if scale_factor <= 0:
            scale_factor = 1.0

        objective_label = f"{qty:g} {unit}"
        note = f"{(rec['name'] or '').strip()} · {objective_label}".strip(" ·")

        production_id = create_draft_production(
            cur, int(center_id), int(warehouse_id), note=note, production_group=group
        )

        # Cargar ingredientes automáticamente
        try:
            lines, _ = _collect_recipe_production_inputs(cur, int(recipe_id), float(scale_factor))
            for ln in lines:
                _merge_or_insert_production_line(
                    cur, production_id, "OUT",
                    int(ln["item_id"]), float(ln["qty_base"]),
                    str(ln["input_unit"] or "ud"), float(ln["qty_input"]),
                )

            # Auto-crear línea resultado (IN) si hay artículo con mismo nombre
            result_item = cur.execute(
                "SELECT id,unit FROM items WHERE lower(trim(name))=lower(trim(?)) ORDER BY id LIMIT 1",
                ((rec["name"] or '').strip(),)
            ).fetchone()
            explicit_output_units = {"g", "kg", "ud", "racion", "raciones", "porcion", "porciones"}
            if raw_target_unit in explicit_output_units:
                result_qty = float(qty)
                result_unit = raw_target_unit
            else:
                result_qty  = rec_yield_final_qty * scale_factor
                result_unit = rec_yield_final_unit
            if result_item and result_qty > 0 and result_unit:
                result_base = (result_item["unit"] or 'ud').strip()
                factor = _unit_factor(result_unit, result_base)
                qty_base_r  = result_qty * factor if factor else result_qty
                qty_input_r = result_qty
                _merge_or_insert_production_line(
                    cur, production_id, "IN",
                    int(result_item["id"]), qty_base_r, result_unit, qty_input_r
                )
        except Exception as e:
            # Si falla la carga de ingredientes, el borrador queda vacío (no falla el batch entero)
            import traceback
            print(f"BATCH_WARN production {production_id}: {e}")

        created_ids.append(production_id)

    return created_ids
