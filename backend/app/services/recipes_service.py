from typing import Optional, Sequence

from app.core import db, recipe_with_calc, recipe_visible_in_center, next_recipe_code, _parse_scope, _parse_float
from app.services.units_service import canonical_unit


def get_recipe_detail(recipe_id: int, center_id: Optional[int] = None):
    conn = db()
    cur = conn.cursor()
    detail = recipe_with_calc(cur, int(recipe_id))
    conn.close()
    if detail and not recipe_visible_in_center(detail, center_id):
        return None
    return detail


def normalize_recipe_yield_input(yield_final_qty, yield_final_unit: str):
    """Normalize recipe final yield to the stored base unit.

    The canonical unit helper intentionally maps kg/l/ml to g because the system
    stores weight-like recipe yields in grams. The previous implementation
    canonicalized first and therefore lost the original "kg" signal, storing
    2 kg as 2 g. This guard converts the numeric value before canonicalization.
    """
    yfq = _parse_float(yield_final_qty, 0.0)
    raw_unit = (yield_final_unit or 'g').strip().lower() or 'g'
    if raw_unit in {'kg', 'kilo', 'kilos', 'l', 'lt', 'lts', 'litro', 'litros'}:
        return float(yfq or 0.0) * 1000.0, 'g'
    if raw_unit in {'ml'}:
        return float(yfq or 0.0), 'g'
    yfu = canonical_unit(raw_unit)
    if yfu not in {'g', 'ud'}:
        yfu = 'g'
    return float(yfq or 0.0), yfu


def build_recipe_create_payload(cur, *, name: str, category: str, is_subrecipe: int, subcategory: str,
                                yield_final_qty, yield_final_unit: str, waste_pct: float, contingency_pct: float,
                                prep_steps: str, allergens_list: Sequence[str], target_food_cost_pct: float,
                                target_margin_pct: float, manual_price: float, cost_supplier_id: str,
                                scope_global: Optional[str], scope_centers: Sequence[str]):
    allergens = ', '.join([a.strip() for a in allergens_list if a and a.strip()])
    yfq, yfu = normalize_recipe_yield_input(yield_final_qty, yield_final_unit)
    cs = int(cost_supplier_id) if str(cost_supplier_id).isdigit() and int(cost_supplier_id) > 0 else None
    sg, sc = _parse_scope(scope_global, scope_centers)
    code = next_recipe_code(cur, category)
    return {
        'code': code, 'name': name, 'category': category, 'subcategory': subcategory,
        'is_subrecipe': int(1 if int(is_subrecipe or 0) == 1 else 0), 'yield_final_qty': yfq, 'yield_final_unit': yfu,
        'waste_pct': float(waste_pct or 0), 'contingency_pct': float(contingency_pct or 0),
        'prep_steps': (prep_steps or '').strip(), 'allergens': allergens,
        'target_food_cost_pct': float(target_food_cost_pct or 0), 'target_margin_pct': float(target_margin_pct or 0),
        'manual_price': float(manual_price or 0), 'cost_supplier_id': cs,
        'scope_global': sg, 'scope_centers': sc
    }
