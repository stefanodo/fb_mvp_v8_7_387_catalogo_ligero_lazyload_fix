from __future__ import annotations

import json
from app.core import ensure_columns, _parse_float
from app.productions_panel import create_batch_productions
from app.services.productions_create_service import load_recipe_into_production


def parse_batch_payload(batch_payload: str = "") -> tuple[list[int], dict[int, dict]]:
    try:
        payload = json.loads(batch_payload or "[]")
    except Exception:
        payload = []
    clean_ids = []
    batch_specs: dict[int, dict] = {}
    for row in (payload or []):
        try:
            rid = int(row.get("recipe_id") or 0)
        except Exception:
            rid = 0
        if rid <= 0:
            continue
        qty = _parse_float(str(row.get("qty", "1")), 1.0)
        if qty <= 0:
            qty = 1.0
        unit = (str(row.get("unit", "lotes")) or "lotes").strip() or "lotes"
        grp = (str(row.get("group", "Otros")) or "Otros").strip() or "Otros"
        clean_ids.append(rid)
        batch_specs[rid] = {"qty": float(qty), "unit": unit, "group": grp}
    return clean_ids, batch_specs



def create_batch_drafts(cur, center_id: int, warehouse_id: int, batch_payload: str = "", append_production_id: int | None = None) -> list[int]:
    ensure_columns(cur)
    clean_ids, batch_specs = parse_batch_payload(batch_payload)
    if not clean_ids:
        return []

    if append_production_id:
        p = cur.execute("SELECT id,status,center_id,warehouse_id FROM productions WHERE id=?", (int(append_production_id),)).fetchone()
        if p and p["status"] == "DRAFT":
            loaded = 0
            for rid in clean_ids:
                spec = batch_specs.get(int(rid), {}) or {}
                result = load_recipe_into_production(
                    cur,
                    int(append_production_id),
                    recipe_id=str(rid),
                    recipe_query="",
                    multiplier=str(spec.get("qty", 1)),
                    target_unit=str(spec.get("unit", "lotes")),
                    append_note=True,
                )
                if result:
                    loaded += 1
            return [int(append_production_id)] if loaded > 0 else []

    return create_batch_productions(cur, int(center_id), int(warehouse_id), clean_ids, batch_specs)
