# INFORME CAMBIOS · v8_7_340

Build acumulado sobre v8_7_339.

## OÍDO ALFI / Operativa real
- Refuerzo de intención PEDIDO: reconoce “pide”, “compra”, “encarga”, “solicita” además de pedir/encargar/solicitar.
- Mantiene creación de borradores reales para PRODUCCIÓN, MERMA y PEDIDO.
- Producción “pico de gallo” queda como borrador pendiente aunque falte cantidad.
- Mermas quedan pendientes y no descuentan stock hasta confirmación humana.

## Stock
- Entrada manual devuelve datos verificables: movement_id, item_id, warehouse_id, qty_base, base_unit y stock_after.
- Redirección tras guardar stock conserva artículo/almacén para que se vea el stock recién actualizado.
- Simulado caso PUERRO: entrada manual 10 kg guarda item_id correcto y stock_after=10 kg.

## Inventario
- Confirmado flujo de auditoría multiusuario: conserva primer contador, último modificador, valor anterior/nuevo y registro en inventory_count_audit.
- Se mantiene foco/scroll sobre área de inventario y línea libre.

## Mermas
- UI de entrada rápida aún más compacta, oscura y alineada con System MAC.
- Fecha y hora se mantienen en chips separados.
- Confirmar merma la saca del estado pendiente; anular funciona sin exigir artículo/cantidad.

## Pedidos
- Cabecera reordenada por CSS para evitar solape entre Nuevo pedido, Historial y Ver archivados.
- Responsable y Nota mantienen anchura útil en escritorio y apilado limpio en móvil.

## Inicio / dashboard mensual
- Filtros Mes/Año reforzados con mayor contraste, anchura y alineación real en HTML/CSS.

## Producciones
- Producción guiada por partidas: Fríos incluye también salsas/guarniciones/bases sin marca caliente/postre, para evitar listas vacías por clasificación operativa.

## Recetas IA
- En UI móvil/listados se elimina el acceso directo a JSON crudo; se prioriza ficha legible de borrador.
- Se mantienen chips de revisión y hora.

## Pruebas internas realizadas
- compileall backend/app: OK.
- Import app FastAPI: OK.
- Render de páginas inicio/pedidos/mermas/inventario/producciones: HTTP 200.
- Simulacro OÍDO ALFI: producción pico de gallo, merma tomates, merma tomate pera, pedido tomate rama y pedido puerro: OK.
- Simulacro Stock PUERRO: entrada 10 kg con item_id real y stock_after correcto: OK.
- Simulacro Inventario auditoría: primer conteo + modificación con previous/new qty: OK.
- Simulacro Mermas: confirmar quita de pendientes; cancelada queda CANCELLED: OK.

## Límites
- No se ha probado audio real de iPhone en este entorno; queda cubierto por fallback texto/dictado + endpoint de transcripción cuando OpenAI esté configurado.
- No se ha confirmado visualmente en navegador real; sí se han renderizado las páginas sin error.
