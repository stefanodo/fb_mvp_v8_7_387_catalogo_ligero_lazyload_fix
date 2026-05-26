# INFORME CAMBIOS v8_7_367

- Añadido LAB de albarán/OCR bebidas hacia Stock Bar e Inventario Bar.
- Añadidas tablas demo/no productivas: bar_receipts, bar_receipt_lines, bar_supplier_item_prices, bar_stock_balances, bar_inventory_movements, bar_receipt_cost_recalc_log.
- Añadido control de mixers/refrescos multi-servicio: botella 1L/2L, envase abierto, ml usados/restantes, gas/caducidad.
- Al validar albarán de bebidas LAB: crea entrada Stock Bar, actualiza coste artículo de barra, actualiza inventario Bar y recalcula cócteles/bebidas afectados.
- Líneas compartidas Cocina/Barra quedan en revisión; no se toca Stock Cocina sin reparto validado.
- Todo demo_data=true y non_productive_demo=true.
