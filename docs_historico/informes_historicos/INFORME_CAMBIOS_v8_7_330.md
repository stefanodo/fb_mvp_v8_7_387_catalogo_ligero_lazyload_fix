# INFORME CAMBIOS · v8_7_330 · TPV modificadores como aprendizaje supervisado

## Objetivo
Corregir el enfoque de Modificadores TPV: el usuario no debe precargar todas las variantes posibles. El camarero podrá escribir peticiones libres en el TPV; System MAC interpretará lo claro y dejará en revisión lo ambiguo.

## Cambios aplicados

### 1. Motor prudente de notas libres TPV
Añadido en `backend/app/services/pos_modifiers_service.py`:

- `split_customer_modifier_note()`
- `interpret_free_pos_modifier_note()`
- `register_modifier_review_from_note()`

La lógica permite interpretar frases como:

- `sin pan`
- `extra queso`
- `ensalada en vez de patatas`
- `solo aceite`
- `poco hecho`
- `como siempre`

Estados posibles:

- `CONSUMO_EXACTO`
- `CONSUMO_ESTIMADO_CON_ALERTA`
- `REQUIERE_MAPEO`
- `IGNORADO_NO_STOCK`
- `SIN_MODIFICADORES`

### 2. Nueva cola de aprendizaje supervisado
Tabla nueva:

- `pos_modifier_review_queue`

Sirve para guardar notas libres que requieren revisión/corrección. No mueve stock ni modifica recetas maestras.

### 3. Endpoint de previsualización
Nuevo endpoint de solo lectura:

- `/api/tpv/modifiers/interpret?recipe_id=...&note=...&qty=...`

Permite probar cómo System MAC interpretaría una nota libre antes de conectar un TPV real.

### 4. Admin → Modificadores TPV
La pantalla se redefine como:

- aprendizaje supervisado,
- revisión de excepciones,
- reglas aprendidas,
- no carga manual exhaustiva.

Añadido bloque “Probar nota libre / crear pendiente”.

### 5. Blindajes mantenidos

- No se modifica receta maestra.
- No se mueve stock desde el analizador TPV.
- No se inventan consumos ambiguos.
- Lo claro puede convertirse en delta.
- Lo ambiguo queda en revisión.
- Si no está claro, se descuenta base y se alerta según configuración futura.

## Validaciones realizadas

- Compilación backend/app: OK
- Importación app principal: OK
- `interpret_free_pos_modifier_note('sin pan, extra queso, como siempre')`: OK
- Endpoint `/api/tpv/modifiers/interpret`: OK
- Render Admin con aprendizaje TPV: OK

## No tocado

- OCR de albaranes.
- Dictado/voz antiguo.
- Conversión automática a receta maestra.
- Confirmación automática de ventas o stock.
