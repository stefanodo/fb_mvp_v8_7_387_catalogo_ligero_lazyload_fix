# System MAC · Informe de cambios v8_7_359

## Objetivo
Cerrar el bloque de ajustes pedidos por Mauro antes de empaquetar: Pedidos sin superposición, Catálogo con edición masiva, Mermas más legible y compacta, e Inventario con Nueva sesión mejor alineada.

## Cambios aplicados

### Pedidos
- Reorganizada la cabecera de pedido para evitar superposiciones.
- Formulario de creación en una línea en escritorio: Local · Responsable · Nota · Nuevo pedido.
- Historial de pedidos separado debajo en una fila propia, sin invadir Nota ni el botón Nuevo pedido.
- En móvil/tablet se apila de forma controlada.
- Reforzado CSS final `v8_7_359` para prevalecer sobre reglas históricas anteriores.

### Catálogo > Artículos
- Añadida explicación funcional del campo Tipo:
  - Insumo = materia prima comprable/inventariable.
  - Preparación = elaboración interna/subreceta con stock propio.
- Añadido botón `Guardar todas las modificaciones`.
- La tabla detecta filas modificadas y permite guardar varias filas en lote desde la pantalla.
- Se mantiene el botón individual `Guardar` por fila.
- El guardado masivo usa el endpoint AJAX ya existente de actualización de artículos.
- Añadidos estados visuales: modificado, guardando, guardado y error.

### Mermas
- Aumentado contraste de títulos, ayudas y etiquetas.
- Motivos convertidos a chips compactos oscuros estilo System MAC.
- Estado seleccionado más claro.
- Refuerzo visual del autocompletado de artículo/elaboración.

### Inventario
- Botón `Nueva sesión desde cero` mejor alineado en la cabecera de sesión.
- Mantiene separación conceptual frente a `Guardar sesión` y `Cerrar y conciliar stock`.
- Microcopy visible: crea otra sesión independiente y no guarda el conteo actual.
- Responsive reforzado.

## Pruebas internas
- `python3 -m compileall backend/app`: OK.
- Render HTTP 200:
  - Inicio
  - Pedidos
  - Catálogo/Admin
  - Mermas
  - Inventario
- Prueba AJAX `/item/{id}/update_form`: OK.
- Restaurado dato de prueba tras test de artículo.

## Notas
- No se ha implementado pago bancario real. Solo queda la arquitectura previa de versiones anteriores.
- El acceso móvil beta sigue dependiendo de HTTP local/IP; la versión final debe ir por dominio/HTTPS/PWA/login.
