# INFORME CAMBIOS v8_7_317_WORKING

## Bloque aplicado
Dashboard proveedores/margen: recomendación de proveedor alternativo más barato para artículos caros o con mayor impacto.

## Lógica
- Para cada artículo/proveedor comparable del periodo, se busca en `supplier_item_prices` otro proveedor activo para el mismo artículo.
- El precio se normaliza por unidad base: `price_per_purchase / purchase_to_base_factor`.
- Se excluye el proveedor actual.
- Solo se sugiere alternativa si el precio normalizado es menor que el precio actual comparable.
- Calcula ahorro por unidad, ahorro porcentual y ahorro mensual estimado usando cantidad mensual del artículo/proveedor.

## Blindaje
- No cambia proveedor automáticamente.
- No modifica artículos, pedidos, albaranes, recetas ni stock.
- La recomendación exige revisión de calidad, formato, mínimo de pedido y días de reparto.
- Si no hay proveedor alternativo más barato, no inventa recomendación.

## UI
- Inicio: bloque “Proveedor alternativo más barato”.
- Informe imprimible mensual de proveedores: sección con proveedor actual, precio actual, proveedor sugerido, precio sugerido, ahorro por unidad y ahorro mensual estimado.

## Validaciones
- Compilación del servicio monthly_supplier_dashboard_service: OK.
- Importación y ejecución de build_monthly_supplier_dashboard(): OK.
- OCR no tocado.
- Dictado/voz no tocado.
- Recetas IA laboratorio no acoplado.
- ZIP no generado.
