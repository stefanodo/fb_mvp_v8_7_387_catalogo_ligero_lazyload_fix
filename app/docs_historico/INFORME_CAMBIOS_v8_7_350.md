# v8_7_350 · Recetas estabilidad real

Cambios:
- Recetas: guardado de ficha/foto por AJAX para evitar recarga completa, pantallazos negros y mezcla visual de pantallas anteriores.
- Limpieza de estado transitorio: menú móvil, sugerencias abiertas y `flow_preserve` al guardar receta.
- Blindaje móvil: foto de receta con altura controlada, botones debajo y separación clara antes del campo Nombre.
- Mano de obra pasa más abajo en móvil para no invadir la ficha principal.
- Se desregistran Service Workers/cachés antiguos en beta local para evitar páginas viejas o mezcladas en Safari.

Pruebas internas:
- Compilación backend OK.
- Render Recetas OK.
- JS Recetas sin error de sintaxis.
