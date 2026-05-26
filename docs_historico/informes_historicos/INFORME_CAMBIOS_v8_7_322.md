# INFORME CAMBIOS · v8_7_322_recipe_ai_lab_integrado

## Objetivo
Incorporar el paquete Recipe AI auditado como laboratorio aislado dentro de System MAC, sin convertirlo aún en flujo activo de recetas maestras.

## Integrado
- `backend/app/recipe_ai/` copiado al árbol vivo `backend/app`.
- Router `/recipe-ai` incluido en FastAPI.
- Acceso desde `Laboratorio → Recetas IA LAB`.
- Importación por texto, foto/lectura y voz como borrador IA.
- Borradores guardados en tablas propias `recipe_import_*`.
- Catálogo real leído solo en modo consulta para matching/costes.
- Subrecetas reales leídas solo en modo consulta.
- Precio actual de artículos usado para coste preliminar.

## Blindajes
- La conversión a receta maestra queda bloqueada por defecto con `RECIPE_AI_ALLOW_COMMIT=0`.
- Para activar conversión real hay que poner explícitamente `RECIPE_AI_ALLOW_COMMIT=1`.
- Ingredientes nuevos no se borran: quedan como `PENDIENTE_ALTA`.
- Si hay ingredientes pendientes, el coste queda incompleto y la conversión queda bloqueada.
- Subidas de foto/audio tienen límite de tamaño y extensión.
- La unidad original se conserva y los líquidos se convierten para coste con regla práctica del laboratorio.

## No tocado
- OCR de albaranes.
- Dictado/voz antiguo del sistema.
- Recetas maestras existentes.
- Producciones, pedidos, inventario y stock, salvo lectura de catálogo para laboratorio.

## Estado
Laboratorio integrado y accesible, pero no acoplado como flujo definitivo de receta maestra.
