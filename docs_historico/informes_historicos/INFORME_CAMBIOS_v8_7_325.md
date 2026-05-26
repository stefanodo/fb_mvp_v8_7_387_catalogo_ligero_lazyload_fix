# INFORME CAMBIOS v8_7_325

## Corrección aplicada

Se corrige Inventario > Producciones para permitir conteo en unidades operativas de cocina:

- g
- kg
- ración
- lote
- ud

## Lógica

En producciones, el inventario puede contarse como raciones o lotes. El sistema mantiene la cantidad física introducida y la unidad original del conteo. En cierre/conciliación, si existe receta vinculada:

- 1 ración = rendimiento final de la receta / nº de raciones.
- 1 lote = rendimiento final completo de la receta.

Si la receta no tiene rendimiento o raciones suficientes, no inventa conversión fiable: mantiene aviso técnico en la nota de ajuste.

## Vista de inventario

En las líneas de producción se muestra también la referencia de receta:

- lote de receta
- unidad del rendimiento
- número de raciones

Ejemplo: `Receta: lote 2 kg · 20 raciones`.

## No tocado

- OCR de albaranes.
- Dictado/voz antiguo.
- Recetas IA LAB funcionalmente.
- Recetas maestras.

## Validación

- Compilación Python backend/app: OK.
- Importación app principal: OK.
- Router inventario: OK.
- Sintaxis plantillas Jinja: revisada por carga de app.
