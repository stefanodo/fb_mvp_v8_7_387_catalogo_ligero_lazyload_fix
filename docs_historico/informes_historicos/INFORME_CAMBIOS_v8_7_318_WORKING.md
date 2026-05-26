# INFORME CAMBIOS v8_7_318 WORKING

Estado: aplicado en carpeta de trabajo. ZIP no generado.

## Objetivo
Cruzar la sugerencia de proveedor alternativo más barato con condiciones reales de compra para evitar recomendaciones engañosas.

## Cambios

1. Dashboard proveedores/margen:
   - La alternativa no se evalúa solo por precio.
   - Ahora incorpora mínimos de pedido, días de reparto y plazo de entrega.
   - Si el proveedor alternativo es barato pero queda bajo mínimo, aparece como `BAJO_MINIMO`.
   - Si tiene plazo de entrega o regla de reparto, se muestra la próxima fecha de reparto estimada.

2. Proveedores:
   - Migración aditiva de columnas:
     - `delivery_days`
     - `delivery_min_order_amount`
     - `delivery_min_tax_mode`
     - `delivery_lead_time_days`
     - `delivery_notes`

3. Orden de recomendación:
   - Primero alternativas operativamente viables.
   - Luego alternativas que requieren revisión.
   - Último: alternativas bajo mínimo o con bloqueo operativo.

4. Informe imprimible mensual de proveedores:
   - Añade columna de reparto/mínimo/plazo.
   - Mantiene nota de revisión obligatoria.

## Blindaje

- No cambia proveedor automáticamente.
- No infla pedido para llegar al mínimo.
- No inventa calidad ni fiabilidad del proveedor.
- No compra ni confirma nada.
- Si falta configuración de reparto, se muestra como `sin regla` y requiere revisión operativa.

## Validaciones

- Compilación `core.py`: OK.
- Compilación `monthly_supplier_dashboard_service.py`: OK.
- Migración columnas proveedor: OK.
- Parseo reparto `lunes, miércoles, viernes`: OK.
- Simulación alternativa bajo mínimo: OK.
- `build_monthly_supplier_dashboard()`: OK.
- OCR no tocado.
- Dictado/voz no tocado.
- Recetas IA laboratorio no acoplado.
- ZIP no generado.
