from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional
from .models import ImportedRecipeDraft, ImportedIngredient, RecipeCostStatus
from .unit_conversion_service import convert_for_cost

@dataclass
class IngredientCostLine:
    ingredient_name: str
    ingredient_type: str
    quantity_net: Optional[float]
    quantity_gross: Optional[float]
    unit: Optional[str]
    matched_item_id: Optional[int]
    matched_item_name: Optional[str]
    matched_subrecipe_id: Optional[int]
    matched_subrecipe_name: Optional[str]
    unit_cost: Optional[float]
    line_cost: Optional[float]
    cost_status: str
    notes: Optional[str] = None
    def to_dict(self) -> dict: return asdict(self)

@dataclass
class RecipeCostPreview:
    recipe_name: str
    total_cost: Optional[float]
    cost_per_portion: Optional[float]
    cost_per_yield_unit: Optional[float]
    portions: Optional[int]
    yield_quantity: Optional[float]
    yield_unit: Optional[str]
    cost_status: str
    lines: list[IngredientCostLine] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    def to_dict(self) -> dict: return asdict(self)

def safe_float(value, default=None):
    if value is None or value == "": return default
    if isinstance(value, str): value = value.strip().replace(",", ".")
    try: return float(value)
    except Exception: return default

def round_money(value): return None if value is None else round(float(value), 4)

def normalize_price_map(price_map):
    out = {}
    for k, v in (price_map or {}).items():
        try: item_id = int(k)
        except Exception: continue
        if isinstance(v, dict):
            out[item_id] = {"name": v.get("name") or v.get("nombre"), "unit_cost": safe_float(v.get("unit_cost", v.get("precio_actual"))), "unit": v.get("unit") or v.get("unidad") or "kg"}
        else:
            out[item_id] = {"name": None, "unit_cost": safe_float(v), "unit": "kg"}
    return out

def normalize_subrecipe_cost_map(data):
    out = {}
    for k, v in (data or {}).items():
        try: sid = int(k)
        except Exception: continue
        if isinstance(v, dict):
            out[sid] = {"name": v.get("name") or v.get("nombre"), "unit_cost": safe_float(v.get("unit_cost", v.get("coste_unitario"))), "unit": v.get("unit") or v.get("unidad") or "kg"}
        else:
            out[sid] = {"name": None, "unit_cost": safe_float(v), "unit": "kg"}
    return out

def _incomplete(ingredient, status, note):
    return IngredientCostLine(ingredient.normalized_name, ingredient.ingredient_type, ingredient.quantity_net, ingredient.quantity_gross, ingredient.unit, ingredient.matched_item_id, ingredient.matched_item_name, ingredient.matched_subrecipe_id, ingredient.matched_subrecipe_name, None, None, status, note)

def calculate_ingredient_cost_line(ingredient: ImportedIngredient, price_map: dict, subrecipe_cost_map: dict) -> IngredientCostLine:
    ingredient.calculate_gross_quantity()
    qty = ingredient.quantity_gross
    if qty is None or qty <= 0:
        return _incomplete(ingredient, RecipeCostStatus.COSTE_NO_CALCULABLE, "Cantidad bruta no calculable.")
    if ingredient.ingredient_type == "SUBRECETA":
        if not ingredient.matched_subrecipe_id: return _incomplete(ingredient, RecipeCostStatus.COSTE_INCOMPLETO, "Subreceta sin vincular.")
        info = subrecipe_cost_map.get(int(ingredient.matched_subrecipe_id))
        if not info or info.get("unit_cost") is None: return _incomplete(ingredient, RecipeCostStatus.COSTE_INCOMPLETO, "Subreceta sin coste unitario.")
        unit_cost, price_unit = info["unit_cost"], info.get("unit") or "kg"
    else:
        if not ingredient.matched_item_id: return _incomplete(ingredient, RecipeCostStatus.COSTE_INCOMPLETO, "Ingrediente nuevo pendiente de alta en Catálogo.")
        info = price_map.get(int(ingredient.matched_item_id))
        if not info or info.get("unit_cost") is None: return _incomplete(ingredient, RecipeCostStatus.COSTE_INCOMPLETO, "Artículo sin precio actual.")
        unit_cost, price_unit = info["unit_cost"], info.get("unit") or "kg"

    conv = convert_for_cost(qty, ingredient.unit, price_unit)
    if not conv.ok():
        line = _incomplete(ingredient, RecipeCostStatus.COSTE_NO_CALCULABLE, conv.notes or "Unidad incompatible.")
        line.unit_cost = round_money(unit_cost)
        return line
    line_cost = conv.converted_quantity * unit_cost

    if ingredient.ingredient_type == "SUBRECETA":
        return IngredientCostLine(
            ingredient.normalized_name,
            ingredient.ingredient_type,
            ingredient.quantity_net,
            conv.converted_quantity,
            conv.converted_unit,
            None,
            None,
            ingredient.matched_subrecipe_id,
            ingredient.matched_subrecipe_name or info.get("name"),
            round_money(unit_cost),
            round_money(line_cost),
            RecipeCostStatus.COSTE_COMPLETO,
        )

    return IngredientCostLine(
        ingredient.normalized_name,
        ingredient.ingredient_type,
        ingredient.quantity_net,
        conv.converted_quantity,
        conv.converted_unit,
        ingredient.matched_item_id,
        ingredient.matched_item_name or info.get("name"),
        None,
        None,
        round_money(unit_cost),
        round_money(line_cost),
        RecipeCostStatus.COSTE_COMPLETO,
    )

def calculate_recipe_cost_preview(draft: ImportedRecipeDraft, price_map: Optional[dict] = None, subrecipe_cost_map: Optional[dict] = None) -> RecipeCostPreview:
    prices = normalize_price_map(price_map)
    subcosts = normalize_subrecipe_cost_map(subrecipe_cost_map)
    if not draft.ingredients:
        return RecipeCostPreview(draft.recipe_name, None, None, None, draft.portions, draft.yield_quantity, draft.yield_unit, RecipeCostStatus.COSTE_NO_CALCULABLE, [], ["El borrador no tiene ingredientes."])
    lines = [calculate_ingredient_cost_line(i, prices, subcosts) for i in draft.ingredients]
    warnings = [f"{l.ingredient_name}: {l.notes or 'coste incompleto'}" for l in lines if l.cost_status != RecipeCostStatus.COSTE_COMPLETO]
    complete = [l for l in lines if l.cost_status == RecipeCostStatus.COSTE_COMPLETO and l.line_cost is not None]
    if not complete:
        status, total = RecipeCostStatus.COSTE_NO_CALCULABLE, None
    else:
        total = round_money(sum(l.line_cost for l in complete))
        status = RecipeCostStatus.COSTE_COMPLETO if len(complete) == len(lines) else RecipeCostStatus.COSTE_INCOMPLETO
    draft.cost_status = status
    return RecipeCostPreview(draft.recipe_name, total, round_money(total / draft.portions) if total and draft.portions else None, round_money(total / draft.yield_quantity) if total and draft.yield_quantity else None, draft.portions, draft.yield_quantity, draft.yield_unit, status, lines, warnings)
