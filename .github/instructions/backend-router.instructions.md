---
description: "Use when creating or modifying backend routers, services, or Jinja2 templates. Covers DB access patterns, router registration, template conventions, and naming rules for System MAC F&B MVP."
applyTo: ["backend/app/routers/**", "backend/app/services/**", "backend/app/templates/**", "backend/app/main.py"]
---

# Backend Router & Service Conventions

## DB access
- Always use `core.db()` — never create raw `sqlite3.connect()` outside `core.py` or `db_config.py`.
- Use context manager pattern: `with db() as conn:` or call `conn.close()` in a `finally`.
- Do not hold connections across `await` calls or between requests.

## Adding a new router
1. Create `backend/app/routers/<domain>.py` with `router = APIRouter(prefix="/<domain>", tags=["<Domain>"])`.
2. Import and register in `backend/app/main.py`:
   ```python
   from app.routers import <domain>
   app.include_router(<domain>.router)
   ```
3. Name template files `templates/<domain>_*.html`.

## Adding a new service
- Place pure business logic (no FastAPI imports) in `backend/app/services/<domain>_service.py`.
- Services receive `conn` or `db_path` as arguments; they do not open DB connections themselves.
- Import the service function in the relevant router — keep routes thin.

## Jinja2 templates
- Templates live in `backend/app/templates/`.
- Pass `BUILD_ID` via context for cache-busting: `{"build": BUILD_ID, ...}`.
- Use `{{ human_qty(...) }}`, `{{ fmt_price(...) }}` and other helpers from `core.py` for display formatting — do not reimplement them in templates.
- Static assets are served from `/static/`; reference them as `{{ url_for('static', path='...') }}`.

## Error handling
- Return `JSONResponse({"ok": False, "error": "..."}, status_code=4xx)` for API errors.
- For HTML routes, redirect to the listing page or re-render the form with an error message.
- Do not expose raw Python exceptions to the client.

## Language
- Route paths, function names, and Python variables: English or Spanish as already established per domain.
- All user-facing strings, template text, and business-logic constants: **Spanish**.
- Comments in new code: Spanish preferred, consistent with surrounding code.

## Units & ingredients
- Prefer weight (`g`/`kg`). Liquid units (`ml`/`l`) must be flagged as `PENDIENTE_CONVERSION_PESO`.
- Valid unit set: `{"g", "kg", "ud", "racion", "docena", "ml", "l"}`.
- Import `VALID_UNITS` from `core.py` rather than redefining the set.
