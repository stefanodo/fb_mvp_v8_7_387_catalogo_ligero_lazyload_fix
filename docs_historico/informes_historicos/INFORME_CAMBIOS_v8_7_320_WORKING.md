# INFORME CAMBIOS · v8_7_320_tpv_modificadores_stock_realista_working_no_zip

## Objetivo
Preparar una capa TPV para que el consumo de stock sea más realista cuando una venta tenga modificadores: sin pan, extra queso, guarnición alternativa, sin aderezo, solo aceite, sin tomate, extra aguacate, etc.

## Regla principal
La receta maestra no se modifica. La venta TPV representa el plato realmente vendido y los modificadores aplican deltas de consumo sobre la receta base.

## Tablas añadidas
- `recipe_modifiers`: reglas internas por receta.
- `pos_modifier_map`: traducción de nombres TPV a modificadores internos.
- `pos_sales_modifier_daily`: ventas agregadas de modificadores por día/receta.
- `pos_modifier_consumption_audit`: preparada para auditar consumos calculados por modificador.

## Servicio añadido
- `backend/app/services/pos_modifiers_service.py`

Funciones principales:
- `normalize_modifier_name()`
- `ensure_pos_modifier_tables()`
- `resolve_modifier()`
- `build_modifier_delta()`
- `build_monthly_modifier_dashboard()`

## Lógica aplicada
- `SIN`: resta ingrediente/subreceta.
- `EXTRA`: suma ingrediente/subreceta.
- `SUSTITUIR` / `GUARNICIÓN`: puede representar salida y entrada por reglas separadas.
- `NO_STOCK`: observaciones que no descuentan stock, como punto de cocción o cortar en dos.
- `REQUIERE_MAPEO`: el sistema no inventa consumo si no entiende el modificador.

## Dashboard
En Inicio, dentro de ventas de platos, se agregó bloque:
- Modificadores TPV · stock realista
- modificadores vendidos
- mapeados
- sin mapear
- sin impacto stock
- recomendaciones

## Informe imprimible
Nueva ruta:
- `/direction/recipe-modifiers/print`

## Validaciones realizadas
- Compilación `backend/app`: OK.
- Migración de tablas TPV/modificadores en runtime temporal: OK.
- `normalize_modifier_name('Sin pan') -> SIN_PAN`: OK.
- Simulación Burger MAC:
  - Sin pan x3 => delta -3 ud pan: OK.
  - Extra queso x2 => delta +40 g queso: OK.
  - Especial cocina sin mapear => REQUIERE_MAPEO: OK.
- Render Inicio: HTTP 200 OK.
- Render informe modificadores: HTTP 200 OK.

## No tocado
- OCR.
- Dictado/voz antigua.
- Recetas IA laboratorio.
- Confirmación real de ventas TPV contra stock.
- Envío automático de pedidos.

## Pendiente recomendado
- Pantalla de administración para crear/modificar modificadores por receta.
- Mapeo TPV ↔ receta y TPV ↔ modificadores.
- Previsualización de consumo por venta antes de generar movimientos `salida_venta_tpv`.
- Reglas compuestas de sustitución: patatas → ensalada, aderezo → aceite.
