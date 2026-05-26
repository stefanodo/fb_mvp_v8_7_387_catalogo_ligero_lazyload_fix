# INFORME CAMBIOS v8_7_376

## Coctelería / Barra · limpieza visual ficha cóctel

- Se elimina la doble visualización de foto en la ficha de cóctel: queda una única zona de foto dentro de Datos generales.
- Se añaden botones visibles `Subir foto` y `Quitar foto` junto al campo de ruta/foto.
- Se retira el texto auxiliar largo situado encima del listado de cócteles/escandallo para liberar espacio operativo.
- En escandallo, el ingrediente vinculado ya no muestra la etiqueta visible `bloqueado`; el bloqueo queda implícito para proteger vínculo con Stock Bar / Producción Bar.
- Se conserva la edición de cantidad, unidad, merma y coste.
- Se mantiene Barra en unidades propias ml/gr/ud, sin alterar Cocina.

## Pruebas

- Compilación Python: OK.
- Import app FastAPI: OK.
- Ruta Laboratorio: OK.
- API Coctelería resumen: OK.
