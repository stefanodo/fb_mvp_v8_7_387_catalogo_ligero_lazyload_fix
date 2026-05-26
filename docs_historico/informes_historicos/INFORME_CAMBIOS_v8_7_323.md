# INFORME CAMBIOS · v8_7_323_ui_recetas_inventario_fix

## Objetivo
Corregir los problemas visuales reportados en Recetas e Inventario sin tocar OCR ni dictado antiguo. Mantener Recetas IA LAB integrado, pero sin conversión automática a recetas maestras.

## Cambios aplicados

### Recetas · cabecera
- Compactado el bloque superior de búsqueda de receta.
- Campo `Receta`, botón `Abrir ficha` y botón `Crear receta` quedan alineados en una misma línea cuando hay ancho suficiente.
- En móvil se apilan sin solaparse.

### Recetas · foto
- `Subir foto` y `Quitar foto` salen debajo del recuadro de foto, alineados en dos columnas.
- Se eliminan superposiciones sobre el recuadro de imagen.

### Recetas · ingredientes
- Reordenada la columna de edición de ingredientes: cantidad, unidad, merma, guardar y quitar.
- Añadidas reglas responsive para portátil y móvil.
- Limpieza de decimales visibles en cantidades y merma.

### Recetas · costes indirectos y salarios
- El bloque grande pasa a un desplegable dentro de Recetas.
- La vista principal muestra solo resumen mínimo: estructura % y carga/ración.
- Al abrir el desplegable se mantienen todos los campos editables con IVA/sin IVA, salarios y porcentajes.

### IA / Asistente
- Eliminado el botón flotante `Asistente` de las pantallas operativas.
- Añadido acceso ordenado `IA Recetas` en navegación hacia el laboratorio IA.
- Recetas IA LAB sigue aislado y no toca recetas maestras salvo activación explícita futura.

### Inventario
- El selector `Paso 1 · Elige bloque` muestra ahora estado visible: bloque seleccionado y avance.
- El botón activo queda iluminado y marcado como seleccionado.
- En Producciones se añade contexto: total de producciones disponibles, familia visible y líneas visibles.
- Si solo aparece una producción, el sistema lo explica y orienta a cambiar familia o usar buscador.

## Validaciones
- `python3 -m compileall -q backend/app`: OK.
- Carga de templates modificados con Jinja: OK.
- Importación de `app.main`: OK.
- Render HTTP 200 en Recetas, Inventario y Laboratorio con TestClient: OK.
- Confirmado que `macVoiceAssistant` ya no aparece en páginas renderizadas.

## No tocado
- OCR de albaranes.
- Dictado/voz antiguo.
- Motor de stock.
- Confirmación de producciones.
- Pedidos.
- Base de datos productiva.
