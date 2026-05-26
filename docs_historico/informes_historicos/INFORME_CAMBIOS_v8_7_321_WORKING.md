# INFORME CAMBIOS v8_7_321 · Admin modificadores TPV

Estado: WORKING · NO ZIP generado.

## Objetivo
Preparar una administración intuitiva para que los modificadores que vienen del TPV puedan traducirse a consumo real de stock sin alterar recetas maestras.

## Cambios aplicados

1. Nueva pestaña en Admin:
   - `Admin → Modificadores TPV`.

2. Creación de modificadores internos:
   - receta específica o modificador genérico,
   - tipo: SIN, EXTRA, SUSTITUIR, GUARNICIÓN, SALSA, PUNTO_COCCION, OBSERVACIÓN_NO_STOCK, REVIEW,
   - acción de stock: ADD_ITEM, SUBTRACT_ITEM, REPLACE, ADD_SUBRECIPE, SUBTRACT_SUBRECIPE, NO_STOCK, REVIEW,
   - artículo afectado,
   - cantidad delta,
   - unidad,
   - afecta/no afecta stock,
   - precio extra opcional,
   - notas.

3. Mapeo de nombres TPV:
   - texto que llega del TPV,
   - normalización interna,
   - modificador System MAC,
   - receta/negocio/proveedor TPV opcional.

4. Desactivación segura:
   - los modificadores y mapeos se desactivan; no se borran físicamente.

5. Blindaje operativo:
   - la receta maestra no se modifica,
   - solo modificadores mapeados pueden convertirse en delta de stock,
   - modificadores desconocidos quedan para mapeo/revisión,
   - no se inventan consumos.

## Archivos modificados

- `backend/app/services/pos_modifiers_service.py`
- `backend/app/routers/admin.py`
- `backend/app/main.py`
- `backend/app/templates/partials/admin_tabs.html`
- `backend/app/templates/sections/admin.html`
- `backend/app/templates/partials/admin_tab_modificadores_tpv.html`
- `VERSION_BUILD.txt`
- `app/VERSION_BUILD.txt`
- `HANDOVER_INTERNO_CONTINUIDAD.md`

## Validaciones realizadas

- Compilación Python: OK.
- Importación app principal: OK.
- Servicio `list_recipe_modifiers_admin`: OK.
- Creación simulada de modificador EXTRA QUESO: OK.
- Mapeo simulado `EXTRA CHEESE TEST`: OK.
- Delta calculado: 2 ventas × 20 g = +40 g: OK.
- Render `/?page=admin`: HTTP 200 OK.
- Texto `Modificadores TPV` presente en HTML: OK.
- OCR no tocado.
- Dictado/voz no tocado.
- Recetas IA laboratorio no acoplado.
- ZIP no generado.
