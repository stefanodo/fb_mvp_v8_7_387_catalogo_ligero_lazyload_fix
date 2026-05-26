from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional, Literal

class RecipeImportStatus:
    DICTADO_EN_CURSO = "DICTADO_EN_CURSO"
    BORRADOR_IA = "BORRADOR_IA"
    PENDIENTE_REVISION = "PENDIENTE_REVISION"
    VALIDADA_PARA_CONVERTIR = "VALIDADA_PARA_CONVERTIR"
    CONVERTIDA_A_RECETA = "CONVERTIDA_A_RECETA"
    RECETA_MAESTRA_VALIDADA = "RECETA_MAESTRA_VALIDADA"
    PROPUESTA_CAMBIO_IA = "PROPUESTA_CAMBIO_IA"
    CAMBIO_PENDIENTE_APROBACION = "CAMBIO_PENDIENTE_APROBACION"
    RECHAZADA = "RECHAZADA"
    ARCHIVADA = "ARCHIVADA"

class RecipeCostStatus:
    NO_CALCULADO = "NO_CALCULADO"
    COSTE_COMPLETO = "COSTE_COMPLETO"
    COSTE_INCOMPLETO = "COSTE_INCOMPLETO"
    COSTE_ESTIMADO = "COSTE_ESTIMADO"
    COSTE_NO_CALCULABLE = "COSTE_NO_CALCULABLE"

class ImportedIngredientStatus:
    VINCULADO_CATALOGO = "VINCULADO_CATALOGO"
    COINCIDENCIA_SUGERIDA = "COINCIDENCIA_SUGERIDA"
    PENDIENTE_ALTA = "PENDIENTE_ALTA"
    PENDIENTE_REVISION = "PENDIENTE_REVISION"
    UNIDAD_INCOMPATIBLE = "UNIDAD_INCOMPATIBLE"
    SUBRECETA_PENDIENTE = "SUBRECETA_PENDIENTE"

class ConversionStatus:
    NO_REQUIERE_CONVERSION = "NO_REQUIERE_CONVERSION"
    PENDIENTE_CONVERSION_PESO = "PENDIENTE_CONVERSION_PESO"
    CONVERTIDO_A_PESO = "CONVERTIDO_A_PESO"
    NO_CONVERTIBLE = "NO_CONVERTIBLE"

IngredientType = Literal["ARTICULO", "SUBRECETA"]
VALID_UNITS = {"g", "kg", "ud", "racion", "docena", "ml", "l"}
LIQUID_UNITS_TO_REVIEW = {"ml", "l"}

@dataclass
class CatalogCandidate:
    item_id: int
    name: str
    similarity_score: float
    reason: str = ""
    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class ImportedIngredient:
    original_text: str
    normalized_name: str
    ingredient_type: IngredientType = "ARTICULO"
    quantity_net: Optional[float] = None
    unit: Optional[str] = None
    waste_percent: float = 0.0
    quantity_gross: Optional[float] = None
    match_status: str = ImportedIngredientStatus.PENDIENTE_ALTA
    matched_item_id: Optional[int] = None
    matched_item_name: Optional[str] = None
    matched_subrecipe_id: Optional[int] = None
    matched_subrecipe_name: Optional[str] = None
    candidates: list = field(default_factory=list)
    needs_admin_validation: bool = True
    notes: Optional[str] = None
    original_quantity: Optional[float] = None
    original_unit: Optional[str] = None
    conversion_status: str = ConversionStatus.NO_REQUIERE_CONVERSION

    def add_note(self, note: str) -> None:
        if note and (not self.notes or note not in self.notes):
            self.notes = note if not self.notes else f"{self.notes} | {note}"

    def calculate_gross_quantity(self) -> None:
        if self.quantity_net is None:
            self.quantity_gross = None
            return
        if self.waste_percent < 0 or self.waste_percent >= 100:
            self.quantity_gross = None
            self.match_status = ImportedIngredientStatus.PENDIENTE_REVISION
            self.needs_admin_validation = True
            self.add_note("Merma inválida. Debe estar entre 0 y 99,99%.")
            return
        self.quantity_gross = round(self.quantity_net / (1 - self.waste_percent / 100), 6)

    def is_critical_pending(self) -> bool:
        return self.match_status in {
            ImportedIngredientStatus.PENDIENTE_ALTA,
            ImportedIngredientStatus.PENDIENTE_REVISION,
            ImportedIngredientStatus.UNIDAD_INCOMPATIBLE,
            ImportedIngredientStatus.SUBRECETA_PENDIENTE,
        }

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class LaborInfo:
    prep_time_minutes: int = 0
    cook_time_minutes: int = 0
    rest_time_minutes: int = 0
    people: int = 1
    hourly_cost: float = 14.0
    labor_cost: float = 0.0
    def calculate_labor_cost(self) -> None:
        active_minutes = max(self.prep_time_minutes, 0) + max(self.cook_time_minutes, 0)
        self.labor_cost = round((active_minutes / 60) * max(self.people, 1) * max(self.hourly_cost, 0), 2)
    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class ImportedRecipeDraft:
    source_type: str
    recipe_name: str
    recipe_type: str = "RECETA"
    category: str = "OTRO"
    subcategory: Optional[str] = None
    service_family: str = "OTRO"
    yield_quantity: Optional[float] = None
    yield_unit: str = "kg"
    portions: Optional[int] = None
    ingredients: list[ImportedIngredient] = field(default_factory=list)
    elaboration_steps: list[str] = field(default_factory=list)
    allergens: list[str] = field(default_factory=list)
    labor: LaborInfo = field(default_factory=LaborInfo)
    import_status: str = RecipeImportStatus.BORRADOR_IA
    cost_status: str = RecipeCostStatus.NO_CALCULADO
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)
    ia_provider: str = "none"
    ia_model: str = "none"
    process_time_s: float = 0.0
    raw_input_text: Optional[str] = None
    raw_ia_json: Optional[dict] = None
    created_by: Optional[str] = None
    validated_by: Optional[str] = None

    def add_warning(self, warning: str) -> None:
        if warning and warning not in self.warnings:
            self.warnings.append(warning)

    def has_critical_pending(self) -> bool:
        return any(i.is_critical_pending() for i in self.ingredients)

    def calculate_all_gross_quantities(self) -> None:
        for i in self.ingredients:
            i.calculate_gross_quantity()

    def can_convert_to_master_recipe(self) -> bool:
        if self.has_critical_pending(): return False
        if not self.recipe_name or self.recipe_name.strip().upper() == "SIN NOMBRE": return False
        if self.yield_quantity is None or self.yield_quantity <= 0: return False
        if not self.yield_unit or self.yield_unit not in VALID_UNITS: return False
        if not self.ingredients: return False
        if self.cost_status not in {RecipeCostStatus.COSTE_COMPLETO, RecipeCostStatus.COSTE_ESTIMADO}: return False
        return True

    def to_dict(self) -> dict:
        return asdict(self)

def normalize_text_upper(value: Optional[str], fallback: str = "") -> str:
    if not value:
        return fallback
    return " ".join(str(value).strip().split()).upper()

def validate_imported_ingredient(ingredient: ImportedIngredient) -> ImportedIngredient:
    ingredient.normalized_name = normalize_text_upper(ingredient.normalized_name, "INGREDIENTE SIN NOMBRE")
    if not ingredient.original_text:
        ingredient.original_text = ingredient.normalized_name
    if ingredient.ingredient_type not in {"ARTICULO", "SUBRECETA"}:
        ingredient.ingredient_type = "ARTICULO"
        ingredient.match_status = ImportedIngredientStatus.PENDIENTE_REVISION
        ingredient.needs_admin_validation = True
        ingredient.add_note("Tipo de ingrediente no reconocido.")
    if ingredient.quantity_net is None or ingredient.quantity_net <= 0:
        ingredient.match_status = ImportedIngredientStatus.PENDIENTE_REVISION
        ingredient.needs_admin_validation = True
        ingredient.add_note("Cantidad neta pendiente o inválida.")
    if not ingredient.unit or ingredient.unit not in VALID_UNITS:
        ingredient.match_status = ImportedIngredientStatus.PENDIENTE_REVISION
        ingredient.needs_admin_validation = True
        ingredient.add_note("Unidad pendiente o no reconocida.")
    if ingredient.unit in LIQUID_UNITS_TO_REVIEW:
        ingredient.conversion_status = ConversionStatus.PENDIENTE_CONVERSION_PESO
        ingredient.needs_admin_validation = True
        ingredient.add_note("Unidad líquida detectada. System MAC prioriza kg/g.")
    if ingredient.ingredient_type == "SUBRECETA" and not ingredient.matched_subrecipe_id:
        ingredient.match_status = ImportedIngredientStatus.SUBRECETA_PENDIENTE
        ingredient.needs_admin_validation = True
        ingredient.add_note("Subreceta pendiente de vinculación.")
    if ingredient.match_status == ImportedIngredientStatus.VINCULADO_CATALOGO:
        ingredient.needs_admin_validation = False
    ingredient.calculate_gross_quantity()
    return ingredient

def validate_imported_recipe_draft(draft: ImportedRecipeDraft) -> ImportedRecipeDraft:
    draft.recipe_name = normalize_text_upper(draft.recipe_name, "SIN NOMBRE")
    if draft.recipe_name == "SIN NOMBRE":
        draft.import_status = RecipeImportStatus.PENDIENTE_REVISION
        draft.add_warning("Nombre de receta pendiente de revisión.")
    if draft.yield_quantity is None or draft.yield_quantity <= 0:
        draft.import_status = RecipeImportStatus.PENDIENTE_REVISION
        draft.add_warning("Rendimiento no definido o inválido.")
    if not draft.yield_unit or draft.yield_unit not in VALID_UNITS:
        draft.import_status = RecipeImportStatus.PENDIENTE_REVISION
        draft.add_warning("Unidad de rendimiento pendiente o no reconocida.")
    if not draft.ingredients:
        draft.import_status = RecipeImportStatus.PENDIENTE_REVISION
        draft.add_warning("No se detectaron ingredientes.")
    draft.ingredients = [validate_imported_ingredient(i) for i in draft.ingredients]
    draft.labor.calculate_labor_cost()
    if draft.has_critical_pending():
        draft.import_status = RecipeImportStatus.PENDIENTE_REVISION
    if draft.can_convert_to_master_recipe():
        draft.import_status = RecipeImportStatus.VALIDADA_PARA_CONVERTIR
    return draft

def candidate_from_dict(data: dict) -> CatalogCandidate:
    return CatalogCandidate(
        item_id=int(data.get("item_id") or 0),
        name=normalize_text_upper(data.get("name"), ""),
        similarity_score=float(data.get("similarity_score") or 0),
        reason=str(data.get("reason") or ""),
    )

def ingredient_from_dict(data: dict) -> ImportedIngredient:
    candidates = [candidate_from_dict(c) for c in data.get("candidates", []) if isinstance(c, dict)]
    return validate_imported_ingredient(ImportedIngredient(
        original_text=str(data.get("original_text") or ""),
        normalized_name=str(data.get("normalized_name") or ""),
        ingredient_type=data.get("ingredient_type") or "ARTICULO",
        quantity_net=data.get("quantity_net"),
        unit=data.get("unit"),
        waste_percent=float(data.get("waste_percent") or 0),
        quantity_gross=data.get("quantity_gross"),
        match_status=data.get("match_status") or ImportedIngredientStatus.PENDIENTE_ALTA,
        matched_item_id=data.get("matched_item_id"),
        matched_item_name=data.get("matched_item_name"),
        matched_subrecipe_id=data.get("matched_subrecipe_id"),
        matched_subrecipe_name=data.get("matched_subrecipe_name"),
        candidates=candidates,
        needs_admin_validation=bool(data.get("needs_admin_validation", True)),
        notes=data.get("notes"),
        original_quantity=data.get("original_quantity"),
        original_unit=data.get("original_unit"),
        conversion_status=data.get("conversion_status") or ConversionStatus.NO_REQUIERE_CONVERSION,
    ))

def labor_from_dict(data: dict | None) -> LaborInfo:
    data = data or {}
    labor = LaborInfo(
        prep_time_minutes=int(data.get("prep_time_minutes") or 0),
        cook_time_minutes=int(data.get("cook_time_minutes") or 0),
        rest_time_minutes=int(data.get("rest_time_minutes") or 0),
        people=int(data.get("people") or 1),
        hourly_cost=float(data.get("hourly_cost") or 14.0),
        labor_cost=float(data.get("labor_cost") or 0.0),
    )
    labor.calculate_labor_cost()
    return labor

def draft_from_ai_json(data: dict, provider: str = "none", model: str = "none", elapsed: float = 0.0, raw_input_text: Optional[str] = None, created_by: Optional[str] = None) -> ImportedRecipeDraft:
    ingredients = [ingredient_from_dict(i) for i in data.get("ingredients", []) if isinstance(i, dict)]
    draft = ImportedRecipeDraft(
        source_type=str(data.get("source_type") or "texto"),
        recipe_name=str(data.get("recipe_name") or "SIN NOMBRE"),
        recipe_type=str(data.get("recipe_type") or "RECETA"),
        category=str(data.get("category") or "OTRO"),
        subcategory=data.get("subcategory"),
        service_family=str(data.get("service_family") or "OTRO"),
        yield_quantity=data.get("yield_quantity"),
        yield_unit=str(data.get("yield_unit") or "kg"),
        portions=data.get("portions"),
        ingredients=ingredients,
        elaboration_steps=list(data.get("elaboration_steps") or []),
        allergens=list(data.get("allergens") or []),
        labor=labor_from_dict(data.get("labor")),
        import_status=str(data.get("import_status") or RecipeImportStatus.BORRADOR_IA),
        cost_status=str(data.get("cost_status") or RecipeCostStatus.NO_CALCULADO),
        confidence=float(data.get("confidence") or 0),
        warnings=list(data.get("warnings") or []),
        ia_provider=provider,
        ia_model=model,
        process_time_s=round(float(elapsed or 0), 2),
        raw_input_text=raw_input_text,
        raw_ia_json=data,
        created_by=created_by,
    )
    return validate_imported_recipe_draft(draft)
