from __future__ import annotations
import json, re
from typing import Any, Optional

VALID_UNITS = {"g","kg","ud","racion","docena","ml","l"}
VALID_ALLERGENS = {"GLUTEN","CRUSTACEOS","HUEVO","PESCADO","CACAHUETES","SOJA","LECHE","FRUTOS_SECOS","APIO","MOSTAZA","SESAMO","SULFITOS","ALTRAMUCES","MOLUSCOS"}

class RecipeAISchemaError(ValueError):
    pass

def clean_ai_json_response(raw: str) -> dict:
    if not raw or not isinstance(raw, str):
        raise RecipeAISchemaError("Respuesta IA vacía o no textual.")
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise RecipeAISchemaError("No se encontró JSON válido.")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise RecipeAISchemaError(f"JSON IA inválido: {exc}") from exc
    if not isinstance(data, dict):
        raise RecipeAISchemaError("La respuesta IA debe ser objeto JSON.")
    return data

def as_text(v: Any, fallback: str = "") -> str:
    if v is None:
        return fallback
    text = " ".join(str(v).strip().split())
    return text if text else fallback

def as_upper(v: Any, fallback: str = "") -> str:
    return as_text(v, fallback).upper()

def as_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    if isinstance(v, str):
        v = v.replace(",", ".").strip()
    try:
        return float(v)
    except Exception:
        return None

def as_int(v: Any) -> Optional[int]:
    f = as_float(v)
    return None if f is None else int(f)

def as_list(v: Any) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]

def normalize_unit(v: Any) -> Optional[str]:
    if v is None:
        return None
    unit = str(v).strip().lower()
    aliases = {
        "gramo":"g","gramos":"g","gr":"g","kilo":"kg","kilos":"kg","kilogramo":"kg","kilogramos":"kg",
        "unidad":"ud","unidades":"ud","uds":"ud","ración":"racion","raciones":"racion","docenas":"docena",
        "mililitro":"ml","mililitros":"ml","litro":"l","litros":"l",
    }
    unit = aliases.get(unit, unit)
    return unit if unit in VALID_UNITS else None

def note(existing, new):
    existing = as_text(existing)
    if not existing:
        return new
    return existing if new in existing else f"{existing} | {new}"

def normalize_ingredient(raw: Any) -> dict:
    if not isinstance(raw, dict):
        return {"original_text": str(raw), "normalized_name": "INGREDIENTE SIN NOMBRE", "ingredient_type": "ARTICULO", "quantity_net": None, "unit": None, "waste_percent": 0, "quantity_gross": None, "match_status": "PENDIENTE_REVISION", "matched_item_id": None, "matched_item_name": None, "matched_subrecipe_id": None, "matched_subrecipe_name": None, "candidates": [], "needs_admin_validation": True, "notes": "Ingrediente recibido en formato inválido.", "original_quantity": None, "original_unit": None, "conversion_status": "NO_REQUIERE_CONVERSION"}

    unit = normalize_unit(raw.get("unit"))
    qty = as_float(raw.get("quantity_net", raw.get("quantity")))
    status = as_upper(raw.get("match_status"), "PENDIENTE_REVISION")
    conv = as_upper(raw.get("conversion_status"), "NO_REQUIERE_CONVERSION")
    notes = raw.get("notes")

    if unit in {"ml", "l"} and conv == "NO_REQUIERE_CONVERSION":
        conv = "PENDIENTE_CONVERSION_PESO"
    if qty is None or qty <= 0:
        status = "PENDIENTE_REVISION"
        notes = note(notes, "Cantidad pendiente o inválida.")
    if unit is None:
        status = "PENDIENTE_REVISION"
        notes = note(notes, "Unidad pendiente o no reconocida.")

    return {
        "original_text": as_text(raw.get("original_text")),
        "normalized_name": as_upper(raw.get("normalized_name"), "INGREDIENTE SIN NOMBRE"),
        "ingredient_type": as_upper(raw.get("ingredient_type"), "ARTICULO"),
        "quantity_net": qty,
        "unit": unit,
        "waste_percent": max(0, min(as_float(raw.get("waste_percent")) or 0, 99.99)),
        "quantity_gross": as_float(raw.get("quantity_gross")),
        "match_status": status,
        "matched_item_id": as_int(raw.get("matched_item_id")),
        "matched_item_name": as_upper(raw.get("matched_item_name")) if raw.get("matched_item_name") else None,
        "matched_subrecipe_id": as_int(raw.get("matched_subrecipe_id")),
        "matched_subrecipe_name": as_upper(raw.get("matched_subrecipe_name")) if raw.get("matched_subrecipe_name") else None,
        "candidates": [c for c in as_list(raw.get("candidates")) if isinstance(c, dict)],
        "needs_admin_validation": bool(raw.get("needs_admin_validation", True)),
        "notes": notes,
        "original_quantity": as_float(raw.get("original_quantity")),
        "original_unit": normalize_unit(raw.get("original_unit")) if raw.get("original_unit") else None,
        "conversion_status": conv,
    }

def normalize_recipe_ai_payload(data: dict) -> dict:
    if not isinstance(data, dict):
        raise RecipeAISchemaError("Payload no válido.")
    ingredients = [normalize_ingredient(i) for i in as_list(data.get("ingredients")) if i is not None]
    warnings = [as_text(w) for w in as_list(data.get("warnings")) if as_text(w)]
    if not ingredients:
        warnings.append("No se detectaron ingredientes.")
    allergens = []
    for a in as_list(data.get("allergens")):
        x = as_upper(a)
        if x in VALID_ALLERGENS and x not in allergens:
            allergens.append(x)
    import_status = as_upper(data.get("import_status"), "BORRADOR_IA")
    if import_status in {"RECETA_MAESTRA_VALIDADA", "CONVERTIDA_A_RECETA"}:
        import_status = "BORRADOR_IA"
        warnings.append("La IA intentó devolver un estado no permitido. Se dejó como BORRADOR_IA.")
    return {
        "source_type": str(data.get("source_type") or "texto").lower().strip(),
        "recipe_name": as_upper(data.get("recipe_name"), "SIN NOMBRE"),
        "recipe_type": as_upper(data.get("recipe_type"), "RECETA"),
        "category": as_upper(data.get("category"), "OTRO"),
        "subcategory": as_text(data.get("subcategory")) if data.get("subcategory") else None,
        "service_family": as_upper(data.get("service_family"), "OTRO"),
        "yield_quantity": as_float(data.get("yield_quantity")),
        "yield_unit": normalize_unit(data.get("yield_unit")) or "kg",
        "portions": as_int(data.get("portions")),
        "ingredients": ingredients,
        "elaboration_steps": [as_text(s) for s in as_list(data.get("elaboration_steps")) if as_text(s)],
        "allergens": allergens,
        "labor": data.get("labor") if isinstance(data.get("labor"), dict) else {},
        "import_status": import_status,
        "cost_status": as_upper(data.get("cost_status"), "NO_CALCULADO"),
        "confidence": max(0.0, min(as_float(data.get("confidence")) or 0, 1.0)),
        "warnings": warnings,
    }

def parse_and_normalize_ai_response(raw: str) -> dict:
    return normalize_recipe_ai_payload(clean_ai_json_response(raw))
