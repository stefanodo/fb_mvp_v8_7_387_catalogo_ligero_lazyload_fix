# INFORME CAMBIOS v8_7_378

## Coctelería / Barra · selector y creación de fichas

- El buscador de cócteles ya no abre la ficha automáticamente aunque el texto coincida exactamente.
- El selector tampoco abre la ficha automáticamente.
- Ahora la ficha se abre solo al pulsar `Ver ficha`.
- Al pulsar `Crear cóctel`, se limpia búsqueda, selector, sugerencias y ficha anterior.
- La ficha nueva queda limpia: no arrastra nombre, cantidades, mermas, ingredientes ni valores del cóctel anterior.
- Las sugerencias de búsqueda solo seleccionan el cóctel; no abren ficha hasta pulsar `Ver ficha`.
- Se mantiene el modo LAB/no productivo y no se toca Cocina.

## Chequeo

- Python compileall OK.
- JS `laboratory.js` comprobado por Node OK.
- App importa OK.
- `/ ?page=laboratorio` responde OK.
- `/api/lab/bar/summary` responde OK.
