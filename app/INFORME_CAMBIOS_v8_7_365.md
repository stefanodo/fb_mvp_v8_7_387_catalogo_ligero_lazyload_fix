# INFORME CAMBIOS v8_7_365 · Pedidos Cocina + Barra LAB

## Cambios aplicados

- Añadido simulador LAB de pedidos consolidados Cocina + Coctelería/Barra.
- Cada área calcula necesidades de pedido con stock mínimo/máximo propio.
- La consolidación se hace solo a nivel proveedor/artículo/unidad compatible.
- La recepción reparte automáticamente entre Stock Cocina y Stock Bar si la cantidad recibida coincide con el pedido consolidado.
- Si hay diferencia de cantidad, el sistema deja la línea en revisión y no valida stock.
- Alcoholes, mixers y bebidas específicas quedan como `bar_only`.
- Lima, limón, naranja, hierbabuena, azúcar y sal quedan como `common_purchase_split_stock` en demo.

## Nuevas tablas LAB

- `lab_consolidated_order_runs`
- `lab_area_order_lines`
- `lab_consolidated_order_lines`
- `lab_receipt_split_lines`

## Nuevos endpoints

- `POST /api/lab/bar/orders/simulate`
- `GET /api/lab/bar/orders/summary`

## Seguridad

- No crea pedidos reales.
- No modifica Stock Cocina.
- No modifica Stock Bar productivo.
- No envía nada a proveedores.
- Todo queda marcado como demo/no productivo.

## Simulacro interno

Prueba recepción correcta:
- 11 líneas por área.
- 8 líneas consolidadas.
- Lima, azúcar y sal consolidadas con reparto Cocina/Barra.
- Ginebra, ron y tónica quedan como Barra independiente.
- Tomate queda como Cocina independiente.
- Recepción correcta: `ok_auto_split`.

Prueba con diferencia:
- Pedido Lima: 11.700 gr.
- Recibido Lima: 11.000 gr.
- Estado: `revision_diferencia_cantidad`.
- No valida stock; propone reparto proporcional para revisión humana.
