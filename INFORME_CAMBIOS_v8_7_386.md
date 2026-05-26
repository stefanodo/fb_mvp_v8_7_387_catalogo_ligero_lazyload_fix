# INFORME CAMBIOS v8_7_386 · Mobile + ALFI para flujos críticos

## Objetivo
Implementar una primera capa segura para tres flujos operativos críticos, usable desde móvil y desde OÍDO ALFI, sin tocar stock productivo ni romper módulos existentes.

## Flujos implementados en modo LAB seguro

1. **Corrección/anulación de validaciones**
   - Producción/inventario/merma/albarán/pedido ya validado por error.
   - Crea propuesta de reverso/ajuste con impacto.
   - Registra usuario, hora, motivo, antes/después e impacto previsto.

2. **Sugerencias de pedidos editables por línea**
   - Mantiene cantidad sugerida original.
   - Permite cantidad final, prioridad, nota, proveedor y motivo.
   - No genera pedido real hasta futura confirmación productiva.

3. **Racionado/despiece/porcionado**
   - Pieza origen, peso bruto, merma, neto útil, coste útil/kg.
   - Reparte salida entre varios destinos/platos.
   - Crea lote y coste proporcional por destino.

## Doble vía de uso

- Pantalla móvil guiada dentro de Laboratorio > Operativa móvil + ALFI.
- Comando ALFI seguro que genera prelectura, no ejecuta acciones críticas.

## Nuevas tablas LAB

- critical_flow_drafts
- critical_flow_audit
- order_suggestion_review_runs
- order_suggestion_review_lines
- portioning_batches
- portioning_outputs

Todas quedan marcadas como `demo_data=1` y `non_productive_demo=1`.

## Endpoints añadidos

- GET `/api/lab/critical/summary`
- POST `/api/lab/critical/simulate`
- POST `/api/lab/critical/alfi-preview`
- POST `/api/lab/critical/confirm`

## Simulacro ejecutado

- Corrección de producción: tomate 5 kg → 3 kg, impacto +2 kg stock preview.
- Pedido sugerido: tomate 16 kg → 20 kg, perejil quitado, lima mantenida.
- Racionado: atún 10 kg, merma 1,2 kg, neto 8,8 kg, reparto Tataki/Tartar/Especiales.

## Conclusiones

- Hay base suficiente para implementar la capa segura de prelectura móvil + ALFI.
- La ejecución productiva real debe conectarse módulo por módulo para no romper stock, costes ni inventario.
- El siguiente paso lógico es conectar primero Pedidos sugeridos editables, después Correcciones, y después Racionado productivo.
