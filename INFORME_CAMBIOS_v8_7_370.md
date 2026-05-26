# INFORME CAMBIOS v8_7_370

## Objetivo
Corregir la pantalla de Coctelería/Barra para que funcione como ficha técnica editable de cócteles, similar al flujo de recetas de Cocina, manteniendo Barra como bloque separado y LAB/no productivo.

## Cambios aplicados
- Buscador de cócteles con escritura y ayuda/autocompletado.
- Selector de cócteles conservado como alternativa rápida.
- Botón "Crear cóctel".
- Ficha técnica editable de cóctel:
  - nombre, código, categoría, tipo, copa/vaso,
  - ml de servicio,
  - rendimiento,
  - PVP,
  - margen objetivo,
  - contingencia,
  - dificultad,
  - temporada,
  - foto/ruta pendiente,
  - notas y estado.
- Escandallo editable:
  - origen Stock Bar / Producción Bar,
  - ingrediente/preparado con ayuda de búsqueda,
  - cantidad neta,
  - unidad ml/gr/ud,
  - merma %,
  - coste unitario,
  - cantidad bruta calculada,
  - coste total bruto.
- Alta de nuevas líneas de escandallo.
- Edición de líneas existentes.
- Eliminación de líneas.
- Procedimiento paso a paso editable.
- Recalculo automático al guardar:
  - coste neto,
  - coste bruto con merma,
  - precio sugerido,
  - margen,
  - coste por ml,
  - % de alcohol calculado por medidas.

## Reglas mantenidas
- Cocina mantiene su lógica kg/gr.
- Barra mantiene ml/gr propios.
- No se toca Stock Cocina.
- No se conecta TPV real.
- No se descuenta stock productivo.
- Todo el nuevo editor queda en modo LAB / demo no productivo.

## Simulacro realizado
- Búsqueda de Mojito por texto: OK.
- Creación de cóctel demo temporal: OK.
- Alta de línea Vodka 50 ml con merma 1%: OK.
- Cálculo de alcohol automático: 16,67% sobre servicio de 120 ml: OK.
- Guardado de procedimiento: OK.
- Página Laboratorio responde 200 OK.
