from __future__ import annotations
import json, sqlite3
from typing import Optional, Any
from datetime import datetime, timedelta
from .models import ImportedRecipeDraft, ImportedIngredient, LaborInfo, CatalogCandidate, RecipeImportStatus, ImportedIngredientStatus, RecipeCostStatus, validate_imported_recipe_draft
from app.core import get_table_columns_from_cursor, safe_insert_returning

# Recipe AI schema is now managed by backend/migrate.py.
# For production deployments rely on `backend/migrate.py` to create and alter tables.

def get_connection(db_path: str):
    # In production we use the shared DB connection provided by app.db_config
    try:
        from app.db_config import IS_PRODUCTION, get_db_connection
    except Exception:
        IS_PRODUCTION = False
        get_db_connection = None
    if IS_PRODUCTION and callable(get_db_connection):
        return get_db_connection()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # Apply centralized sqlite pragmas when available; skip for Postgres adapters
    try:
        if not getattr(conn, "_is_postgres", False):
            try:
                from app.db_config import ensure_sqlite_pragmas
            except Exception:
                ensure_sqlite_pragmas = None
            if ensure_sqlite_pragmas:
                try:
                    ensure_sqlite_pragmas(conn)
                except Exception:
                    pass
            else:
                # No centralized helper available; skip executing PRAGMA directly.
                # Standalone tools may rely on their own PRAGMA handling when needed.
                pass
    except Exception:
        pass
    return conn

def init_recipe_ai_storage(db_path: str) -> None:
    # In production the Postgres schema is created at build-time by backend/migrate.py.
    try:
        from app.db_config import IS_PRODUCTION
    except Exception:
        IS_PRODUCTION = False
    if IS_PRODUCTION:
        return
    # Schema creation/alterations are performed by backend/migrate.py.
    # Keep a lightweight compatibility step for local DBs (no CREATEs here).
    try:
        with get_connection(db_path) as conn:
            # If an older local DB exists, add the `review_at` column safely.
            try:
                cols = get_table_columns_from_cursor(conn, "recipe_import_drafts")
                if "review_at" not in cols:
                    conn.execute("ALTER TABLE recipe_import_drafts ADD COLUMN review_at DATETIME")
                try:
                    conn.execute("UPDATE recipe_import_drafts SET review_at=COALESCE(review_at, created_at, CURRENT_TIMESTAMP) WHERE import_status='PENDIENTE_REVISION'")
                except Exception:
                    pass
            except Exception:
                # Table may not exist in fresh environments; migrations should be applied instead.
                pass
            try:
                conn.commit()
            except Exception:
                pass
    except Exception:
        pass

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
        if not ingredient.notes:
            ingredient.add_note("Ingrediente nuevo pendiente de alta en Catálogo.")
    candidates = [c.to_dict() if hasattr(c, "to_dict") else c for c in ingredient.candidates]

    cur = conn.cursor()
    sqlite_sql = """
            INSERT INTO recipe_import_ingredients
            (draft_id, original_text, normalized_name, ingredient_type, quantity_net, unit, waste_percent, quantity_gross, match_status, matched_item_id, matched_item_name, matched_subrecipe_id, matched_subrecipe_name, candidates_json, needs_admin_validation, notes, original_quantity, original_unit, conversion_status)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """
    params = (
        draft_id, ingredient.original_text, ingredient.normalized_name, ingredient.ingredient_type,
        ingredient.quantity_net, ingredient.unit, ingredient.waste_percent, ingredient.quantity_gross,
        ingredient.match_status, ingredient.matched_item_id, ingredient.matched_item_name,
        ingredient.matched_subrecipe_id, ingredient.matched_subrecipe_name, json_dumps(candidates),
        1 if ingredient.needs_admin_validation else 0, ingredient.notes, ingredient.original_quantity,
        ingredient.original_unit, ingredient.conversion_status,
    )
    pg_sql = sqlite_sql.replace('?', '%s')
    iid = safe_insert_returning(cur, sqlite_sql, params, pg_sql=pg_sql)
    return int(iid or 0)


def _find_recent_empty_duplicate(conn, draft: ImportedRecipeDraft) -> Optional[int]:
    """Evita crear múltiples borradores vacíos idénticos cuando la IA/foto queda offline.
    Regla conservadora: mismo origen + mismo nombre + 0 ingredientes + revisión reciente.
    """
    try:
        # If there are any ingredients, it's not an "empty" draft: skip duplicate check.
        if draft.ingredients:
            return None

        # Prefer a param-driven cutoff for portability (avoid sqlite-only datetime('now','-2 hours')).
        cutoff = (datetime.utcnow() - timedelta(hours=2)).isoformat()
        try:
            row = conn.execute(
                """
                SELECT d.id
                  FROM recipe_import_drafts d
                  LEFT JOIN recipe_import_ingredients i ON i.draft_id=d.id
                 WHERE UPPER(TRIM(d.recipe_name))=UPPER(TRIM(?))
                   AND COALESCE(d.source_type,'')=COALESCE(?, '')
                   AND d.import_status='PENDIENTE_REVISION'
                   AND COALESCE(d.created_at,CURRENT_TIMESTAMP) >= ?
                 GROUP BY d.id
                HAVING COUNT(i.id)=0
                 ORDER BY d.created_at DESC
                 LIMIT 1
                """,
                (draft.recipe_name or "RECETA PENDIENTE DE REVISION", draft.source_type or "", cutoff),
            ).fetchone()
        except Exception:
            # Fallback: perform a safe time comparison in Python when SQL dialect features fail.
            try:
                cutoff_dt = datetime.utcnow() - timedelta(hours=2)
                rows = conn.execute(
                    "SELECT d.id,d.created_at FROM recipe_import_drafts d LEFT JOIN recipe_import_ingredients i ON i.draft_id=d.id WHERE UPPER(TRIM(d.recipe_name))=UPPER(TRIM(?)) AND COALESCE(d.source_type,'')=COALESCE(?, '') AND d.import_status='PENDIENTE_REVISION' GROUP BY d.id HAVING COUNT(i.id)=0 ORDER BY d.created_at DESC LIMIT 10",
                    (draft.recipe_name or "RECETA PENDIENTE DE REVISION", draft.source_type or ""),
                ).fetchall()
                row = None
                for r in rows:
                    try:
                        created = r.get("created_at") if isinstance(r, dict) or hasattr(r, 'get') else r[1]
                        if created:
                            created_dt = datetime.fromisoformat(created.replace('Z', '+00:00')) if isinstance(created, str) else None
                            if created_dt and created_dt >= cutoff_dt:
                                row = r
                                break
                    except Exception:
                        continue
            except Exception:
                row = None

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
        cols = [
            "recipe_name", "recipe_type", "category", "subcategory", "service_family", "yield_quantity",
            "yield_unit", "portions", "elaboration_steps_json", "allergens_json", "labor_json", "import_status",
            "cost_status", "confidence", "warnings_json", "source_type", "raw_input_text", "raw_ia_json",
            "ia_provider", "ia_model", "process_time_s", "created_by",
        ]
        placeholders_q = ", ".join("?" for _ in cols)
        placeholders_pct = ", ".join("%s" for _ in cols)
        params = (
            draft.recipe_name, draft.recipe_type, draft.category, draft.subcategory, draft.service_family, draft.yield_quantity,
            draft.yield_unit, draft.portions, json_dumps(draft.elaboration_steps), json_dumps(draft.allergens), json_dumps(draft.labor.to_dict()), draft.import_status,
            draft.cost_status, draft.confidence, json_dumps(draft.warnings), draft.source_type, draft.raw_input_text, json_dumps(draft.raw_ia_json) if draft.raw_ia_json else None,
            draft.ia_provider, draft.ia_model, draft.process_time_s, draft.created_by or actor,
        )

        sqlite_sql = f"INSERT INTO recipe_import_drafts ({', '.join(cols)}, review_at) VALUES ({placeholders_q}, {review_at_expr})"
        try:
            cur2 = conn.cursor()
            pg_sql = sqlite_sql.replace('?', '%s')
            draft_id = safe_insert_returning(cur2, sqlite_sql, params, pg_sql=pg_sql) or 0
        except Exception:
            # Retry with an explicit cursor through the safe helper (avoid raw INSERT+SELECT fallbacks)
            try:
                cur_alt = conn.cursor()
                pg_sql = sqlite_sql.replace('?', '%s')
                draft_id = safe_insert_returning(cur_alt, sqlite_sql, params, pg_sql=pg_sql) or 0
            except Exception:
                # Last resort deterministic lookup by recipe_name + created_by
                try:
                    created_by = params[-1] if len(params) > 0 else None
                    row = conn.execute("SELECT id FROM recipe_import_drafts WHERE recipe_name=? AND created_by=? ORDER BY id DESC LIMIT 1", (params[0], created_by)).fetchone()
                    draft_id = int(row['id']) if row else 0
                except Exception:
                    draft_id = 0

        for i in draft.ingredients:
            save_imported_ingredient_row(conn, draft_id, i)
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
