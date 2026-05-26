# System MAC · v8_7_316 WORKING · Dashboard mensual proveedores/margen

Estado: cambios aplicados en carpeta de trabajo. ZIP no generado.

## Bloques agrupados aplicados

1. Dashboard mensual de proveedores/precios.
2. Detección de subidas/bajadas comparables por artículo + proveedor.
3. Impacto económico estimado del mes por consumo comprado en albaranes.
4. Proveedores con mayor riesgo económico.
5. Artículos causantes de subida.
6. Recetas afectadas por ingredientes que subieron.
7. Informe imprimible mensual de proveedores y margen.

## Blindajes

- Lectura pura: no modifica stock, recetas, pedidos, albaranes ni inventario.
- No inventa subidas si no hay precio anterior comparable del mismo artículo/proveedor.
- Los artículos sin histórico quedan separados como "sin histórico previo".
- No toca OCR.
- No toca dictado/voz.
- Recetas IA laboratorio no acoplado.
- ZIP no generado.

## Archivos modificados

- backend/app/services/monthly_supplier_dashboard_service.py
- backend/app/main.py
- backend/app/templates/sections/inicio.html
- backend/app/templates/reports/monthly_supplier_direction.html
- backend/app/static/style.css
- VERSION_BUILD.txt
- app/VERSION_BUILD.txt

## Validaciones previstas/ejecutadas

- Compilación Python backend/app.
- Importación del servicio mensual de proveedores.
- Construcción del dashboard con DB actual.
- Render de Inicio.
- Render del informe imprimible.
