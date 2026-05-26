# System MAC · F&B MVP — Agent Instructions

## What this project is
Multi-restaurant F&B management system (stock, recipes, productions, orders, AI recipe import, executive dashboards). Built for local Mac use with optional Vercel/PostgreSQL deployment.

## Stack
- **Backend**: Python + FastAPI + Jinja2 templates (no separate frontend framework)
- **DB (local)**: SQLite WAL at `~/Documents/F&B_MAC_RUNTIME/fb_mvp_v8.db` — **not in the repo**
- **DB (production)**: PostgreSQL via `DATABASE_URL` env var (Vercel)
- **AI**: OpenAI (primary) → Claude (fallback) → Offline (always available)
- **OCR**: PaddleOCR + Tesseract + Pillow (receipt/image parsing)

## Key directories
```
backend/app/
  main.py          ← FastAPI entry point, registers all routers
  core.py          ← DB connection, shared helpers, BUILD_ID, business constants
  db_config.py     ← SQLite/PostgreSQL dual-mode connection helper
  routers/         ← One file per domain: stock, recetas, producciones, pedidos,
                      albaranes, laboratorio, admin, inventario, mermas, operativa, ai_system
  recipe_ai/       ← AI recipe import module (text/photo/voice → draft → master)
  services/        ← Dashboard and business logic services
  templates/       ← Jinja2 HTML templates
  static/          ← CSS/JS/images
  ocr/             ← OCR engine (isolated)
api/index.py       ← Vercel entry point
```

## How to run locally
```bash
# Start server (installs deps, opens Safari at /movil)
./INICIAR_F&B_MVP.command

# Or directly:
cd backend && python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Server runs on port 8000. Runtime DB and uploads live in `~/Documents/F&B_MAC_RUNTIME/`.

## Conventions
- **Language**: UI, comments, and business-domain code are in **Spanish**. Keep this consistent.
- **Build ID**: Defined in `backend/app/core.py` as `BUILD_ID`. Update it on each release.
- **Version tracking**: `VERSION_BUILD.txt` + `INFORME_CAMBIOS_v8_7_NNN.md` per release.
- **Ingredients**: System MAC uses **weight-first** (g/kg). Liquid units (ml/l) require explicit conversion and are flagged as `PENDIENTE_CONVERSION_PESO`.
- **Units**: Valid set — `{"g", "kg", "ud", "racion", "docena", "ml", "l"}`.
- **Recipe AI drafts**: Always saved as `BORRADOR_IA`. Never auto-converted to master recipes. Requires `RECIPE_AI_ALLOW_COMMIT=1` env var + human validation (`VALIDADA_PARA_CONVERTIR` status).
- **DB connections**: Use `core.db()` for SQLite (WAL mode, 240 s busy_timeout). Do not create raw connections outside `core.py` except in `db_config.py`.
- **`app/` folder**: Legacy alias — launchers inside redirect to root. The **active backend is `backend/`**, not `app/backend/`.

## Environment variables
| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | OpenAI API (recipes AI, STT, TTS) |
| `ANTHROPIC_API_KEY` | Claude fallback for recipe AI |
| `DATABASE_URL` | PostgreSQL URL in production; absence = SQLite |
| `FB_MVP_RUNTIME_DIR` | Override default runtime dir |
| `RECIPE_AI_ALLOW_COMMIT` | Set to `1` to enable draft→master conversion |
| `OPERATIVA_AI_MODE` | `openai` or `local` |

## Recipe AI module (`backend/app/recipe_ai/`)
- `models.py` — dataclasses: `ImportedRecipeDraft`, `ImportedIngredient`, status enums
- `ai_provider_service.py` — provider chain (OpenAI → Claude → Offline)
- `prompts.py` — system prompts for text/image/voice extraction
- `schemas.py` — JSON parsing and normalization from AI response
- `storage_service.py` — SQLite persistence for drafts
- `commit_service.py` — controlled draft→master conversion (gated by env var)
- `costing_service.py` — cost preview before committing
- `voice_service.py` — STT + recipe extraction + TTS response
- `router.py` — FastAPI routes (`/recipe-ai/...`)
- See [recipe_ai/README_INTEGRACION.md](backend/app/recipe_ai/README_INTEGRACION.md) for integration details.

## Adding a new feature
1. Create a router in `backend/app/routers/` or a service in `backend/app/services/`.
2. Register the router in `backend/app/main.py`.
3. Add templates to `backend/app/templates/` and static assets to `backend/app/static/`.
4. Update `BUILD_ID` in `core.py` and create the corresponding `INFORME_CAMBIOS_v8_7_NNN.md`.

## Pitfalls
- **Never write to `~/Documents/F&B_MAC_RUNTIME/`** in tests — mock `DB_PATH` or use a temp path.
- **Do not import `paddleocr` at module level** — it's optional and may not be installed.
- **Concurrent SQLite writes** are handled by WAL + busy_timeout; avoid long transactions.
- **HEIC/HEIF images** from iPhone are normalized to JPG via `sips` (macOS) before processing.
- **`app/` subdirectory** mirrors the root structure for legacy compatibility — do not add new logic there.
