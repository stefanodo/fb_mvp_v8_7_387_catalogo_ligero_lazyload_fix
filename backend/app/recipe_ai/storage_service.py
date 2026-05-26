from __future__ import annotations
import json, sqlite3
from typing import Optional, Any
from .models import ImportedRecipeDraft, ImportedIngredient, LaborInfo, CatalogCandidate, RecipeImportStatus, ImportedIngredientStatus, RecipeCostStatus, validate_imported_recipe_draft

RECIPE_AI_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS recipe_import_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_name TEXT NOT NULL,
    recipe_type TEXT DEFAULT 'RECETA',
    category TEXT DEFAULT 'OTRO',
    subcategory TEXT,
    service_family TEXT DEFAULT 'OTRO',
    yield_quantity REAL,
    yield_unit TEXT DEFAULT 'kg',
    portions INTEGER,
    elaboration_steps_json TEXT,
    allergens_json TEXT,
    labor_json TEXT,
    import_status TEXT DEFAULT 'BORRADOR_IA',
    cost_status TEXT DEFAULT 'NO_CALCULADO',
    confidence REAL DEFAULT 0,
    warnings_json TEXT,
    source_type TEXT,
    raw_input_text TEXT,
    raw_ia_json TEXT,
    ia_provider TEXT,
    ia_model TEXT,
    process_time_s REAL,
    created_by TEXT,
    validated_by TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    validated_at DATETIME,
    review_at DATETIME,
    converted_recipe_id INTEGER
);
CREATE TABLE IF NOT EXISTS recipe_import_ingredients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id INTEGER NOT NULL REFERENCES recipe_import_drafts(id) ON DELETE CASCADE,
    original_text TEXT,
    normalized_name TEXT NOT NULL,
    ingredient_type TEXT DEFAULT 'ARTICULO',
    quantity_net REAL,
    unit TEXT,
    waste_percent REAL DEFAULT 0,
    quantity_gross REAL,
    match_status TEXT DEFAULT 'PENDIENTE_ALTA',
    matched_item_id INTEGER,
    matched_item_name TEXT,
    matched_subrecipe_id INTEGER,
    matched_subrecipe_name TEXT,
    candidates_json TEXT,
    needs_admin_validation INTEGER DEFAULT 1,
    notes TEXT,
    original_quantity REAL,
    original_unit TEXT,
    conversion_status TEXT DEFAULT 'NO_REQUIERE_CONVERSION',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS recipe_import_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id INTEGER,
    ingredient_id INTEGER,
    action TEXT NOT NULL,
    actor TEXT,
    previous_value_json TEXT,
    new_value_json TEXT,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_recipe_import_drafts_status ON recipe_import_drafts(import_status);
CREATE INDEX IF NOT EXISTS idx_recipe_import_ingredients_draft ON recipe_import_ingredients(draft_id);
CREATE INDEX IF NOT EXISTS idx_recipe_import_ingredients_status ON recipe_import_ingredients(match_status);
"""

def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_recipe_ai_storage(db_path: str) -> None:
    with get_connection(db_path) as conn:
        conn.executescript(RECIPE_AI_SCHEMA_SQL)
        # Migración segura: versiones anteriores no tenían review_at.
        try:
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(recipe_import_drafts)").fetchall()}
            if "review_at" not in cols:
                conn.execute("ALTER TABLE recipe_import_drafts ADD COLUMN review_at DATETIME")
            conn.execute("UPDATE recipe_import_drafts SET review_at=COALESCE(review_at, created_at, CURRENT_TIMESTAMP) WHERE import_status='PENDIENTE_REVISION'")
        except Exception:
            pass
        conn.commit()

def json_dumps(value: Any) -> str: return json.dumps(value, ensure_ascii=False)
def json_loads(value: Optional[str], fallback):
    if not value: return fallback
    try: return json.loads(value)
    except Exception: return fallback
def row_to_dict(row): return None if row is None else {k: row[k] for k in row.keys()}

def add_audit_log(conn, draft_id, action, actor=None, ingredient_id=None, previous_value=None, new_value=None, notes=None):
    conn.execute("INSERT INTO recipe_import_audit_log (draft_id, ingredient_id, action, actor, previous_value_json, new_value_json, notes) VALUES (?, ?, ?, ?, ?, ?, ?)", (draft_id, ingredient_id, action, actor, json_dumps(previous_value) if previous_value is not None else None, json_dumps(new_value) if new_value is not None else None, notes))

def save_imported_ingredient_row(conn, draft_id: int, ingredient: ImportedIngredient) -> int:
    ingredient.calculate_gross_quantity()
    if ingredient.ingredient_type == "ARTICULO" and not ingredient.matched_item_id:
        if ingredient.match_status not in {ImportedIngredientStatus.PENDIENTE_REVISION, ImportedIngredientStatus.COINCIDENCIA_SUGERIDA}:
            ingredient.match_status = ImportedIngredientStatus.PENDIENTE_ALTA
        ingredient.needs_admin_validation = True
        if not ingredient.notes: ingredient.add_note("Ingrediente nuevo pendiente de alta en Catálogo.")
    candidates = [c.to_dict() if hasattr(c, "to_dict") else c for c in ingredient.candidates]
    cur = conn.execute("""
        INSERT INTO recipe_import_ingredients
        (draft_id, original_text, normalized_name, ingredient_type, quantity_net, unit, waste_percent, quantity_gross, match_status, matched_item_id, matched_item_name, matched_subrecipe_id, matched_subrecipe_name, candidates_json, needs_admin_validation, notes, original_quantity, original_unit, conversion_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (draft_id, ingredient.original_text, ingredient.normalized_name, ingredient.ingredient_type, ingredient.quantity_net, ingredient.unit, ingredient.waste_percent, ingredient.quantity_gross, ingredient.match_status, ingredient.matched_item_id, ingredient.matched_item_name, ingredient.matched_subrecipe_id, ingredient.matched_subrecipe_name, json_dumps(candidates), 1 if ingredient.needs_admin_validation else 0, ingredient.notes, ingredient.original_quantity, ingredient.original_unit, ingredient.conversion_status))
    return int(cur.lastrowid)


def _find_recent_empty_duplicate(conn, draft: ImportedRecipeDraft) -> Optional[int]:
    """Evita crear múltiples borradores vacíos idénticos cuando la IA/foto queda offline.
    Regla conservadora: mismo origen + mismo nombre + 0 ingredientes + revisión reciente.
    """
    try:
        if draft.ingredients:
            return None
        row = conn.execute(
            """
            SELECT d.id
              FROM recipe_import_drafts d
              LEFT JOIN recipe_import_ingredients i ON i.draft_id=d.id
             WHERE UPPER(TRIM(d.recipe_name))=UPPER(TRIM(?))
               AND COALESCE(d.source_type,'')=COALESCE(?, '')
               AND d.import_status='PENDIENTE_REVISION'
               AND datetime(COALESCE(d.created_at,CURRENT_TIMESTAMP)) >= datetime('now','-2 hours')
             GROUP BY d.id
            HAVING COUNT(i.id)=0
             ORDER BY d.created_at DESC
             LIMIT 1
            """,
            (draft.recipe_name or "RECETA PENDIENTE DE REVISION", draft.source_type or "")
        ).fetchone()
        return int(row["id"]) if row else None
    except Exception:
        return None

def save_imported_recipe_draft(db_path: str, draft: ImportedRecipeDraft, actor: Optional[str] = None) -> int:
    init_recipe_ai_storage(db_path)
    draft = validate_imported_recipe_draft(draft)
    with get_connection(db_path) as conn:
        existing_id = _find_recent_empty_duplicate(conn, draft)
        if existing_id:
            add_audit_log(conn, existing_id, "BORRADOR_IA_DUPLICADO_EVITADO", actor or draft.created_by, new_value=draft.to_dict(), notes="Se evitó duplicar un borrador vacío reciente.")
            conn.commit()
            return existing_id
        review_at_expr = "CURRENT_TIMESTAMP" if draft.import_status == RecipeImportStatus.PENDIENTE_REVISION else "NULL"
        cur = conn.execute(f"""
            INSERT INTO recipe_import_drafts
            (recipe_name, recipe_type, category, subcategory, service_family, yield_quantity, yield_unit, portions, elaboration_steps_json, allergens_json, labor_json, import_status, cost_status, confidence, warnings_json, source_type, raw_input_text, raw_ia_json, ia_provider, ia_model, process_time_s, created_by, review_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, {review_at_expr})
        """, (draft.recipe_name, draft.recipe_type, draft.category, draft.subcategory, draft.service_family, draft.yield_quantity, draft.yield_unit, draft.portions, json_dumps(draft.elaboration_steps), json_dumps(draft.allergens), json_dumps(draft.labor.to_dict()), draft.import_status, draft.cost_status, draft.confidence, json_dumps(draft.warnings), draft.source_type, draft.raw_input_text, json_dumps(draft.raw_ia_json) if draft.raw_ia_json else None, draft.ia_provider, draft.ia_model, draft.process_time_s, draft.created_by or actor))
        draft_id = int(cur.lastrowid)
        for i in draft.ingredients: save_imported_ingredient_row(conn, draft_id, i)
        add_audit_log(conn, draft_id, "CREAR_BORRADOR_IA", actor or draft.created_by, new_value=draft.to_dict(), notes="Borrador creado desde IA/voz/foto/texto.")
        conn.commit()
    return draft_id

def list_imported_recipe_drafts(db_path: str, status: Optional[str] = None, limit: int = 50) -> list[dict]:
    init_recipe_ai_storage(db_path)
    q = "SELECT d.*, COUNT(i.id) AS ingredient_count, SUM(CASE WHEN i.needs_admin_validation = 1 THEN 1 ELSE 0 END) AS pending_count FROM recipe_import_drafts d LEFT JOIN recipe_import_ingredients i ON i.draft_id = d.id"
    params = []
    if status:
        q += " WHERE d.import_status = ?"; params.append(status)
    q += " GROUP BY d.id ORDER BY d.created_at DESC LIMIT ?"; params.append(limit)
    with get_connection(db_path) as conn:
        return [row_to_dict(r) for r in conn.execute(q, params).fetchall()]

def draft_from_rows(draft_row, ingredient_rows) -> ImportedRecipeDraft:
    ingredients = []
    for row in ingredient_rows:
        candidates = [CatalogCandidate(int(c.get("item_id") or 0), c.get("name") or "", float(c.get("similarity_score") or 0), c.get("reason") or "") for c in json_loads(row["candidates_json"], []) if isinstance(c, dict)]
        ingredients.append(ImportedIngredient(row["original_text"] or "", row["normalized_name"] or "", row["ingredient_type"] or "ARTICULO", row["quantity_net"], row["unit"], row["waste_percent"] or 0, row["quantity_gross"], row["match_status"] or ImportedIngredientStatus.PENDIENTE_ALTA, row["matched_item_id"], row["matched_item_name"], row["matched_subrecipe_id"], row["matched_subrecipe_name"], candidates, bool(row["needs_admin_validation"]), row["notes"], row["original_quantity"], row["original_unit"], row["conversion_status"] or "NO_REQUIERE_CONVERSION"))
    labor_data = json_loads(draft_row["labor_json"], {})
    labor = LaborInfo(int(labor_data.get("prep_time_minutes") or 0), int(labor_data.get("cook_time_minutes") or 0), int(labor_data.get("rest_time_minutes") or 0), int(labor_data.get("people") or 1), float(labor_data.get("hourly_cost") or 14), float(labor_data.get("labor_cost") or 0))
    draft = ImportedRecipeDraft(draft_row["source_type"] or "texto", draft_row["recipe_name"] or "SIN NOMBRE", draft_row["recipe_type"] or "RECETA", draft_row["category"] or "OTRO", draft_row["subcategory"], draft_row["service_family"] or "OTRO", draft_row["yield_quantity"], draft_row["yield_unit"] or "kg", draft_row["portions"], ingredients, json_loads(draft_row["elaboration_steps_json"], []), json_loads(draft_row["allergens_json"], []), labor, draft_row["import_status"] or RecipeImportStatus.BORRADOR_IA, draft_row["cost_status"] or RecipeCostStatus.NO_CALCULADO, float(draft_row["confidence"] or 0), json_loads(draft_row["warnings_json"], []), draft_row["ia_provider"] or "none", draft_row["ia_model"] or "none", float(draft_row["process_time_s"] or 0), draft_row["raw_input_text"], json_loads(draft_row["raw_ia_json"], None), draft_row["created_by"], draft_row["validated_by"])
    return validate_imported_recipe_draft(draft)

def get_imported_recipe_draft(db_path: str, draft_id: int):
    init_recipe_ai_storage(db_path)
    with get_connection(db_path) as conn:
        d = conn.execute("SELECT * FROM recipe_import_drafts WHERE id = ?", (draft_id,)).fetchone()
        if not d: return None
        rows = conn.execute("SELECT * FROM recipe_import_ingredients WHERE draft_id = ? ORDER BY id ASC", (draft_id,)).fetchall()
    return draft_from_rows(d, rows)

def update_imported_ingredient(db_path: str, ingredient_id: int, updates: dict, actor: Optional[str] = None) -> bool:
    allowed = {"original_text","normalized_name","ingredient_type","quantity_net","unit","waste_percent","quantity_gross","match_status","matched_item_id","matched_item_name","matched_subrecipe_id","matched_subrecipe_name","candidates_json","needs_admin_validation","notes","original_quantity","original_unit","conversion_status"}
    clean = {k:v for k,v in updates.items() if k in allowed}
    if not clean: return False
    init_recipe_ai_storage(db_path)
    with get_connection(db_path) as conn:
        prev = conn.execute("SELECT * FROM recipe_import_ingredients WHERE id = ?", (ingredient_id,)).fetchone()
        if not prev: return False
        draft_id = int(prev["draft_id"])
        set_clause = ", ".join([f"{k} = ?" for k in clean]) + ", updated_at = CURRENT_TIMESTAMP"
        conn.execute(f"UPDATE recipe_import_ingredients SET {set_clause} WHERE id = ?", list(clean.values()) + [ingredient_id])
        conn.execute("UPDATE recipe_import_drafts SET updated_at = CURRENT_TIMESTAMP, import_status = ? WHERE id = ?", (RecipeImportStatus.PENDIENTE_REVISION, draft_id))
        add_audit_log(conn, draft_id, "ACTUALIZAR_INGREDIENTE_IMPORTADO", actor, ingredient_id, row_to_dict(prev), clean)
        conn.commit()
    return True

def mark_ingredient_pending_catalog(db_path, ingredient_id, actor=None): return update_imported_ingredient(db_path, ingredient_id, {"match_status": ImportedIngredientStatus.PENDIENTE_ALTA, "matched_item_id": None, "matched_item_name": None, "needs_admin_validation": 1, "notes": "Ingrediente nuevo pendiente de alta en Catálogo."}, actor)
def link_ingredient_to_catalog_item(db_path, ingredient_id, item_id, item_name, actor=None): return update_imported_ingredient(db_path, ingredient_id, {"match_status": ImportedIngredientStatus.VINCULADO_CATALOGO, "matched_item_id": item_id, "matched_item_name": str(item_name).upper(), "needs_admin_validation": 0, "notes": None}, actor)
def link_ingredient_to_subrecipe(db_path, ingredient_id, subrecipe_id, subrecipe_name, actor=None): return update_imported_ingredient(db_path, ingredient_id, {"ingredient_type": "SUBRECETA", "match_status": ImportedIngredientStatus.VINCULADO_CATALOGO, "matched_subrecipe_id": subrecipe_id, "matched_subrecipe_name": str(subrecipe_name).upper(), "matched_item_id": None, "matched_item_name": None, "needs_admin_validation": 0, "notes": None}, actor)

def update_draft_status(db_path, draft_id, new_status, actor=None, notes=None):
    init_recipe_ai_storage(db_path)
    with get_connection(db_path) as conn:
        prev = conn.execute("SELECT * FROM recipe_import_drafts WHERE id = ?", (draft_id,)).fetchone()
        if not prev: return False
        conn.execute("UPDATE recipe_import_drafts SET import_status = ?, updated_at = CURRENT_TIMESTAMP, review_at = CASE WHEN ?='PENDIENTE_REVISION' THEN COALESCE(review_at, CURRENT_TIMESTAMP) ELSE review_at END WHERE id = ?", (new_status, new_status, draft_id))
        add_audit_log(conn, draft_id, "CAMBIAR_ESTADO_BORRADOR", actor, previous_value={"import_status": prev["import_status"]}, new_value={"import_status": new_status}, notes=notes)
        conn.commit()
    return True

def mark_draft_ready_to_convert(db_path, draft_id, actor=None):
    draft = get_imported_recipe_draft(db_path, draft_id)
    if not draft: return False, ["Borrador no encontrado."]
    errors = []
    if draft.has_critical_pending(): errors.append("Hay ingredientes pendientes.")
    if not draft.yield_quantity or draft.yield_quantity <= 0: errors.append("Rendimiento pendiente o inválido.")
    if draft.cost_status not in {RecipeCostStatus.COSTE_COMPLETO, RecipeCostStatus.COSTE_ESTIMADO}: errors.append("El coste no está completo o estimado.")
    if errors:
        update_draft_status(db_path, draft_id, RecipeImportStatus.PENDIENTE_REVISION, actor, " | ".join(errors)); return False, errors
    update_draft_status(db_path, draft_id, RecipeImportStatus.VALIDADA_PARA_CONVERTIR, actor, "Borrador validado para conversión.")
    return True, []

def update_draft_cost_status(db_path, draft_id, cost_status, warnings=None, actor=None):
    init_recipe_ai_storage(db_path)
    with get_connection(db_path) as conn:
        prev = conn.execute("SELECT cost_status, warnings_json FROM recipe_import_drafts WHERE id = ?", (draft_id,)).fetchone()
        if not prev: return False
        merged = json_loads(prev["warnings_json"], [])
        for w in warnings or []:
            if w and w not in merged: merged.append(w)
        conn.execute("UPDATE recipe_import_drafts SET cost_status = ?, warnings_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (cost_status, json_dumps(merged), draft_id))
        add_audit_log(conn, draft_id, "ACTUALIZAR_COSTE_BORRADOR", actor, previous_value={"cost_status": prev["cost_status"]}, new_value={"cost_status": cost_status, "warnings": warnings or []})
        conn.commit()
    return True
