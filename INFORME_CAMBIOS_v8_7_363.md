# Informe de cambios · v8_7_363

## Laboratorio
- Retirado el bloque duplicado de alta/carga de artículos del Laboratorio.
- Laboratorio queda dividido en bloques técnicos seguros:
  - Integraciones TPV / Ventas.
  - Continuidad / Anti-caída.
  - Conciliación albarán-factura-pago proveedor.
  - IA / OCR.

## Integraciones TPV / Ventas
- Añadidas tablas base TPV:
  - tpv_sources
  - tpv_sales_raw
  - tpv_sales
  - tpv_sale_lines
  - tpv_product_mappings
  - tpv_modifiers
  - tpv_modifier_rules
  - tpv_consumption_events
- Añadido normalizador común TPV LAB.
- Añadido simulador de venta TPV desde Laboratorio.
- Añadida revisión de insumos/componentes por receta para pruebas TPV.
- Consumo siempre en PREVIEW. No descuenta stock real.
- Modificadores ambiguos quedan en revisión.

## Continuidad / Anti-caída
- Añadidas tablas base:
  - connectivity_status_log
  - offline_event_queue
  - sync_conflicts
  - sync_devices
  - sync_runs
- Añadido simulador offline.
- Añadida sincronización LAB segura.
- Eventos críticos pasan a conflicto/revisión, no se aplican automáticamente.

## Conciliación albarán-factura-pago proveedor
- Añadidas tablas base documentales:
  - supplier_documents
  - supplier_document_reconciliations
  - supplier_payment_proposals
  - accounting_packages
- Añadido simulador de conciliación.
- Pago real desactivado. Siempre requiere validación humana final.

## Catálogo
- Renombrado “Precios proveedor” a “Comparativa proveedores”.
- Se mantiene como herramienta operativa distinta del Dashboard.

## Manual
- Añadido manual vivo de usuario en Markdown e imprimible HTML.
- Ruta: /manual/system-mac

## Limpieza paquete
- Raíz más limpia; documentación histórica archivada.

## Blindajes
- No se toca stock real desde TPV LAB.
- No se modifican recetas maestras por ventas o eventos offline.
- No se ejecutan pagos reales.
- Todo lo crítico queda en PREVIEW, revisión o conflicto.
