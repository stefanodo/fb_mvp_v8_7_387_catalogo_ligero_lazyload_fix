# Informe cambios v8_7_352

## Objetivo
Reparar superposición real en Pedidos: Local, Responsable, Nota, Nuevo pedido e Historial quedaban montados visualmente.

## Cambios
- `orders.css`: nuevo bloque final de blindaje para cabecera de Pedidos en fila real.
- El formulario queda en una línea en escritorio: Local · Responsable · Nota · Nuevo pedido.
- Historial queda como tarjeta lateral limpia sin invadir Nota ni el botón Nuevo pedido.
- En tablet/móvil se apila de forma controlada.
- `index.html`: añadido cache-busting `?v={{build_id}}` a CSS/JS para evitar que Safari cargue hojas antiguas con 304.

## Pruebas
- Compilación backend OK.
- Comprobación de plantilla `index.html` con versionado de assets OK.
- Comprobación CSS: reglas finales v8_7_352 presentes.
