# INFORME CAMBIOS v8_7_358

## Cambio aplicado
- Inicio / Dashboard de dirección · inventario: se elimina el selector confuso Mensual/Diario.
- Se sustituye por filtro claro de rango de fechas:
  - Desde
  - Hasta
  - Ver
  - Imprimir
- Se corrigen solapes visuales entre Día/Mes/Año en escritorio y móvil.
- Campos de fecha uniformes, mismo tamaño y alineados.
- El informe sigue midiendo solo diferencias de inventarios cerrados/conciliados dentro del rango seleccionado.
- El botón Imprimir pasa el rango de fechas al informe imprimible.

## Blindajes
- No se toca stock, recetas, pedidos, mermas ni inventario operativo.
- No se generan movimientos nuevos.
- Cambio limitado a dashboard de Inicio, servicio de lectura e impresión del informe.
- Se mantiene lectura pura: solo inventarios cerrados y líneas contadas.

## Pruebas internas
- `python3 -m compileall -q backend/app`: OK.
- Import FastAPI: OK.
- Inicio HTTP 200: OK.
- Inicio con `direction_start` / `direction_end`: HTTP 200 OK.
- Mermas HTTP 200: OK.
- Pedidos HTTP 200: OK.
- Comprobado que ya no aparece Mensual/Diario en el dashboard.
