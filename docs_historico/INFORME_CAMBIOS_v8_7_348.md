# INFORME CAMBIOS · v8_7_348

## Pedidos · reparación real de superposición

Se corrige la pantalla de Pedidos en el sistema, no como maqueta:

- Reestructurado `orders_sidebar.html` para separar formulario de creación e historial.
- Formulario de pedido organizado en bloque limpio: Local, Responsable, Nota y acción Nuevo pedido.
- Historial de pedidos movido a una tarjeta lateral independiente.
- Pedido # / estado / Abrir / Borrar ya no se montan sobre Nota ni sobre el formulario.
- Añadidas reglas responsive para escritorio, tablet y móvil.
- Conservado el bloque Detalle debajo, sin quedar tapado por OÍDO ALFI ni por historial.

## Archivos modificados

- `backend/app/templates/partials/orders_sidebar.html`
- `backend/app/static/css/orders.css`

## Pruebas internas

- Compilación backend: OK.
- Import FastAPI: OK.
- Render `/ ?page=pedidos&center_id=1`: HTTP 200.
- Comprobación HTML: clases nuevas presentes.
