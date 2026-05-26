from __future__ import annotations
import os, time, base64, logging, json
from pathlib import Path
from typing import Optional, Protocol
from .prompts import build_recipe_import_prompt
from .schemas import parse_and_normalize_ai_response, RecipeAISchemaError
from .models import ImportedRecipeDraft, draft_from_ai_json, LaborInfo, RecipeCostStatus, RecipeImportStatus

logger = logging.getLogger(__name__)

class RecipeAIConfig:
    provider_mode: str = os.environ.get("RECIPE_AI_PROVIDER", "auto").lower()
    primary_provider: str = os.environ.get("RECIPE_AI_PRIMARY", "openai").lower()
    fallback_provider: str = os.environ.get("RECIPE_AI_FALLBACK", "claude").lower()
    openai_text_model: str = os.environ.get("RECIPE_AI_TEXT_MODEL", "gpt-4o")
    openai_vision_model: str = os.environ.get("RECIPE_AI_VISION_MODEL", "gpt-4o")
    claude_model: str = os.environ.get("RECIPE_AI_CLAUDE_MODEL", "claude-3-5-sonnet-latest")
    max_tokens: int = int(os.environ.get("RECIPE_AI_MAX_TOKENS", "4096"))

class RecipeAIProvider(Protocol):
    name: str
    model: str
    def available(self) -> bool: ...
    def extract_from_text(self, prompt: str, text: str) -> str: ...
    def extract_from_image(self, prompt: str, image_path: str) -> str: ...

def encode_image_as_data_url(path: str) -> str:
    p = Path(path)
    if not p.exists(): raise FileNotFoundError(f"Imagen no encontrada: {path}")
    media_type = {".jpg":"image/jpeg",".jpeg":"image/jpeg",".png":"image/png",".webp":"image/webp"}.get(p.suffix.lower(), "image/jpeg")
    return f"data:{media_type};base64,{base64.b64encode(p.read_bytes()).decode('utf-8')}"

def encode_image_base64(path: str) -> tuple[str, str]:
    p = Path(path)
    if not p.exists(): raise FileNotFoundError(f"Imagen no encontrada: {path}")
    media_type = {".jpg":"image/jpeg",".jpeg":"image/jpeg",".png":"image/png",".webp":"image/webp"}.get(p.suffix.lower(), "image/jpeg")
    return base64.b64encode(p.read_bytes()).decode("utf-8"), media_type

class OpenAIRecipeProvider:
    name = "openai"
    def __init__(self, config: RecipeAIConfig):
        self.config, self.model, self._client = config, config.openai_text_model, None
    def available(self) -> bool: return bool(os.environ.get("OPENAI_API_KEY"))
    def _client_or_raise(self):
        if not self.available(): raise EnvironmentError("OPENAI_API_KEY no configurada.")
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        return self._client
    def extract_from_text(self, prompt: str, text: str) -> str:
        client = self._client_or_raise(); self.model = self.config.openai_text_model
        r = client.responses.create(model=self.model, input=[{"role":"system","content":prompt},{"role":"user","content":text}], max_output_tokens=self.config.max_tokens)
        return r.output_text
    def extract_from_image(self, prompt: str, image_path: str) -> str:
        client = self._client_or_raise(); self.model = self.config.openai_vision_model
        data_url = encode_image_as_data_url(image_path)
        r = client.responses.create(model=self.model, input=[{"role":"system","content":prompt},{"role":"user","content":[{"type":"input_text","text":"Analiza esta receta y devuelve SOLO JSON válido."},{"type":"input_image","image_url":data_url}]}], max_output_tokens=self.config.max_tokens)
        return r.output_text

class ClaudeRecipeProvider:
    name = "claude"
    def __init__(self, config: RecipeAIConfig):
        self.config, self.model, self._client = config, config.claude_model, None
    def available(self) -> bool: return bool(os.environ.get("ANTHROPIC_API_KEY"))
    def _client_or_raise(self):
        if not self.available(): raise EnvironmentError("ANTHROPIC_API_KEY no configurada.")
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        return self._client
    def extract_from_text(self, prompt: str, text: str) -> str:
        client = self._client_or_raise()
        r = client.messages.create(model=self.model, max_tokens=self.config.max_tokens, system=prompt, messages=[{"role":"user","content":text}])
        return r.content[0].text
    def extract_from_image(self, prompt: str, image_path: str) -> str:
        client = self._client_or_raise()
        b64, media_type = encode_image_base64(image_path)
        r = client.messages.create(model=self.model, max_tokens=self.config.max_tokens, system=prompt, messages=[{"role":"user","content":[{"type":"image","source":{"type":"base64","media_type":media_type,"data":b64}},{"type":"text","text":"Analiza esta receta y devuelve SOLO JSON válido."}]}])
        return r.content[0].text

class OfflineRecipeProvider:
    name, model = "offline", "offline-manual-review"
    def __init__(self, config: RecipeAIConfig): self.config = config
    def available(self) -> bool: return True
    def _payload(self, source_type: str, warning: str) -> str:
        return json.dumps({"source_type": source_type, "recipe_name": "RECETA PENDIENTE DE REVISION", "recipe_type": "RECETA", "category": "OTRO", "subcategory": None, "service_family": "OTRO", "yield_quantity": None, "yield_unit": "kg", "portions": None, "ingredients": [], "elaboration_steps": [], "allergens": [], "labor": {"prep_time_minutes":0,"cook_time_minutes":0,"rest_time_minutes":0,"people":1,"hourly_cost":14,"labor_cost":0}, "import_status": "PENDIENTE_REVISION", "cost_status": "COSTE_NO_CALCULABLE", "confidence": 0, "warnings": [warning]}, ensure_ascii=False)
    def extract_from_text(self, prompt: str, text: str) -> str:
        return self._payload("texto", "Modo offline: no se llamó a IA. Texto pendiente de revisión.")
    def extract_from_image(self, prompt: str, image_path: str) -> str:
        return self._payload("foto", "Modo offline: imagen pendiente de revisión manual.")

class RecipeAIService:
    def __init__(self, catalog_items: Optional[list[dict]] = None, subrecipes: Optional[list[dict]] = None, config: Optional[RecipeAIConfig] = None):
        self.config = config or RecipeAIConfig()
        self.catalog_items, self.subrecipes = catalog_items or [], subrecipes or []
        self.providers = {"openai": OpenAIRecipeProvider(self.config), "claude": ClaudeRecipeProvider(self.config), "offline": OfflineRecipeProvider(self.config)}
    def _provider_order(self, task_type: str) -> list[str]:
        mode = self.config.provider_mode
        if mode in {"openai","claude","offline"}: return [mode, "offline"] if mode != "offline" else ["offline"]
        order = ["openai","claude","offline"] if task_type == "voz" else [self.config.primary_provider, self.config.fallback_provider, "offline"]
        return [x for i, x in enumerate(order) if x in self.providers and x not in order[:i]]
    def _run(self, task_type: str, input_value: str, created_by: Optional[str] = None) -> ImportedRecipeDraft:
        prompt = build_recipe_import_prompt(self.catalog_items, self.subrecipes, task_type)
        last_error = None
        for name in self._provider_order(task_type):
            provider = self.providers[name]
            if not provider.available(): continue
            start = time.perf_counter()
            try:
                raw = provider.extract_from_image(prompt, input_value) if task_type == "foto" else provider.extract_from_text(prompt, input_value)
                normalized = parse_and_normalize_ai_response(raw)
                return draft_from_ai_json(normalized, provider=provider.name, model=provider.model, elapsed=time.perf_counter()-start, raw_input_text=input_value if task_type != "foto" else None, created_by=created_by)
            except Exception as exc:
                last_error = str(exc); logger.warning("Proveedor %s falló: %s", name, exc)
        return ImportedRecipeDraft(source_type=task_type, recipe_name="ERROR IMPORTACION IA", recipe_type="RECETA", category="OTRO", service_family="OTRO", yield_quantity=None, yield_unit="kg", portions=None, ingredients=[], elaboration_steps=[], allergens=[], labor=LaborInfo(), import_status=RecipeImportStatus.PENDIENTE_REVISION, cost_status=RecipeCostStatus.COSTE_NO_CALCULABLE, confidence=0, warnings=["No se pudo procesar la receta con ningún proveedor IA.", last_error or "Error desconocido."], raw_input_text=input_value if task_type != "foto" else None, created_by=created_by)
    def import_from_text(self, text: str, created_by: Optional[str] = None) -> ImportedRecipeDraft: return self._run("texto", text, created_by)
    def import_from_voice_text(self, text: str, created_by: Optional[str] = None) -> ImportedRecipeDraft: return self._run("voz", text, created_by)
    def import_from_image(self, image_path: str, created_by: Optional[str] = None) -> ImportedRecipeDraft: return self._run("foto", image_path, created_by)
