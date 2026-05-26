# REPORTE AUDITORÍA GLOBAL · v8_7_380

Build auditado: `v8_7_380_auditoria_global_cocteleria_unidades_costes`
Fecha: 22/05/2026

## Alcance

Auditoría sobre el paquete actual tras las últimas modificaciones de Laboratorio, TPV LAB, Operativa rápida y Coctelería / Barra. Se revisaron rutas principales, APIs LAB, estructura de base de datos empaquetada, puntos de fragilidad y gaps funcionales.

## Resultado general

La aplicación **arranca y responde** en rutas principales. No se detectaron errores de sintaxis Python ni JavaScript en `laboratory.js`.

Estado real del build:

- Cocina/Stock/Recetas/Pedidos/Inventario siguen siendo el núcleo operativo.
- Coctelería / Barra está en estado **LAB/demo no productivo**.
- TPV sigue en estado **PREVIEW**, no TPV real.
- La parte de Barra ya tiene base separada para insumos, stock inicial, producciones internas y recetas de cócteles, pero no todos los submódulos son productivos.

## Pruebas realizadas

### Rutas HTML

Todas respondieron `200 OK`:

- `/`
- `/?page=laboratorio`
- `/?page=operativa`
- `/?page=stock`
- `/?page=recetas`
- `/?page=producciones`
- `/?page=pedidos`
- `/?page=albaranes`
- `/?page=inventario`
- `/?page=mermas`
- `/?page=admin`

### APIs LAB verificadas

Todas respondieron `200 OK`:

- `/api/lab/bar/summary`
- `/api/lab/bar/editor-options`
- `/api/lab/bar/cocktails/search?q=cuba`
- `/api/lab/bar/stock/summary`
- `/api/lab/bar/inventory/summary`
- `/api/lab/bar/orders/summary`
- `/api/lab/bar/shared-receipts/summary`
- `/api/lab/tpv/summary`

### Validaciones específicas de Coctelería

- Crear ficha sin nombre: bloqueado.
- Código de cóctel: no se genera hasta guardar ficha con nombre.
- Unidad en escandallo: selector/control backend.
- Coste unitario: automático desde Stock Bar / Producción Bar; override normal bloqueado.

## Hallazgos priorizados

## Crítico / alto

### 1. Coctelería / Barra sigue siendo LAB, no módulo productivo completo

Tablas existentes en base empaquetada:

- `bar_items`
- `bar_stock_movements`
- `bar_productions`
- `bar_production_lines`
- `bar_production_stock_movements`
- `cocktail_recipes`
- `cocktail_recipe_lines`
- `cocktail_recipe_steps`
- `cocktail_cost_history`
- `bar_alerts`
- `bar_tpv_mappings`

Faltan como estructura productiva estable:

- `bar_orders`
- `bar_order_lines`
- `bar_inventory_sessions`
- `bar_inventory_counts`
- `bar_waste_movements`
- `bar_receipts`
- `bar_receipt_lines`
- `bar_supplier_item_prices`

Riesgo: la UI ya muestra conceptos de Stock/Inventario/Pedidos/Albaranes Bar, pero una parte sigue siendo resumen LAB o simulador. Hay que evitar que parezca productivo hasta tener tablas y flujos reales.

Solución recomendada: siguiente bloque específico para convertir Stock Bar + Inventario Bar + Mermas Bar a estructuras reales, manteniendo flags `demo_data` cuando corresponda.

---

### 2. Dashboard no debe mezclar demo con productivo

El bloque Barra tiene `demo_data=true` y `non_productive_demo=true`. El Dashboard global todavía no debe sumar estos datos como datos reales.

Solución:

- Añadir filtros obligatorios `demo_data=0` en dashboards productivos.
- Crear Dashboard LAB separado si se quieren ver métricas demo.

---

### 3. Albarán único compartido Cocina/Barra sigue siendo simulador LAB

La lógica está bien planteada:

1. Pedido previo con desglose.
2. Si no hay pedido, porcentaje configurado.
3. Si no hay regla, revisión.

Pero todavía no está integrada en el pipeline productivo real de OCR/albaranes.

Riesgo: creer que la recepción real ya reparte Stock Cocina/Stock Bar.

Solución: integrar después con `receipts` reales y movimientos productivos, manteniendo validación humana.

---

### 4. Falta login/roles productivos

El sistema todavía funciona como aplicación local/beta. Para multi-restaurante real faltan:

- usuarios individuales,
- permisos por centro,
- permisos por módulo,
- trazabilidad por usuario,
- bloqueo de edición de recetas maestras salvo admin.

Esto no impide la beta local, pero sí el despliegue serio.

## Medio

### 5. Páginas pesadas

Tamaños observados en HTML renderizado:

- Stock: ~842 KB
- Inventario: ~920 KB
- Admin: ~845 KB
- Laboratorio: ~166 KB

Riesgo: lentitud en móvil, saltos de pantalla y recargas bruscas.

Solución: carga progresiva por pestañas, endpoints JSON y listas bajo demanda.

---

### 6. Exceso de `except Exception`

Se detectaron aproximadamente 392 usos de `except Exception` en `backend/app`.

No todos son errores, pero reducen observabilidad si no registran contexto.

Solución:

- Añadir logger central.
- Registrar módulo, ruta, payload resumido y traceback controlado.
- Evitar silencios en OCR, albaranes, pedidos e inventario.

---

### 7. OCR con muchos `pass` silenciosos

`backend/app/ocr/engine.py` contiene múltiples puntos donde se ignoran excepciones.

Riesgo: fallos de proveedor/OCR difíciles de diagnosticar.

Solución: log técnico interno + aviso visible cuando OCR cae en fallback.

---

### 8. Duplicación documental/estructura heredada

El paquete conserva documentos repetidos entre raíz y `/app`.

Riesgo: confusión sobre qué informe o comando es vigente.

Solución: limpiar en un bloque posterior la raíz del ZIP, dejando solo comandos, README, VERSION, informes actuales, backend y docs históricos ordenados.

---

### 9. Build interno del código venía desfasado

`BUILD_ID` interno seguía en v8_7_373 antes de esta actualización.

Estado: corregido en este ZIP a `v8_7_380_auditoria_global_cocteleria_unidades_costes`.

## Bajo / UX

### 10. Coctelería necesita más separación visual por submódulo

Ya se ocultaron listados permanentes y se añadieron submódulos, pero falta terminar la lógica visual:

- Recetas cócteles
- Stock bebidas
- Inventario Bar
- Mermas Bar
- Pedidos Bar
- Albaranes Bar
- Bebidas por servicio
- Producciones Bar

Recomendación: mantener una barra interna de botones y no cargar el contenido hasta pulsar.

---

### 11. Fotos de cócteles pendientes

La UI tiene zona de foto, pero falta flujo real de subida/almacenamiento para fotos de cócteles equivalente al de recetas de cocina.

Solución: endpoint upload específico para cocktail photo y guardado en carpeta de runtime/uploads/bar.

---

### 12. Servicio TPV LAB necesita pantalla de mapeos pendientes

TPV LAB ya no debe tocar stock definitivo. Falta:

- listado de ventas sin mapeo,
- mapeos por confianza,
- revisión humana,
- reglas aprendidas supervisadas.

## Conclusión

El build actual está estable para seguir trabajando. Los fallos principales no son de arranque, sino de **madurez funcional**: Coctelería/Barra está creciendo desde LAB hacia módulo real y necesita convertir sus simuladores en flujos productivos controlados.

Prioridad recomendada para próximos pasos:

1. Stock Bar real + pantallas agrupadas definitivas.
2. Inventario Bar real.
3. Mermas Bar real.
4. Pedidos Bar reales con consolidación Cocina/Barra.
5. Albaranes OCR reales con reparto a stocks.
6. Dashboard con filtro productivo/demo.
7. Limpieza de paquete y logs.

