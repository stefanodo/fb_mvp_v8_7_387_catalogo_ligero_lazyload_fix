# System MAC · Informe de cambios v8_7_362

## Bloque corregido: Catálogo > Artículos

### Problema detectado
- El botón **Guardar todas las modificaciones** no se activaba aunque el usuario modificara varias filas.
- Al pulsar **Guardar** en una sola línea, la página se recargaba, saltaba arriba y se perdían cambios pendientes en otras filas.
- Campos numéricos como precio o merma mostraban `0,00`, obligando a borrar antes de escribir.

### Corrección aplicada
- La tabla de artículos deja de depender de formularios de fila inválidos dentro de `<tr>`.
- Cada fila tiene ahora datos propios (`data-item-id`, `data-update-url`) y el guardado se hace por AJAX.
- El sistema detecta cambios por fila en `input` y `select`.
- **Guardar todas las modificaciones** se activa cuando hay una o más filas modificadas.
- Guardar una fila ya no recarga la página ni borra cambios pendientes en otras filas.
- Los campos con valor cero se muestran vacíos cuando corresponde y aceptan escribir directamente.
- En edición, un campo de precio/merma vacío se interpreta como 0 explícito para evitar sugerencias automáticas no deseadas.
- Se añadieron estados visuales: fila modificada, guardando, guardada y error.

### Pruebas internas
- `python3 -m compileall backend/app`: OK.
- Import FastAPI: OK.
- Render Admin/Catálogo HTTP 200: OK.
- Comprobado que la tabla renderiza `data-update-url` y ya no depende de `admin-item-update-form`.
- POST AJAX `/item/{id}/update_form` con campos vacíos de precio/merma: OK.

## Nota
No se ha tocado la lógica de pedidos, inventario, recetas, stock ni OCR en este build.
