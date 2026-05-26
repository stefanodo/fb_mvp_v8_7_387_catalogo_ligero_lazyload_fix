# INFORME CAMBIOS · v8_7_324

## Corrección principal
Se corrige la navegación de Inventario en “Paso 1 · Elige bloque”.

Problema observado:
- Al intentar cambiar entre Materias primas / Producciones / Limpieza / Líneas libres, el sistema podía quedarse en el bloque anterior o devolver `warehouse_invalid`.
- En la práctica parecía que solo funcionaba cambiar la familia del Paso 2.

Causa técnica:
- Antes de cambiar de bloque, la interfaz guardaba la sesión actual.
- Si la sesión conservaba un `warehouse_id` no válido para el local activo, el guardado devolvía `warehouse_invalid` y el cambio de bloque quedaba confuso.
- Además, el formulario oculto de sesión no sincronizaba siempre `inv_mode` e `inv_family` con el botón de bloque pulsado antes de guardar.

Corrección aplicada:
- Se normaliza `warehouse_id`: si no pertenece al local activo, se vuelve automáticamente a `Todos` en vez de bloquear la navegación.
- Al pulsar un bloque, el JS copia el `inv_mode` y `inv_family` destino al formulario antes de guardar la sesión.
- Se mantiene el scroll en la zona de trabajo del inventario.

## Limpieza de paquete
- Se limpia la raíz del ZIP.
- Documentación técnica antigua, informes working y comandos históricos se archivan en `docs_historico/`.
- En raíz quedan solo archivos esenciales de uso diario y versión actual.

## No tocado
- OCR de albaranes.
- Voz/dictado antiguo.
- Recetas IA LAB funcionalmente.
- Cálculos de stock ya existentes.

## Validaciones
- Compilación Python de router de inventario: OK.
- Compilación backend/app completa: OK.
- Revisión de raíz del paquete: OK.
