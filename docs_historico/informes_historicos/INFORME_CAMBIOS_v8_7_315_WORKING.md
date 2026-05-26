# INFORME CAMBIOS · v8_7_315_WORKING

Estado: aplicado en carpeta de trabajo. ZIP no generado.

## Bloque aplicado
Dashboard mensual de dirección: filtros de mes/año e informe imprimible.

## Cambios
- Inicio permite elegir mes y año para el dashboard mensual de inventario.
- Añadida ruta `/direction/monthly/print` para informe imprimible/guardable como PDF.
- El informe agrupa por proveedor, rubro y local, con pérdidas, sobrantes, neto, diferencias graves y recomendaciones.
- Mantiene orden alfabético en proveedor y rubro.
- No modifica stock, pedidos, recetas ni inventarios.

## Archivos tocados
- `backend/app/main.py`
- `backend/app/templates/sections/inicio.html`
- `backend/app/templates/reports/monthly_direction_inventory.html`
- `backend/app/static/style.css`
- `VERSION_BUILD.txt`
- `app/VERSION_BUILD.txt`

## No tocado
- OCR.
- Dictado/voz antiguo.
- Recetas IA laboratorio.
- Confirmación de pedidos.
- Movimientos de stock.

## Validaciones previstas/realizadas
- Compilación Python backend/app.
- Importación app principal.
- Render Inicio.
- Render informe imprimible.
