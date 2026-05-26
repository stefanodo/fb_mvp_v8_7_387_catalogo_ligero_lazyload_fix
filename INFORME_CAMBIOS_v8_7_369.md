# INFORME CAMBIOS v8_7_369

## Cambios aplicados

1. Coctelería / Barra: ficha visual de cócteles
- Añadido selector para elegir primero el cóctel.
- La ficha despliega datos completos: foto/foto pendiente, categoría, tipo, vaso, tamaño de servicio, coste bruto, PVP, margen y escandallo.
- Añadido bloque de procedimiento paso a paso.
- Añadido cálculo automático de % de alcohol por medidas de la bebida completa.

2. Cálculo de alcohol en cócteles
- Regla LAB: % alcohol = ml de alcohol puro / ml totales servidos x 100.
- ABV demo/orientativo por familia: ron/ginebra/vodka 40%, tequila 38%, vermut 15%, Campari 25%, vino 12,5%, cerveza 5%, etc.
- No afecta Cocina ni Stock real.
- Pendiente futuro: ficha real de cada botella con ABV desde catálogo/albarán/ficha técnica.

3. TPV LAB: ración vs lote completo
- Añadido modo de consumo:
  - Ración / porción vendida.
  - Lote completo de receta.
- Añadido campo de raciones del lote si la receta no está configurada.
- El consumo PREVIEW escala por ración y ya no fuerza consumir toda la tortilla si el usuario simula una ración.

4. TPV LAB: cantidades más legibles
- Reducidos ceros y decimales visuales en el resultado.
- Se muestra cantidad limpia: por ejemplo 12 ud, 1500 g, 500 g.
- Se mantiene diagnóstico técnico con conversión de coste.

## Simulacro realizado

- Coctelería demo cargada correctamente.
- Ficha de cóctel devuelve alcohol calculado.
- TPV LAB con TORTILLA DE PATATA en modo ración y lote de 10 raciones:
  - HUEVOS: 12 ud.
  - PATATA: 1500 g.
  - CEBOLLA: 500 g.
- TPV LAB en modo lote completo sigue mostrando el lote completo.

## Seguridad

- Todo queda en modo LAB / PREVIEW / demo.
- No descuenta Stock Cocina definitivo.
- No descuenta Stock Bar productivo.
- No conecta TPV real.
- No modifica recetas maestras de Cocina salvo uso de simulador.
