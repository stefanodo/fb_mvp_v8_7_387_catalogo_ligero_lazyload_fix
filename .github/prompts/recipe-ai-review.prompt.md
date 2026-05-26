---
name: "Revisar Borrador IA"
description: "Guía la revisión y validación de un borrador de receta importado por IA (BORRADOR_IA → VALIDADA_PARA_CONVERTIR). Opcional: convierte a receta maestra si RECIPE_AI_ALLOW_COMMIT=1."
argument-hint: "draft_id — ID del borrador a revisar (ej. 42)"
agent: "agent"
---

Revisa y valida un borrador de receta importado por IA en System MAC.

## Argumento
`$ARGUMENTS` = ID numérico del borrador (`draft_id`). Si no se proporciona, listar los borradores en estado `BORRADOR_IA` o `PENDIENTE_REVISION`.

## Flujo de revisión

### 1. Leer el borrador
Consultar en la DB (`~/Documents/F&B_MAC_RUNTIME/fb_mvp_v8.db`) o via API:
```
GET /recipe-ai/drafts/{draft_id}
```
Mostrar:
- `recipe_name`, `category`, `yield_quantity`, `yield_unit`, `portions`
- Lista de ingredientes con `match_status`, `quantity_net`, `unit`, `waste_percent`
- `warnings` del borrador
- `cost_status`

### 2. Identificar pendientes críticos
Ingredientes con `match_status` en:
- `PENDIENTE_ALTA` — no existe en Catálogo
- `PENDIENTE_REVISION` — dato incompleto o inválido
- `UNIDAD_INCOMPATIBLE` — unidad no convertible
- `SUBRECETA_PENDIENTE` — subreceta sin vincular

Ingredientes con `conversion_status = PENDIENTE_CONVERSION_PESO` requieren confirmación de densidad o cambio a kg/g.

### 3. Resolver pendientes
Para cada ingrediente pendiente, proponer:
- Vincular a artículo existente del Catálogo (por nombre similar)
- Marcar para alta nueva en Catálogo
- Corregir unidad a g/kg si es líquido con densidad conocida

Usar el endpoint:
```
PATCH /recipe-ai/drafts/{draft_id}/ingredients/{ingredient_id}
```

### 4. Calcular coste provisional
```
POST /recipe-ai/drafts/{draft_id}/cost-preview
```
Mostrar total, coste por ración, coste por unidad de rendimiento.
El estado debe quedar en `COSTE_COMPLETO` o `COSTE_ESTIMADO` para poder convertir.

### 5. Validar para conversión
Cuando no hay pendientes críticos y el coste está calculado:
```
POST /recipe-ai/drafts/{draft_id}/validate
```
Esto establece `import_status = VALIDADA_PARA_CONVERTIR`.

### 6. Convertir a receta maestra (opcional)
**Solo si `RECIPE_AI_ALLOW_COMMIT=1` está activo.**
```
POST /recipe-ai/drafts/{draft_id}/commit
```
Confirmar antes de ejecutar — esta acción crea la receta maestra definitiva.

## Reglas de seguridad
- Un borrador NUNCA se convierte automáticamente. Siempre requiere validación humana explícita.
- No modificar recetas maestras existentes durante esta revisión.
- Si hay dudas sobre un ingrediente, dejar en `PENDIENTE_REVISION` antes de asumir un match incorrecto.

## Referencias
- Modelos de estado: [models.py](../../backend/app/recipe_ai/models.py)
- Servicio de coste: [costing_service.py](../../backend/app/recipe_ai/costing_service.py)
- Conversión de unidades: [unit_conversion_service.py](../../backend/app/recipe_ai/unit_conversion_service.py)
- Conversión a receta maestra: [commit_service.py](../../backend/app/recipe_ai/commit_service.py)
