# System MAC · v8_7_361 · Pedidos rediseño real sin solapes

## Cambios aplicados
- Rediseño real del módulo Pedidos en templates y CSS, no maqueta ni imagen.
- Formulario principal reorganizado en una fila limpia: Local, Responsable, Nota y + Nuevo pedido.
- Historial de pedidos convertido en tabla/card separada con columnas claras: ID, Local, Responsable, Nota, Fecha, Estado y Acciones.
- Detalle queda debajo como bloque independiente y sin superposición.
- Se evita reutilizar clases antiguas conflictivas para no arrastrar parches anteriores.
- Responsive: en móvil el formulario se apila de forma ordenada y el historial pasa a tarjetas.

## Archivos modificados
- backend/app/templates/sections/pedidos.html
- backend/app/templates/partials/orders_sidebar.html
- backend/app/templates/partials/orders_detail.html
- backend/app/static/css/orders.css
- backend/app/core.py

## Pruebas internas
- Compilación Python backend OK.
- Import FastAPI OK.
- Revisión de sintaxis Jinja básica OK.
