from __future__ import annotations
from typing import Optional

SYSTEM_MAC_ALLERGENS = ["GLUTEN","CRUSTACEOS","HUEVO","PESCADO","CACAHUETES","SOJA","LECHE","FRUTOS_SECOS","APIO","MOSTAZA","SESAMO","SULFITOS","ALTRAMUCES","MOLUSCOS"]
SYSTEM_MAC_CATEGORIES = ["ENTRANTE","PRINCIPAL","POSTRE","GUARNICION","SALSA","BEBIDA","ELABORACION_BASE","OTRO"]
SYSTEM_MAC_SERVICE_FAMILIES = ["CALIENTES","FRIOS","BEBIDAS","REPOSTERIA","PASTELERIA","SALSAS","MISE_EN_PLACE","OTRO"]

def build_catalog_block(catalog_items: Optional[list[dict]] = None, limit: int = 500) -> str:
    if not catalog_items:
        return "\n--- CATÁLOGO ACTUAL ---\nSin catálogo cargado. Marca ingredientes como PENDIENTE_ALTA.\n-----------------------"
    lines = []
    for item in catalog_items[:limit]:
        item_id = item.get("id") or item.get("item_id")
        name = item.get("name") or item.get("nombre")
        if item_id and name:
            lines.append(f"ID {item_id} - {str(name).upper()}")
    return "\n--- CATÁLOGO ACTUAL ---\n" + "\n".join(lines) + "\n-----------------------"

def build_subrecipe_block(subrecipes: Optional[list[dict]] = None, limit: int = 300) -> str:
    if not subrecipes:
        return "\n--- SUBRECETAS ACTUALES ---\nSin subrecetas cargadas.\n--------------------------"
    lines = []
    for item in subrecipes[:limit]:
        subrecipe_id = item.get("id") or item.get("subrecipe_id")
        name = item.get("name") or item.get("nombre")
        if subrecipe_id and name:
            lines.append(f"ID {subrecipe_id} - {str(name).upper()}")
    return "\n--- SUBRECETAS ACTUALES ---\n" + "\n".join(lines) + "\n--------------------------"

def build_recipe_import_prompt(catalog_items: Optional[list[dict]] = None, subrecipes: Optional[list[dict]] = None, source_type: str = "texto") -> str:
    return f"""
Eres un extractor profesional de recetas para System MAC, un sistema F&B multi-restaurante.

Origen: {source_type}.

OBJETIVO:
Transformar una receta escrita, dictada, fotografiada, manuscrita o transcrita en JSON para crear un BORRADOR_IA.

REGLAS CRÍTICAS:
1. No inventes ingredientes, cantidades, unidades, pasos, rendimiento ni raciones.
2. Si un dato no es claro, usa null y añade warning.
3. La receta importada nunca es oficial hasta validación humana.
4. Normaliza nombres de ingredientes en MAYÚSCULAS.
5. Conserva original_text por ingrediente.
6. System MAC prioriza kg/g también para líquidos.
7. Si aparece ml/l y no hay conversión segura a peso, marca conversion_status = PENDIENTE_CONVERSION_PESO.
8. quantity_net representa la cantidad útil indicada.
9. quantity_gross no debe inventarse.
10. Si aparece merma explícita, usa waste_percent; si no, usa 0.
11. Diferencia ARTICULO y SUBRECETA.
12. Si no existe en catálogo, usa PENDIENTE_ALTA.
13. Si falta cantidad, unidad o nombre claro, usa PENDIENTE_REVISION.
14. Devuelve SOLO JSON válido. Sin explicación fuera del JSON.

ALÉRGENOS PERMITIDOS:
{", ".join(SYSTEM_MAC_ALLERGENS)}

CATEGORÍAS PERMITIDAS:
{", ".join(SYSTEM_MAC_CATEGORIES)}

FAMILIAS DE SERVICIO PERMITIDAS:
{", ".join(SYSTEM_MAC_SERVICE_FAMILIES)}

ESTADOS DE INGREDIENTE:
VINCULADO_CATALOGO, COINCIDENCIA_SUGERIDA, PENDIENTE_ALTA, PENDIENTE_REVISION, UNIDAD_INCOMPATIBLE, SUBRECETA_PENDIENTE

{build_catalog_block(catalog_items)}
{build_subrecipe_block(subrecipes)}

FORMATO JSON:
{{
  "source_type": "{source_type}",
  "recipe_name": "NOMBRE EN MAYÚSCULAS O SIN NOMBRE",
  "recipe_type": "RECETA",
  "category": "ENTRANTE|PRINCIPAL|POSTRE|GUARNICION|SALSA|BEBIDA|ELABORACION_BASE|OTRO",
  "subcategory": null,
  "service_family": "CALIENTES|FRIOS|BEBIDAS|REPOSTERIA|PASTELERIA|SALSAS|MISE_EN_PLACE|OTRO",
  "yield_quantity": null,
  "yield_unit": "kg",
  "portions": null,
  "ingredients": [
    {{
      "original_text": "texto original",
      "normalized_name": "NOMBRE NORMALIZADO",
      "ingredient_type": "ARTICULO",
      "quantity_net": null,
      "unit": null,
      "waste_percent": 0,
      "quantity_gross": null,
      "match_status": "PENDIENTE_REVISION",
      "matched_item_id": null,
      "matched_item_name": null,
      "matched_subrecipe_id": null,
      "matched_subrecipe_name": null,
      "candidates": [],
      "needs_admin_validation": true,
      "notes": null,
      "original_quantity": null,
      "original_unit": null,
      "conversion_status": "NO_REQUIERE_CONVERSION"
    }}
  ],
  "elaboration_steps": [],
  "allergens": [],
  "labor": {{"prep_time_minutes":0,"cook_time_minutes":0,"rest_time_minutes":0,"people":1,"hourly_cost":14,"labor_cost":0}},
  "import_status": "BORRADOR_IA",
  "cost_status": "NO_CALCULADO",
  "confidence": 0.0,
  "warnings": []
}}
"""

def build_voice_cleanup_prompt() -> str:
    return (
        "IDIOMA OBLIGATORIO: español. Limpia la transcripción de voz de una receta sin inventar datos. "
        "No traduzcas productos ni elaboraciones al inglés. Si la transcripción trae sesgos en inglés, conviértelos al español operativo cuando sea evidente: production=producción, waste=merma, tomato=tomate, order=pedido. "
        "Ordena en nombre, rendimiento, ingredientes, elaboración y dudas. Devuelve solo texto limpio en español."
    )

def build_voice_response_prompt() -> str:
    return "Responde por voz en español, de forma breve y operativa. No valides recetas maestras sin revisión humana."
