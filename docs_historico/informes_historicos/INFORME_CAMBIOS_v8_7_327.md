# INFORME CAMBIOS · v8_7_327 · OÍDO ALFI proveedores/autónomo

## Objetivo
Ampliar OÍDO ALFI como asistente operativo movible para consultar proveedores e insumos, preparar acciones y responder por voz/texto sin ejecutar cambios críticos sin revisión humana.

## Cambios aplicados

### 1. Consultas de proveedores desde OÍDO ALFI
Añadido endpoint seguro de solo lectura:

- `GET /api/oido-alfi/query?q=...&center_id=...`

Permite preguntar por:

- teléfono de proveedor,
- email/correo,
- días de reparto,
- mínimos de pedido,
- mínimo con IVA/sin IVA,
- plazo de entrega,
- notas/condiciones,
- próximo reparto operativo aproximado.

Ejemplos:

- “teléfono de Negrini”
- “email de La Huerta”
- “días de reparto de Pescadería Palacio”
- “mínimo de proveedor X”

### 2. Preguntar proveedor de un insumo
OÍDO ALFI ahora puede responder:

- “¿de qué proveedor es salmón?”
- “¿quién vende aguacate?”
- “proveedor de tomate pera”

La respuesta se basa en `supplier_item_prices` y prioriza proveedor preferente/último precio. También muestra precio, unidad, reparto y mínimo si están cargados.

### 3. Proveedor alternativo más barato
Si hay varios proveedores comparables para el mismo artículo, OÍDO ALFI puede indicar alternativa más barata como sugerencia de revisión.

Blindaje: no cambia proveedor habitual automáticamente. Solo informa y advierte revisar calidad, formato, mínimo, reparto y plazo.

### 4. Panel OÍDO ALFI
Añadida pestaña “Proveedores” dentro del panel movible con accesos rápidos:

- Teléfono proveedor
- Email proveedor
- Días reparto
- Mínimo pedido
- Proveedor de insumo
- Proveedor alternativo

Añadida caja de respuesta detallada dentro del panel.

### 5. Seguridad
OÍDO ALFI sigue siendo autómata de bajo riesgo:

- consulta,
- abre pantallas,
- prepara propuestas,
- informa alertas.

No confirma:

- pedidos,
- envíos,
- producciones,
- mermas,
- inventarios,
- recetas maestras,
- cambios de proveedor habitual.

## Validaciones

- Compilación backend/app: OK
- Importación app principal: OK
- Endpoint `/api/oido-alfi/query`: OK
- Consulta proveedor por insumo: OK
- Consulta teléfono/mínimo/reparto proveedor: OK
- JS OÍDO ALFI: sintaxis OK
- OCR: no tocado
- Dictado antiguo: no tocado
- Recetas IA LAB: no acoplada a recetas maestras
