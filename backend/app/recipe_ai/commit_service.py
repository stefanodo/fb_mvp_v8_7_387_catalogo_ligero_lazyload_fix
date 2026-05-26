from __future__ import annotations
import json, sqlite3, os, time
from typing import Optional
from .models import ImportedRecipeDraft, RecipeImportStatus, RecipeCostStatus
from .storage_service import get_connection, get_imported_recipe_draft, update_draft_status, add_audit_log, row_to_dict

class RecipeCommitResult:
    def __init__(self, ok: bool, recipe_id: Optional[int] = None, errors: Optional[list[str]] = None, warnings: Optional[list[str]] = None):
        self.ok, self.recipe_id, self.errors, self.warnings = ok, recipe_id, errors or [], warnings or []
    def to_dict(self) -> dict: return {"ok": self.ok, "recipe_id": self.recipe_id, "errors": self.errors, "warnings": self.warnings}

def table_exists(conn, table_name):
    return conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None

def detect_real_recipe_tables(conn):
    for c in [{"recipes":"recipes","ingredients":"recipe_ingredients"},{"recipes":"recetas","ingredients":"receta_ingredientes"},{"recipes":"fichas_tecnicas","ingredients":"ficha_tecnica_ingredientes"}]:
        if table_exists(conn, c["recipes"]) and table_exists(conn, c["ingredients"]): return c
    return {"recipes": None, "ingredients": None}

def validate_draft_before_commit(draft: ImportedRecipeDraft) -> list[str]:
    errors = []
    if draft.import_status != RecipeImportStatus.VALIDADA_PARA_CONVERTIR: errors.append("El borrador no está VALIDADA_PARA_CONVERTIR.")
    if draft.has_critical_pending(): errors.append("Hay ingredientes pendientes.")
    if not draft.recipe_name or draft.recipe_name == "SIN NOMBRE": errors.append("Nombre pendiente.")
    if not draft.yield_quantity or draft.yield_quantity <= 0: errors.append("Rendimiento pendiente.")
    if draft.cost_status not in {RecipeCostStatus.COSTE_COMPLETO, RecipeCostStatus.COSTE_ESTIMADO}: errors.append("Coste no completo/estimado.")
    for idx, ing in enumerate(draft.ingredients, 1):
        if ing.ingredient_type == "ARTICULO" and not ing.matched_item_id: errors.append(f"Línea {idx}: {ing.normalized_name} sin Catálogo.")
        if ing.ingredient_type == "SUBRECETA" and not ing.matched_subrecipe_id: errors.append(f"Línea {idx}: {ing.normalized_name} sin subreceta.")
    return errors

def get_table_columns(conn, table_name): return {r["name"] for r in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
def maybe_set(values, columns, name, value):
    if name in columns: values[name] = value

def _to_float(value, default=0.0):
    try:
        return float(value if value is not None else default)
    except Exception:
        return default


def _yield_to_internal_qty(qty, unit):
    q = _to_float(qty, 0.0)
    u = (unit or 'g').strip().lower()
    if u in {'kg', 'kilo', 'kilos'}:
        return q * 1000.0, 'g'
    if u in {'l', 'lt', 'litro', 'litros'}:
        return q * 1000.0, 'g'
    if u in {'ml'}:
        return q, 'g'
    return q, unit or 'g'


def insert_header(conn, table, draft, actor=None):
    cols, values = get_table_columns(conn, table), {}
    code = f"IA-{int(time.time())}"
    final_qty, final_unit = _yield_to_internal_qty(draft.yield_quantity, draft.yield_unit)
    for c in ["code"]: maybe_set(values, cols, c, code)
    for c in ["nombre","recipe_name","name"]: maybe_set(values, cols, c, draft.recipe_name)
    for c in ["categoria","category"]: maybe_set(values, cols, c, draft.category)
    for c in ["subcategory","subcategoria"]: maybe_set(values, cols, c, draft.subcategory)
    for c in ["rendimiento","yield_quantity"]: maybe_set(values, cols, c, draft.yield_quantity)
    for c in ["unidad_rendimiento","yield_unit"]: maybe_set(values, cols, c, draft.yield_unit)
    for c in ["yield_final_qty"]: maybe_set(values, cols, c, final_qty)
    for c in ["yield_final_unit"]: maybe_set(values, cols, c, final_unit)
    for c in ["raciones","portions","yield_portions"]: maybe_set(values, cols, c, draft.portions or 1)
    maybe_set(values, cols, "prep_steps", "\n".join(draft.elaboration_steps or []))
    maybe_set(values, cols, "elaboracion_json", json.dumps(draft.elaboration_steps, ensure_ascii=False))
    maybe_set(values, cols, "allergens", ",".join(draft.allergens or []))
    maybe_set(values, cols, "alergenos_json", json.dumps(draft.allergens, ensure_ascii=False))
    for c in ["waste_pct", "contingency_pct", "manual_price", "suggested_price", "prep_time_min", "cook_time_min", "rest_time_min"]:
        maybe_set(values, cols, c, 0)
    for c in ["target_food_cost_pct"]: maybe_set(values, cols, c, 30)
    for c in ["target_margin_pct"]: maybe_set(values, cols, c, 70)
    for c in ["is_subrecipe"]: maybe_set(values, cols, c, 0)
    maybe_set(values, cols, "estado", "VALIDADA"); maybe_set(values, cols, "status", "VALIDADA")
    maybe_set(values, cols, "created_by", actor or draft.created_by)
    maybe_set(values, cols, "created_at", time.strftime("%Y-%m-%d %H:%M:%S"))
    maybe_set(values, cols, "updated_at", time.strftime("%Y-%m-%d %H:%M:%S"))
    if not values: raise RuntimeError(f"No se pudo mapear tabla {table}.")
    fields = list(values)
    cur = conn.execute(f"INSERT INTO {table} ({', '.join(fields)}) VALUES ({', '.join(['?']*len(fields))})", [values[f] for f in fields])
    return int(cur.lastrowid)


def insert_ingredients(conn, table, recipe_id, draft):
    cols = get_table_columns(conn, table)
    for ing in draft.ingredients:
        ing.calculate_gross_quantity()
        values = {}
        for c in ["recipe_id","receta_id","ficha_tecnica_id"]: maybe_set(values, cols, c, recipe_id)
        for c in ["tipo","ingredient_type"]: maybe_set(values, cols, c, ing.ingredient_type)
        for c in ["articulo_id","item_id"]: maybe_set(values, cols, c, ing.matched_item_id)
        for c in ["subreceta_id","subrecipe_id"]: maybe_set(values, cols, c, ing.matched_subrecipe_id)
        for c in ["nombre","ingredient_name","item_name"]: maybe_set(values, cols, c, ing.normalized_name)
        for c in ["cantidad","quantity","quantity_net","qty_net"]: maybe_set(values, cols, c, ing.quantity_net or 0)
        for c in ["cantidad_bruta","quantity_gross","qty_gross"]: maybe_set(values, cols, c, ing.quantity_gross or ing.quantity_net or 0)
        for c in ["unidad","unit"]: maybe_set(values, cols, c, ing.unit or 'g')
        for c in ["input_unit"]: maybe_set(values, cols, c, ing.original_unit or ing.unit or 'g')
        for c in ["merma_percent","waste_percent","waste_pct_ing"]: maybe_set(values, cols, c, ing.waste_percent or 0)
        if not values: raise RuntimeError(f"No se pudo mapear ingredientes en {table}.")
        fields = list(values)
        conn.execute(f"INSERT INTO {table} ({', '.join(fields)}) VALUES ({', '.join(['?']*len(fields))})", [values[f] for f in fields])


def commit_imported_draft_to_master_recipe(db_path: str, draft_id: int, actor: Optional[str] = None) -> RecipeCommitResult:
    if str(os.environ.get("RECIPE_AI_ALLOW_COMMIT", "0")).strip().lower() not in {"1", "true", "yes", "si", "sí"}:
        return RecipeCommitResult(False, errors=["Conversión bloqueada por seguridad: activar RECIPE_AI_ALLOW_COMMIT=1 solo después de validar el laboratorio."])
    draft = get_imported_recipe_draft(db_path, draft_id)
    if not draft: return RecipeCommitResult(False, errors=["Borrador no encontrado."])
    errors = validate_draft_before_commit(draft)
    if errors:
        update_draft_status(db_path, draft_id, RecipeImportStatus.PENDIENTE_REVISION, actor, " | ".join(errors)); return RecipeCommitResult(False, errors=errors)
    with get_connection(db_path) as conn:
        tables = detect_real_recipe_tables(conn)
        if not tables["recipes"] or not tables["ingredients"]:
            return RecipeCommitResult(False, errors=["No se detectaron tablas reales de recetas. Ajustar commit_service.py al esquema real."])
        prev = row_to_dict(conn.execute("SELECT * FROM recipe_import_drafts WHERE id=?", (draft_id,)).fetchone())
        try:
            rid = insert_header(conn, tables["recipes"], draft, actor)
            insert_ingredients(conn, tables["ingredients"], rid, draft)
            conn.execute("UPDATE recipe_import_drafts SET import_status=?, converted_recipe_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (RecipeImportStatus.CONVERTIDA_A_RECETA, rid, draft_id))
            add_audit_log(conn, draft_id, "CONVERTIR_BORRADOR_A_RECETA", actor, previous_value=prev, new_value={"converted_recipe_id": rid})
            conn.commit()
            return RecipeCommitResult(True, rid, warnings=["Receta creada desde borrador IA. Revisar antes de producción real."])
        except Exception as exc:
            conn.rollback()
            return RecipeCommitResult(False, errors=[str(exc)])
