# System MAC · Informe de cambios v8_7_356

## Catálogo / Artículos
- Compactado el bloque **Añadir artículo** para que en escritorio quede en un máximo de 3 líneas.
- Línea 1: nombre/nomenclatura comercial y proveedor habitual opcional.
- Línea 2: unidad base, tipo, precio actual y ubicación de stock.
- Línea 3: categoría de pedido, merma, ayuda breve y botón de alta.
- Eliminadas ayudas largas repetidas dentro del bloque para reducir altura visual.
- Si se elige proveedor habitual, el alta usa el `supplier_id` ya soportado por backend para vincular precio proveedor.
- Mantiene responsive: en tablet/móvil se apila sin solapes.

## Verificaciones
- Sintaxis Jinja del parcial de artículos revisada.
- Compilación backend `compileall`: OK.
- Import de FastAPI: OK.
