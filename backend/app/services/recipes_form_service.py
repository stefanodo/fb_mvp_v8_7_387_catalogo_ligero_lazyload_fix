from __future__ import annotations

from app.core import _parse_scope, _parse_float
from app.services.units_service import canonical_unit


def recipe_page_url(*, center_id:int=0, recipe_id:int|None=None, new:bool=False, ok:str|None=None, err:str|None=None, anchor:str='recipePanel') -> str:
    params = [f"page=recetas", f"center_id={int(center_id or 0)}"]
    if recipe_id is not None:
        params.append(f"rid={int(recipe_id)}")
    if new:
        params.append('new=1')
    if ok:
        params.append(f"ok={ok}")
    if err:
        params.append(f"err={err}")
    return f"/?{'&'.join(params)}#{anchor}"


def build_recipe_update_payload(*, name:str, is_subrecipe:int, category:str, subcategory:str,
                                yield_portions:str, yield_final_qty:str, yield_final_unit:str,
                                waste_pct:str, contingency_pct:str, prep_steps:str,
                                allergens_list:list[str], target_food_cost_pct:str,
                                target_margin_pct:str, manual_price:str, cost_supplier_id:str,
                                scope_global, scope_centers:list[str]):
    name = (name or '').strip().upper()
    yp = _parse_float(yield_portions, 1.0)
    yfq = _parse_float(yield_final_qty, 0.0)
    raw_yfu = (yield_final_unit or 'g').strip().lower() or 'g'
    if raw_yfu in {'kg', 'kilo', 'kilos', 'l', 'lt', 'lts', 'litro', 'litros'}:
        yfq = float(yfq or 0) * 1000.0
        yfu = 'g'
    elif raw_yfu in {'ml'}:
        yfu = 'g'
    else:
        yfu = canonical_unit(raw_yfu)
        if yfu not in {'g', 'ud'}:
            yfu = 'g'
    cs = int(cost_supplier_id) if str(cost_supplier_id).isdigit() and int(cost_supplier_id) > 0 else None
    sg, sc = _parse_scope(scope_global, scope_centers)
    allergens = ', '.join([a.strip() for a in allergens_list if a and a.strip()])
    return {
        'name': name,
        'category': category,
        'subcategory': subcategory,
        'yield_portions': float(yp or 1),
        'yield_final_qty': float(yfq or 0),
        'yield_final_unit': yfu,
        'waste_pct': float(_parse_float(waste_pct, 0.0) or 0),
        'contingency_pct': float(_parse_float(contingency_pct, 0.0) or 0),
        'prep_steps': (prep_steps or '').strip(),
        'allergens': allergens,
        'target_food_cost_pct': float(_parse_float(target_food_cost_pct, 0.0) or 0),
        'target_margin_pct': float(_parse_float(target_margin_pct, 0.0) or 0),
        'manual_price': float(_parse_float(manual_price, 0.0) or 0),
        'is_subrecipe': int(1 if int(is_subrecipe or 0) == 1 else 0),
        'cost_supplier_id': cs,
        'scope_global': sg,
        'scope_centers': sc,
    }
