# System MAC · Informe cambios v8_7_334

## Objetivo
Agrupar correcciones operativas y visuales detectadas durante la revisión manual: Inventario, Stock, Mermas, Recetas, Pedidos, Inicio, TPV y Producciones.

## Cambios aplicados

### Inventario
- La pestaña superior Inventario queda resaltada correctamente.
- El cambio de bloque/rubro se separa de la familia: Materias primas, Producciones, Limpieza y Líneas libres ya no dependen de cambiar familia para refrescar.
- Materias primas ahora toma una línea operativa por artículo desde catálogo/stock, evitando que solo aparezca un artículo aislado.
- Limpieza muestra artículos de limpieza existentes.
- Se reducen duplicados aparentes agrupando por artículo/almacén/unidad.
- El campo “Ayuda en vivo sobre las líneas visibles” ahora filtra y ofrece sugerencias clicables.
- En Líneas libres, el campo Nombre tiene autocompletado contra Catálogo.
- Al pulsar Líneas libres, el sistema enfoca directamente la casilla Nombre.

### Stock
- Los botones Frescos/Producciones/Congelados/Secos/Limpieza cambian mediante navegación suave por JS para evitar flash y salto brusco.
- El flujo de entrada manual conserva sección de stock y ancla.
- La resolución de artículos manuales es más tolerante: acepta primeras letras, acentos y texto con [#id]. Evita movimientos huérfanos cuando el artículo ya existe, como PUERRO.

### Mermas
- Anular merma se ejecuta de forma más suave, sin recarga visual completa cuando el navegador lo permite.
- El estado CANCELLED queda respetado aunque la merma no tenga artículo/cantidad/responsable.
- Fecha y hora se separan visualmente en registros.
- Mejorado contraste en Control de Mermas: títulos, KPIs, tarjetas y “Últimos registros incluidos”.
- Botones superiores y tarjetas de entrada se compactan.

### Recetas
- Foto de receta: botones Subir foto/Quitar foto quedan debajo del marco y más alineados hacia la izquierda, según referencia enviada.
- Ingredientes: cantidad, unidad, merma, guardar y quitar quedan mejor alineados en escritorio.
- En móvil, tarjetas de ingredientes más compactas y nombres largos con mejor corte.

### Pedidos
- Reordenada cabecera para evitar solape entre Nuevo pedido, Historial y Ver archivados.
- Responsable y Nota ganan anchura útil.

### Inicio
- Filtros Mes/Año del dashboard mensual tienen más contraste, ancho y separación.
- Ver/Imprimir quedan en una fila más clara y responsive.

### TPV / Modificadores
- El simulador queda entendido como prueba/aprendizaje, no carga manual diaria.
- Se mantiene el modelo de aprendizaje supervisado: automático cuando es claro, revisión cuando es ambiguo.

### Producciones
- Producción guiada por partidas deja de tratar Fríos/Salsas/Guarniciones/Bases como una sola dimensión.
- Fríos puede mostrar recetas/subrecetas frías aunque sean salsas, guarniciones o bases.
- Salsas/Guarniciones/Bases siguen funcionando como filtros operativos.

## Validación realizada
- Compilación Python: OK.
- Arranque FastAPI local de prueba: OK.
- Render Inicio: OK.
- Render Inventario por bloques: OK.
- Render Stock: OK.
- Render Mermas y Control: OK.
- Render Pedidos: OK.
- Render Recetas: OK.
- Render Producciones: OK.
- Render Admin/TPV: OK.
- Simulación de resolución manual de PUERRO: OK.

## No tocado
- OCR de albaranes.
- Recetas maestras ya validadas.
- Dictado/voz antigua como motor de reconocimiento.
