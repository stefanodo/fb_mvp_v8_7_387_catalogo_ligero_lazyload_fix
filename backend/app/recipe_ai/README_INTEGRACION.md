# System MAC · Recetas IA + Voz

## Objetivo

Importar recetas desde texto, foto, manuscrito y voz dictada.

La IA crea un `BORRADOR_IA`. No modifica recetas maestras directamente.

## Archivos

- `models.py`: estados, modelos internos, validación, bruto/neto/merma.
- `prompts.py`: prompts de texto, foto, voz y respuesta.
- `schemas.py`: limpia y valida JSON devuelto por IA.
- `ai_provider_service.py`: OpenAI, Claude y offline.
- `voice_service.py`: audio a texto y respuesta hablada.
- `unit_conversion_service.py`: g/kg, ud/docena, ml/l pendiente.
- `costing_service.py`: coste provisional con modelo actual.
- `storage_service.py`: SQLite seguro para borradores.
- `commit_service.py`: conversión controlada a receta oficial.
- `matching_service.py`: sugerencias Catálogo/Subrecetas.
- `router.py`: rutas API y pantallas mínimas.

## Integración mínima en main.py

```python
from .recipe_ai.router import router as recipe_ai_router
app.include_router(recipe_ai_router)
```

Si falla:

```python
from backend.app.recipe_ai.router import router as recipe_ai_router
app.include_router(recipe_ai_router)
```

## Botón para Recetas

```html
<section class="mac-card recipe-ai-card">
  <h2>Recetas IA</h2>
  <p>Importa recetas desde texto, foto o voz. Siempre se guardan como borrador.</p>
  <div class="recipe-ai-actions">
    <a class="btn btn-primary" href="/recipe-ai/ui/import-text">Importar por texto</a>
    <a class="btn btn-primary" href="/recipe-ai/ui/import-image">Importar por foto</a>
    <a class="btn btn-primary" href="/recipe-ai/ui/import-voice">Dictar por voz</a>
    <a class="btn btn-secondary" href="/recipe-ai/ui/drafts">Ver borradores IA</a>
  </div>
</section>
```

## Variables recomendadas

```bash
SYSTEM_MAC_DB_PATH=fb_mvp.db
RECIPE_AI_PROVIDER=auto
RECIPE_AI_PRIMARY=openai
RECIPE_AI_FALLBACK=claude
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
RECIPE_AI_UPLOAD_DIR=uploads/recipe_ai
RECIPE_VOICE_PROVIDER=openai
RECIPE_VOICE_STT_MODEL=gpt-4o-transcribe
RECIPE_VOICE_TTS_MODEL=gpt-4o-mini-tts
RECIPE_VOICE_NAME=alloy
```

## Pendiente al acoplar al ZIP real

En `router.py` hay que conectar:

```python
load_catalog_items()
load_subrecipes()
load_price_map()
load_subrecipe_cost_map()
```

En `commit_service.py` hay que ajustar columnas reales de recetas si tu esquema usa otros nombres.
