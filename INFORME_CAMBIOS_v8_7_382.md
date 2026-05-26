# INFORME CAMBIOS v8_7_382

## Objetivo
Añadir al Dashboard de Inicio una capa ejecutiva diaria alineada con System MAC:

- ventas del día/rango,
- coste teórico de ventas,
- food cost % diario,
- margen bruto,
- mermas,
- compras/entradas,
- separación Cocina / Barra / Total,
- sugerencias de venta por caducidad/rotación.

## Cambios técnicos

### Nuevo servicio
`backend/app/services/daily_business_dashboard_service.py`

Calcula de forma conservadora:

- ventas desde `pos_sales_daily` y, como fallback LAB, `tpv_sales`;
- coste teórico desde `pos_sales_item_daily`, `tpv_sale_lines`, recetas y cócteles si existen;
- compras/entradas Cocina desde `receipts` + `receipt_lines`;
- entradas Barra desde `bar_stock_movements` + `bar_items`;
- mermas Cocina desde `waste_records` confirmados;
- sugerencias de salida desde Producciones Bar con caducidad corta y artículos de coste alto.

### Inicio / Dashboard
`backend/app/templates/sections/inicio.html`

Añadido bloque:

- “Cuenta diaria del negocio”
- KPIs compactos
- tarjetas Cocina / Barra / Total
- sugerencias de venta por caducidad/rotación
- avisos de lectura

### Estilo visual
`backend/app/static/style.css`

Añadidos estilos oscuros y compactos para mantener coherencia con la paleta System MAC.

## Reglas de seguridad

- El dashboard solo lee datos.
- No modifica stock.
- No modifica precios.
- No genera descuentos.
- No ejecuta ventas.
- Food cost teórico y compras del día se muestran separados para evitar lecturas engañosas.

## Validaciones realizadas

- `python -m compileall app`: OK
- `node --check` en JS estáticos: OK
- Importación de app FastAPI: OK
- Inicio con dashboard diario: OK
- Rutas principales: OK

## Nota
El dashboard no inventa datos. Si no hay ventas TPV normalizadas, muestra estado vacío/listo y notas de integración.
