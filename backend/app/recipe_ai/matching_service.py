from __future__ import annotations
import difflib, sqlite3
from dataclasses import dataclass, asdict
from typing import Optional
from .models import ImportedIngredient, ImportedIngredientStatus

@dataclass
class MatchCandidate:
    item_id: int
    name: str
    score: float
    reason: str
    match_type: str = "ARTICULO"
    def to_dict(self) -> dict: return asdict(self)

@dataclass
class MatchResult:
    status: str
    matched_item_id: Optional[int] = None
    matched_item_name: Optional[str] = None
    matched_subrecipe_id: Optional[int] = None
    matched_subrecipe_name: Optional[str] = None
    candidates: list[MatchCandidate] = None
    notes: Optional[str] = None
    def __post_init__(self):
        if self.candidates is None: self.candidates = []
    def to_dict(self): return asdict(self)

def normalize_name(v):
    if not v: return ""
    t = " ".join(str(v).strip().upper().split())
    for a,b in {"Á":"A","É":"E","Í":"I","Ó":"O","Ú":"U","Ü":"U","Ñ":"N"}.items(): t = t.replace(a,b)
    return t
def similarity(a,b):
    a,b = normalize_name(a), normalize_name(b)
    return 0.0 if not a or not b else difflib.SequenceMatcher(None,a,b).ratio()
def table_exists(conn, table): return conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None
def load_catalog_for_matching(conn):
    for table,idc,namec in [("articulos","id","nombre"),("items","id","name"),("catalog_items","id","name")]:
        if table_exists(conn, table):
            try: return [{"id":r["id"],"name":r["name"]} for r in conn.execute(f"SELECT {idc} AS id, {namec} AS name FROM {table}").fetchall()]
            except Exception: pass
    return []
def load_subrecipes_for_matching(conn):
    for table,idc,namec in [("subrecetas","id","nombre"),("subrecipes","id","name"),("recetas","id","nombre"),("recipes","id","name")]:
        if table_exists(conn, table):
            try: return [{"id":r["id"],"name":r["name"]} for r in conn.execute(f"SELECT {idc} AS id, {namec} AS name FROM {table}").fetchall()]
            except Exception: pass
    return []
def _matches(name, items, kind, min_score):
    out = []
    for item in items:
        item_id, item_name = item.get("id"), item.get("name") or item.get("nombre")
        if not item_id or not item_name: continue
        score = 1.0 if normalize_name(name) == normalize_name(item_name) else similarity(name, item_name)
        if score >= min_score: out.append(MatchCandidate(int(item_id), str(item_name).upper(), round(score,4), f"Coincidencia textual con {kind}.", kind))
    return sorted(out, key=lambda x:x.score, reverse=True)
def match_imported_ingredient(ingredient: ImportedIngredient, catalog_items, subrecipes, auto_link_threshold=0.94, suggested_threshold=0.70):
    candidates = _matches(ingredient.normalized_name, catalog_items, "ARTICULO", 0.55) + _matches(ingredient.normalized_name, subrecipes, "SUBRECETA", 0.60)
    candidates = sorted(candidates, key=lambda x:x.score, reverse=True)
    if not candidates: return MatchResult(ImportedIngredientStatus.PENDIENTE_ALTA, candidates=[], notes="Ingrediente nuevo pendiente de alta en Catálogo.")
    best = candidates[0]
    if best.score >= auto_link_threshold:
        if best.match_type == "SUBRECETA": return MatchResult(ImportedIngredientStatus.VINCULADO_CATALOGO, matched_subrecipe_id=best.item_id, matched_subrecipe_name=best.name, candidates=candidates, notes="Subreceta vinculada por coincidencia alta.")
        return MatchResult(ImportedIngredientStatus.VINCULADO_CATALOGO, matched_item_id=best.item_id, matched_item_name=best.name, candidates=candidates, notes="Artículo vinculado por coincidencia alta.")
    if best.score >= suggested_threshold: return MatchResult(ImportedIngredientStatus.COINCIDENCIA_SUGERIDA, candidates=candidates, notes="Hay posibles coincidencias. Requiere validación humana.")
    return MatchResult(ImportedIngredientStatus.PENDIENTE_ALTA, candidates=candidates, notes="Ingrediente nuevo pendiente de alta en Catálogo.")
def apply_match_to_ingredient(ingredient, result):
    ingredient.match_status, ingredient.candidates = result.status, result.candidates or []
    if result.matched_item_id:
        ingredient.ingredient_type, ingredient.matched_item_id, ingredient.matched_item_name, ingredient.needs_admin_validation = "ARTICULO", result.matched_item_id, result.matched_item_name, False
    elif result.matched_subrecipe_id:
        ingredient.ingredient_type, ingredient.matched_subrecipe_id, ingredient.matched_subrecipe_name, ingredient.needs_admin_validation = "SUBRECETA", result.matched_subrecipe_id, result.matched_subrecipe_name, False
    else:
        ingredient.needs_admin_validation = True
    if result.notes: ingredient.add_note(result.notes)
    return ingredient
def match_draft_ingredients(draft, catalog_items, subrecipes):
    draft.ingredients = [apply_match_to_ingredient(i, match_imported_ingredient(i, catalog_items, subrecipes)) for i in draft.ingredients]
    if draft.has_critical_pending(): draft.import_status = "PENDIENTE_REVISION"
    return draft
