# System MAC · Informe de cambios v8_7_335

## Objetivo
Cerrar el bloque solicitado de Recetas IA/Borradores IA y trazabilidad temporal de recetas, sin tocar OCR ni dictado antiguo.

## Cambios aplicados

### Recetas IA / Borradores IA
- La importación por foto/texto/voz desde la interfaz ya no devuelve JSON crudo al usuario.
- Después de importar, se muestra una ficha HTML del sistema con:
  - nombre del borrador,
  - estado,
  - coste,
  - ingredientes detectados,
  - avisos,
  - fecha y hora de revisión,
  - acciones de volver/reintentar/ver borradores/ver JSON técnico.
- Si la IA está offline o no detecta ingredientes:
  - no se inventan ingredientes,
  - se muestra “Imagen pendiente de revisión / No se detectaron ingredientes”,
  - el borrador queda en revisión,
  - el JSON queda solo como vista técnica manual.
- Añadido control anti-duplicado para borradores vacíos recientes:
  - mismo origen,
  - mismo nombre provisional,
  - sin ingredientes,
  - en revisión reciente.

### Fecha/hora en revisión IA
- Añadida columna `review_at` a `recipe_import_drafts` mediante migración segura.
- Los borradores `PENDIENTE_REVISION` muestran chips separados:
  - `Revisión: dd/mm/aaaa`,
  - `Hora: hh:mm`.
- Visible en listado de Borradores IA y en la ficha de resultado.

### Recetas maestras
- Añadidos campos `created_at` y `updated_at` a `recipes` mediante migración segura.
- Las recetas existentes reciben fecha fallback si no tenían datos.
- La ficha de receta muestra chips:
  - `Creada: dd/mm/aaaa`,
  - `Hora: hh:mm`,
  - `Modificada: dd/mm/aaaa`,
  - `Hora: hh:mm`.
- `updated_at` se actualiza al modificar:
  - datos principales,
  - foto,
  - ingredientes,
  - cantidades,
  - merma,
  - pricing/costes.

## Blindajes mantenidos
- La IA no modifica recetas maestras automáticamente.
- Los ingredientes nuevos se conservan en borrador como pendientes, no se eliminan.
- OCR no tocado.
- Dictado/voz antiguo no tocado.
- JSON técnico queda disponible solo si se abre manualmente.

## Validación realizada
- Compilación Python de módulos principales: OK.
- Importación de app FastAPI: OK.
- Render Inicio/Recetas/Recetas IA/Borradores IA: OK.
- POST interfaz Recetas IA por texto: OK.
- POST interfaz Recetas IA por foto: OK, sin JSON crudo.
- Creación de receta con timestamps: OK.
