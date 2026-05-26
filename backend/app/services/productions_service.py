from app.core import _parse_float, _resolve_item_id, _unit_factor
from app.services.productions_redirect_service import production_redirect_url


def get_draft_production(cur, production_id: int):
    return cur.execute("SELECT status,center_id FROM productions WHERE id=?", (production_id,)).fetchone()


def resolve_line_payload(cur, *, item_id: str, item_query: str, qty_value: str, qty_unit: str):
    resolved_item_id = _resolve_item_id(cur, item_id, item_query)
    if not resolved_item_id:
        return None
    item = cur.execute("SELECT unit FROM items WHERE id=?", (int(resolved_item_id),)).fetchone()
    if not item:
        return None
    base_unit = item["unit"]
    iu = (qty_unit or base_unit).strip() or base_unit
    factor = _unit_factor(iu, base_unit)
    qty_input = _parse_float(qty_value, 0.0)
    qty_base = float(qty_input) * float(factor)
    return {
        "item_id": int(resolved_item_id),
        "base_unit": base_unit,
        "input_unit": iu,
        "qty_input": float(qty_input),
        "qty_base": float(qty_base),
    }
