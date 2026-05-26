# INFORME CAMBIOS v8_7_375

## Coctelería / Barra · Escandallo editable compacto

- Se reordenó el escandallo de cócteles para que el ingrediente quede en la primera columna.
- La columna `Origen` se compactó a `Stock` / `Prod. Bar`.
- Se mantiene una sola cabecera superior: Ingrediente, Orig., Cant., Unidad, Merma %, Coste €/u, Bruto/coste y Acciones.
- Guardar y Quitar quedan en la misma línea en escritorio.
- Se redujo altura, padding y tamaño de inputs/botones para evitar saltos de línea.
- Los ingredientes ya creados quedan visualmente bloqueados. Para cambiar ingrediente se debe quitar la línea y añadir el ingrediente/preparado correcto, evitando vínculos de coste cruzados.
- En líneas nuevas, el campo de ingrediente queda resaltado con buscador/autocompletado.
- Se mantiene Barra en unidades ml/gr/ud y Cocina en su lógica kg/gr.

## Pruebas

- Python compileall OK.
- JS laboratory.js validado con node --check OK.
