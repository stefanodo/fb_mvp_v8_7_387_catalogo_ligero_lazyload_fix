# Informe cambios v8_7_371 · Coctelería ficha compacta

## Cambios aplicados
- Compactada la pantalla de ficha técnica de cócteles.
- Datos generales y foto reorganizados en una composición tipo ficha de receta: foto amplia a la izquierda y campos principales en líneas compactas.
- Escandallo editable con cabecera visible: Origen, Ingrediente, Cantidad, Unidad, Merma %, Coste €/u, Bruto/Coste, Guardar y Quitar.
- Botones Guardar y Quitar alineados en la misma línea de cada ingrediente.
- Reducción de ceros/decimales visibles en cantidades, mermas y costes unitarios.
- Mantiene unidades propias de Barra: ml/gr/ud.
- No cambia lógica productiva ni mezcla datos con Cocina.

## Simulacro
- Compilación Python OK.
- Pantalla Laboratorio mantiene carga JS/CSS.
- Ficha de cóctel continúa editable mediante las APIs ya existentes.

## Pendiente
- Añadir subida real de foto por archivo si se decide replicar exactamente el flujo de Recetas Cocina.
- Convertir Coctelería de LAB a módulo productivo cuando se estabilicen Stock/Pedidos/Inventario/Mermas Bar.
