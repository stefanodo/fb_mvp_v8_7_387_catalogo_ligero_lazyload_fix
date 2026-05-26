# Informe de simulacro integral — System MAC F&B

**Build auditado:** `v8_7_291_stock_producciones_pedidos_hierbas_fix_macfix`  
**Build reforzado generado:** `v8_7_292_audit_yield_fix_no_ocr_no_voice`  
**Fecha:** 2026-05-19  
**Alcance:** catálogo/artículos, stock, min/max, receta, merma, producción, movimientos y pedidos.  
**Fuera de alcance por instrucción:** OCR de albaranes y dictado por voz.

---

## 1. Resumen ejecutivo

El sistema supera el flujo base desde alta de artículos hasta pedido sugerido, pero el simulacro detectó un fallo crítico en el rendimiento de receta cuando se introducía en kg. Ese fallo fue corregido en el build reforzado.

Resultado general:

| Área | Estado tras simulacro | Observación |
|---|---:|---|
| Alta de artículos por rubro | Correcto | Se pudieron crear frescos, secos, congelados, limpieza, lácteos y preparación. |
| Min/max por local y almacén | Correcto | Guarda por posición centro/almacén/artículo. |
| Carga inicial de stock | Correcto | Inserta movimientos de entrada. |
| Receta con merma por ingrediente | Correcto | Aplica bruto = neto / (1 - merma). |
| Coste de receta | Correcto | Calcula coste base, contingencia, IVA y precio sugerido. |
| Producción desde receta | Parcialmente correcto | Consume bruto y genera entrada de elaborado, pero descuenta todo desde el almacén de la producción. |
| Pedido post-producción/min-max | Parcialmente correcto | Genera líneas para artículos bajo mínimo; no siempre cubre necesidades si el consumo queda en almacén distinto al de stock real. |
| Control almacén-centro | Correcto | Rechaza movimientos con almacén de otro centro. |
| Control unidad incompatible | Débil | Acepta `l` contra artículos `kg` por la política de líquidos como peso; falta distinguir sólidos/líquidos. |

---

## 2. Prueba ejecutada

Se creó un escenario completo con:

- Centro: Restaurante Centro.
- Almacenes: Cocina, Economato y Cámara.
- Artículos auditados:
  - fresco verdura: AUDIT TOMATE FRESCO;
  - fresco pescado: AUDIT SALMON FRESCO;
  - fresco carne: AUDIT POLLO FRESCO;
  - seco: AUDIT ARROZ SECO;
  - congelado: AUDIT GUISANTE CONGELADO;
  - limpieza: AUDIT DETERGENTE LIMPIEZA;
  - lácteo fresco: AUDIT NATA LACTEO;
  - elaborado/preparación: AUDIT SALSA BASE.

Se configuraron mínimos/máximos, se hizo carga inicial, se creó una receta “AUDIT SALSA BASE”, se añadieron ingredientes con merma, se generó una producción desde receta, se confirmó la producción y se generó un pedido sugerido.

---

## 3. Validación de fórmula de merma

La receta usó cantidades netas y el sistema calculó el bruto correctamente:

| Ingrediente | Neto | Merma | Bruto esperado | Bruto obtenido | Estado |
|---|---:|---:|---:|---:|---|
| Tomate fresco | 1,000 kg | 12% | 1,136 kg | 1,136 kg | Correcto |
| Salmón fresco | 0,200 kg | 8% | 0,217 kg | 0,217 kg | Correcto |
| Arroz seco | 0,500 kg | 0% | 0,500 kg | 0,500 kg | Correcto |
| Nata lácteo | 0,300 kg | 0% | 0,300 kg | 0,300 kg | Correcto |

Conclusión: la lógica crítica `bruto = neto / (1 - merma%)` funciona en receta y se traslada a producción.

---

## 4. Coste de receta

Resultado calculado en el simulacro:

- Coste base: **9,3949 €**.
- Coste con contingencia 5%: **9,8646 €**.
- Food cost objetivo: **30%**.
- Precio sugerido sin IVA: **32,8820 €**.
- IVA 10%: **3,2882 €**.
- Precio sugerido con IVA: **36,1702 €**.

Conclusión: el cálculo financiero responde correctamente con precios actuales y merma.

---

## 5. Fallo crítico detectado y reforzado

### 5.1. Problema

Al crear una receta con rendimiento final `2 kg`, el sistema guardaba:

- `yield_final_qty = 2`
- `yield_final_unit = g`

Esto equivale a **2 gramos**, no a **2 kilos**.

Impacto real observado antes del refuerzo:

- La producción de la receta entraba al stock como **0,002 kg**.
- Debería entrar como **2 kg**.

### 5.2. Causa técnica

La función de normalización convertía la unidad `kg` a unidad canónica `g` antes de multiplicar la cantidad por 1000. Al perder la señal original `kg`, ya no podía convertir `2 kg` a `2000 g`.

Archivos afectados:

- `backend/app/services/recipes_service.py`
- `backend/app/services/recipes_form_service.py`
- mismas copias dentro de `app/backend/app/services/`

### 5.3. Refuerzo aplicado

Se modificó la normalización de rendimiento de receta para leer primero la unidad original:

- `kg`, `kilo`, `kilos`, `l`, `lt`, `litro`, `litros` → cantidad × 1000 y unidad interna `g`.
- `ml` → cantidad directa y unidad interna `g`.
- `ud` → se mantiene como unidad.

### 5.4. Resultado tras el refuerzo

Tras repetir el simulacro:

- receta guardada como `yield_final_qty = 2000`, `yield_final_unit = g`;
- línea IN de producción: `qty_base = 2,0 kg`;
- stock de elaborado AUDIT SALSA BASE en Cocina: `2,0 kg`.

Estado: **corregido**.

---

## 6. Puntos débiles que quedan

### 6.1. Producción descuenta ingredientes desde el almacén de la producción, no desde el almacén real del artículo

En el simulacro, la producción se creó en Cocina. El sistema consumió tomate, salmón, arroz y nata desde Cocina, aunque esos artículos estaban cargados en Cámara/Economato.

Resultado observado:

| Artículo | Stock real cargado | Movimiento de producción | Efecto |
|---|---|---|---|
| Tomate fresco | Cámara +5 kg | Cocina -1,136 kg | Crea negativo en Cocina y no baja Cámara. |
| Salmón fresco | Cámara +1 kg | Cocina -0,217 kg | Crea negativo en Cocina y no baja Cámara. |
| Arroz seco | Economato +6 kg | Cocina -0,5 kg | Crea negativo en Cocina y no baja Economato. |
| Nata lácteo | Cámara +2 kg | Cocina -0,3 kg | Crea negativo en Cocina y no baja Cámara. |

Riesgo: el stock por almacén queda contablemente correcto solo si todo se gestiona desde el mismo almacén. En una operativa real con Cámara/Economato/Cocina, puede generar negativos falsos y pedidos incompletos.

Refuerzo recomendado:

1. En cada línea OUT de producción, resolver almacén de consumo por prioridad:
   - preferencia `item_location_prefs` del centro/artículo;
   - almacén según `stock_area`: frescos→Cámara, secos→Economato, limpieza→Economato, congelados→almacén congelado/Cocina si no existe otro;
   - almacén de la producción solo como último fallback.
2. Guardar `warehouse_id` por línea de producción, no solo en cabecera.
3. En confirmación, cada salida debe impactar su almacén de origen y la entrada del elaborado sí debe impactar el almacén de producción.

No lo he tocado en este refuerzo porque requiere migración de esquema o una regla de compatibilidad para producciones ya existentes.

---

### 6.2. Unidades compatibles de forma demasiado amplia

El sistema acepta `l` contra artículos base `kg`. Esto viene de la regla operativa de tratar líquidos por peso, pero se aplica también a sólidos.

Ejemplo probado:

- movimiento de AUDIT TOMATE FRESCO con unidad `l` fue aceptado como entrada válida.

Riesgo: un usuario puede introducir litros en un sólido y contaminar stock/costes.

Refuerzo recomendado:

- Añadir campo `unit_family` o `is_liquid` en artículos.
- Permitir `l/ml ↔ kg/g` solo si el artículo está marcado como líquido o si el usuario confirma equivalencia.
- Para sólidos, bloquear `l/ml` salvo conversión definida.

No lo he tocado porque ahora mismo no existe una propiedad fiable para distinguir líquidos de sólidos sin romper la política global de trabajar líquidos por peso.

---

### 6.3. Pedido por necesidades de producción no añadió líneas después de producción confirmada

En el simulacro, `pedido_necesidades_produccion` añadió 0 líneas, y `pedido_sugerencias_minmax` añadió 3. La causa probable es que la producción ya estaba confirmada y el consumo quedó en Cocina, mientras el min/max principal estaba en Cámara/Economato.

Riesgo: si el consumo se registra en el almacén equivocado, el pedido automático puede no ver correctamente qué posición necesita reposición.

Refuerzo recomendado:

- Resolver primero el punto 6.1.
- Hacer que el pedido post-producción lea consumos por almacén real de línea, no solo por cabecera de producción.

---

### 6.4. Riesgo por doble árbol de código

El ZIP contiene dos copias funcionales:

- `backend/app/...`
- `app/backend/app/...`

En este caso quedaron sincronizadas tras el refuerzo, pero es un riesgo permanente: si se modifica una copia y no la otra, el launcher podría ejecutar una versión distinta a la auditada.

Refuerzo recomendado:

- Mantener una sola ruta viva: `backend/app`.
- Dejar la otra como archivo histórico o eliminarla después de comprobar que ningún `.command` depende de ella.

---

## 7. Resultado de pedidos

Tras confirmar la producción y lanzar sugerencias por min/max, el sistema generó pedido para artículos bajo mínimo:

| Línea generada | Almacén | Cantidad |
|---|---|---:|
| AUDIT SALMON FRESCO | Cámara | 4 kg |
| AUDIT POLLO FRESCO | Cámara | 6 kg |
| PATATA | Cámara | 4 kg |

Conclusión: el pedido sugerido funciona, pero depende de que stock/minmax estén en la misma posición lógica que el consumo. El caso de consumo desde Cocina demuestra que el siguiente refuerzo importante debe ser almacén por línea de producción.

---

## 8. Estado final

### Reforzado ya aplicado

- Corrección de rendimiento final de receta en kg/l → gramos internos.
- Verificación de que la producción entra 2 kg de elaborado cuando la receta declara 2 kg.
- Sin tocar OCR.
- Sin tocar dictado por voz.

### Próximo refuerzo prioritario

Implementar consumo de producción por almacén real de cada ingrediente. Esto evitará negativos falsos en Cocina y hará que los pedidos automáticos post-producción sean más fiables.

---

## 9. Recomendación técnica de siguiente bloque

Bloque propuesto: `v8_7_293_producciones_warehouse_line_fix`.

Objetivo:

1. Añadir `warehouse_id` opcional a `production_lines`.
2. Al cargar receta en producción, resolver almacén de salida por artículo.
3. En confirmación, usar almacén de línea para OUT y almacén de cabecera para IN.
4. Mantener compatibilidad: si una línea antigua no tiene `warehouse_id`, usar cabecera.
5. Repetir simulacro completo.

Este bloque es más delicado que el refuerzo de rendimiento porque afecta movimientos contables de stock.
