# HANDOVER INTERNO CONTINUIDAD · v8_7_370

## Estado actual
Se mantiene el bloque Coctelería/Barra separado de Cocina. La versión añade una pantalla de ficha técnica editable para cócteles dentro de Laboratorio > Coctelería / Barra.

## Cambios clave
- Buscar cóctel escribiendo con autocompletado.
- Crear ficha técnica de cóctel.
- Editar datos generales.
- Editar escandallo completo.
- Añadir/quitar ingredientes.
- Diferenciar origen: Stock Bar o Producción Bar.
- Editar cantidades, unidades, mermas y coste unitario.
- Guardar procedimiento.
- Recalcular costes, margen, precio sugerido y alcohol %.

## Blindajes
- Cocina sigue usando conversión kg/gr según reglas existentes.
- Barra usa ml/gr sin convertir visualmente a kg.
- No tocar Stock Cocina desde Barra.
- No tocar stock productivo en TPV LAB.
- No conectar TPV real todavía.
- Todo dato nuevo de Coctelería sigue marcado demo/no productivo.

## Pendientes recomendados
1. Pasar Coctelería desde Laboratorio a módulo propio cuando el flujo esté validado.
2. Añadir carga real de foto de cóctel, no solo ruta/texto.
3. Añadir selector avanzado de ingredientes con precio automático visible antes de guardar.
4. Añadir duplicar cóctel.
5. Añadir impresión/PDF de ficha técnica de cóctel.
6. Añadir permisos por rol cuando deje de ser LAB.

## v8_7_375 · Coctelería / Barra
Se compactó el escandallo editable de cócteles: ingrediente primero, origen abreviado, cantidad/unidad/merma/coste/bruto/acciones en una sola fila de escritorio, y Guardar/Quitar juntos. Los ingredientes existentes quedan bloqueados para evitar cambiar el nombre de una línea ya vinculada a stock/preparado; para cambiar ingrediente se debe quitar y añadir de nuevo. Cantidades, unidades, mermas y costes siguen editables.


## v8_7_377 · Coctelería buscador sin lista fija

Se ocultó el listado permanente de cócteles en Laboratorio > Coctelería / Barra. La selección queda mediante buscador con sugerencias al escribir, selector y botón Crear cóctel. La ficha técnica se muestra solo al elegir o crear un cóctel.

---

## Handover añadido · v8_7_380

Se aplicaron correcciones puntuales en Coctelería / Barra antes de la auditoría global:

- En el editor de cócteles, la unidad de línea ya no es texto libre; queda controlada por selector `ml/gr/ud` y el backend fuerza la unidad base real del ingrediente/preparado.
- El coste unitario de línea se toma automáticamente desde Stock Bar o Producción Bar; la UI lo muestra como informativo y el backend ignora overrides normales para evitar errores de coste manual.
- Al crear cóctel, no se genera código ni registro hasta pulsar Guardar ficha con nombre informado. Si no hay nombre, no guarda. Si el nombre ya existe normalizado en el mismo negocio/local/bar, bloquea duplicado.
- Se generó `REPORTE_AUDITORIA_GLOBAL_v8_7_380.md` con fallos, gaps y prioridades.

Mantener criterio: búsqueda/selección/acción separadas; no abrir fichas automáticamente; crear siempre limpia estado; no mezclar Stock Cocina y Stock Bar.

## v8_7_385 · Manual Finanzas Ejecutivas CEO/CFO

Se añadió `MANUAL_FINANZAS_EJECUTIVAS_CEO.md` para fijar el enfoque estratégico de la pestaña Finanzas Ejecutivas.

Objetivo: que el sistema no solo muestre métricas, sino que facilite decisiones ejecutivas mediante una lectura clara:

estado actual → variación → causa probable → impacto económico → riesgo → decisión recomendada.

La unidad base financiera es cada local/restaurante, con vista agregada de grupo. Debe incluir capital invertido, fondos propios, capital financiado, coste financiero al 5 % anual por defecto, working capital, EBITDA, resultado neto estimado, ROIC, pasivo laboral, food cost, beverage cost, prime cost, mermas, compras, desviaciones, análisis por plato/bebida y recomendaciones.

La pestaña debe quedar restringida a dueño/CEO/CFO/dirección/contabilidad/inversor. No debe estar visible para cocina/sala sin permiso.

También se actualizó la redacción de README/LEEME para retirar la frase de ejecutar archivos como explicación de manual principal, manteniendo una redacción de uso más limpia.



---

## Handover v8_7_387_catalogo_ligero_lazyload_fix

### Cambio técnico
Catálogo/Admin queda optimizado con carga progresiva. La página ya no debe incrustar ni renderizar toda la tabla de artículos ni toda la comparativa de proveedores al abrir.

### Archivos tocados
- `backend/app/main.py`: rama ligera para `page == "admin"`; evita carga pesada inicial y supplier_prices completos.
- `backend/app/routers/laboratorio.py`: APIs ligeras `items_page` y `supplier_prices_page`.
- `backend/app/templates/partials/admin_tabs.html`: eliminado wrapper duplicado.
- `backend/app/templates/partials/admin_tab_articulos.html`: tabla lazy-load, búsqueda remota, guardar fila y guardar todas sin recarga.
- `backend/app/templates/partials/admin_tab_precios.html`: comparativa y búsqueda de artículo por API.
- `backend/app/templates/index.html`: en Admin no expone arrays grandes de `ITEMS`/`SUPPLIER_PRICES` al JS inicial.

### Blindaje nuevo
Regla permanente: páginas pesadas = HTML mínimo + datos bajo demanda. No hacer cargas masivas iniciales de catálogo, stock, precios o históricos salvo que sean imprescindibles.

### Pendiente recomendado
Aplicar el mismo patrón por fases a Stock, Inventario, Pedidos y Albaranes si crecen mucho: endpoint paginado, búsqueda remota, render parcial y filtros sin recargar.
