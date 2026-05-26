# INFORME CAMBIOS · v8_7_338

## Objetivo
Endurecer OÍDO ALFI para que no se quede en interpretación textual y deje propuestas operativas reales en cola revisable; añadir trazabilidad multiusuario en conteos de Inventario.

## Cambios aplicados

### OÍDO ALFI / intérprete operativo
- Normalización previa reforzada para errores y frases incompletas:
  - “quiero hacer una producción de pico de gallo”
  - “hacer producción pico gallo”
  - “preparar pico de gallo”
  - “producción de pico”
- Diccionario interno ampliado:
  - `pico gallo` → `pico de gallo`
  - `tomate / tomates / tom.` → `tomate`
  - `hacer / preparar / producir` → producción
  - `tirar / pérdida / merma / mal estado` → merma
  - `pedir / encargar / solicitar` → pedido
- El orquestador ahora prioriza intención operativa antes de consulta. Ejemplo: “hay una merma de tomates” ya no cae en consulta de stock por contener “hay”.
- Si detecta PRODUCCIÓN / MERMA / PEDIDO, intenta crear propuesta pendiente en la cola operativa.
- Producción sin cantidad queda como borrador pendiente, sin mover stock.
- Merma sin cantidad queda como merma pendiente, sin descontar stock.
- Pedido sin cantidad o ambiguo no se crea falsamente; devuelve aviso de aclaración.
- Salida pública de intención alineada con: PRODUCCIÓN, MERMA, PEDIDO, CONSULTA_STOCK, CONSULTA_PROVEEDOR, RECETA_IA, ALBARÁN_IA, NO_ENTENDIDO.

### Seguridad operativa
- No se confirma stock automáticamente.
- No se cierra pedido.
- No se valida producción.
- No se confirma merma.
- Toda acción creada queda pendiente de revisión humana.

### Inventario multiusuario
- Añadida migración segura de columnas en `inventory_counts`:
  - `original_counted_by_user_id`
  - `original_counted_by_name`
  - `original_counted_at`
  - `last_modified_by_user_id`
  - `last_modified_by_name`
  - `last_modified_at`
  - `previous_physical_qty`
  - `previous_count_unit`
  - `modified_count`
- Añadida tabla `inventory_count_audit` para histórico de cambios por línea.
- Al primer conteo se guarda quién contó inicialmente.
- Si otro usuario modifica una línea ya contada, se permite, pero queda constancia de valor anterior, valor nuevo, usuario y fecha/hora.
- En la UI de Inventario se muestra chip discreto de auditoría: “Contó: … · Modificado por … · Cambios: …”.

## Simulacro interno ejecutado
- Compilación Python completa: `python3 -m compileall -q backend/app` OK.
- Prueba de interpretación local:
  - “quiero hacer una producción de pico de gallo” → PRODUCCIÓN, borrador pendiente sin cantidad.
  - “hay una merma de tomates” → MERMA, pendiente, sin descontar stock.
  - “pedir tomate” → no crea línea falsa si falta cantidad/ambigüedad.
- Prueba de esquema Inventario:
  - creación de columnas de auditoría OK.
  - simulación de conteo inicial + modificación posterior OK.
  - limpieza posterior de datos de prueba realizada.

## Pendiente conocido
- Si no existe una receta real “PICO DE GALLO” en la base, la producción queda como propuesta pendiente sin vínculo (`item_ref_id=0`). Esto es intencionado: no inventa receta ni confirma producción.
