# REPORTE AUDITORÍA GLOBAL · v8_7_368

## Estado verificado
- Compilación Python: OK (`python -m compileall backend/app`).
- Arranque FastAPI local: OK.
- Rutas HTML probadas: Inicio, Laboratorio, Stock, Recetas, Producciones, Pedidos, Albaranes, Inventario, Mermas, Admin, Operativa, Móvil: OK 200.
- APIs LAB probadas: TPV, Barra, bebidas por servicio, mixers, albaranes bebidas, pedidos consolidados, albarán único compartido: OK 200.
- Nuevo simulador albarán único compartido: OK.

## Cambios v8_7_368 aplicados
- Añadido en Laboratorio > Coctelería / Barra: `Albarán único compartido proveedor → Cocina + Barra · LAB`.
- Un solo documento proveedor; no crea dos albaranes artificiales.
- Prioridad de reparto:
  1. Pedido previo consolidado Cocina/Barra.
  2. Regla porcentual por artículo/proveedor/local/área.
  3. Revisión si no hay pedido ni regla.
- Simulacros OK:
  - `pedido_previo`: 3 líneas auto-repartidas, 0 revisión.
  - `porcentaje`: 3 líneas auto-repartidas, 0 revisión.
  - `sin_regla`: 1 línea auto-repartida, 1 línea a revisión.

## Fallos / gaps críticos detectados

### 1. El paquete sigue con estructura duplicada raíz/app
Hay archivos duplicados en raíz y dentro de `/app`: comandos, informes, README, handover y VERSION. Esto puede confundir al usuario y al siguiente desarrollo.

Solución: en una futura limpieza, mantener en raíz solo comandos esenciales, README, VERSION, handover actual e informe actual. Mover histórico a `docs_historico/` y eliminar duplicados dentro de `/app` si no los usa ningún lanzador.

### 2. Base runtime fuera del ZIP durante pruebas
La app usa `/home/oai/Documents/F&B_MAC_RUNTIME/fb_mvp_v8.db` como DB runtime. Esto es correcto para no pisar datos, pero en auditoría implica que las pruebas se apoyan en runtime local, no necesariamente en una DB limpia dentro del ZIP.

Solución: añadir modo test con DB temporal por build para auditorías reproducibles.

### 3. Coctelería/Barra está en LAB, no productivo completo
Está separado y funcional como demo, pero todavía no es módulo productivo real. Falta flujo completo de:
- Pedidos Bar reales.
- Inventario Bar real con sesiones/cierres.
- Mermas Bar reales.
- OCR real enlazado a albaranes físicos.
- Reglas productivas de reparto con tolerancias.

Solución: pasar de LAB a módulo operativo por fases, empezando por Stock Bar + Pedidos Bar + Recepción Bar.

### 4. TPV sigue en modo preview y mapeo incompleto
TPV LAB ya no debe conectar stock real. Correcto. Pero si una receta/artículo no está mapeado, devuelve `PENDING_MAPPING` y consumo vacío.

Solución: crear pantalla de mapeos TPV pendientes con acción humana: mapear a receta cocina, cocktail_recipe, beverage_service o item.

### 5. Falta un motor común de coste por área
Cocina y Barra deben mantener unidades distintas. Cocina puede normalizar a g/kg; Barra debe preservar ml/gr. Ahora hay lógica repartida por servicios.

Solución: crear `cost_engine_service.py` con perfiles:
- `kitchen_profile`: kg/g.
- `bar_profile`: ml/gr.
- validación de unidades incompatibles.

### 6. Demasiados `except Exception` silenciosos
Hay muchos bloques defensivos. Algunos son correctos para robustez, pero otros pueden ocultar fallos y devolver pantallas aparentemente correctas con datos incompletos.

Solución: crear logger interno y tabla `system_error_log`; evitar `except Exception: pass` salvo en UI no crítica.

### 7. Albarán único compartido aún no crea movimientos productivos
El nuevo bloque simula el split, pero no crea entradas reales en stock cocina/barra. Es correcto en LAB, pero falta fase productiva.

Solución: cuando se valide productivo, crear un documento único `receipt` y líneas hijas `receipt_line_splits` con movimientos separados por destino.

### 8. Dashboard todavía no debe absorber Barra hasta estabilizar base
Dashboard puede leer datos de Barra en el futuro, pero si se conecta ahora puede mezclar demo con real.

Solución: todo dashboard debe filtrar `demo_data=0` salvo modo LAB explícito.

## Gaps funcionales pendientes por bloque

### Cocina / Recetas
- Mantener control estricto de subrecetas: `qty_gross`, `qty_net`, `yield_final_qty`.
- Revisar que impresiones sigan con foto y costes opcionales.
- Validar que ingredientes nuevos de recetas IA no queden vacíos; deben quedar pendientes de catálogo.

### Stock / Inventario
- Revisar definitivamente entrada manual de stock para artículo existente, caso PUERRO.
- Evitar saltos/parpadeos al cambiar bloque/familia.
- Añadir trazabilidad multiusuario en conteos de inventario.

### Pedidos Cocina
- Cabecera visual todavía era un pendiente histórico: evitar solapes.
- Integrar futura consolidación real con Barra sin mezclar stocks.
- El pedido consolidado debe guardar split original para recepción.

### Albaranes OCR
- OCR debe decidir área: Cocina, Barra, Compartido, Revisión.
- Documento único compartido con splits internos.
- Diferencias cantidad/precio/unidad deben ir a revisión según tolerancias configurables.

### Coctelería / Barra
- Completar Pedidos Bar productivos.
- Completar Inventario Bar.
- Completar Mermas Bar.
- Añadir albaranes reales de bebidas y compartidos.
- Añadir reglas para botellas abiertas, vino por copas, mixers multi-servicio y barriles en productivo.

### TPV LAB / futuro TPV real
- Crear mapeo pendiente con estado y confianza.
- Distinguir producto TPV de cocina, cóctel, bebida por servicio, insumo vendible.
- No descontar stock hasta validación de integración real.

### Continuidad / Offline
- La arquitectura de eventos está bien orientada.
- Falta pantalla final de resolución de conflictos con aprobar/descartar/convertir en borrador.

### Conciliación albarán-factura-pago
- Sigue siendo maqueta LAB.
- Falta vincular documentos reales, condiciones de pago por proveedor y paquete gestoría.
- Pago real debe mantenerse bloqueado con validación humana doble.

## Recomendación de orden de solución
1. Limpiar paquete raíz y duplicados.
2. Crear motor de coste común por perfiles Cocina/Barra.
3. Convertir albarán único compartido LAB en modelo productivo seguro con splits.
4. Crear Pedidos Bar reales con min/max y consolidación con Cocina.
5. Crear Inventario/Mermas Bar.
6. Crear pantalla de mapeo TPV pendiente.
7. Resolver fallos visuales pendientes de Inventario/Pedidos/Mermas.
8. Añadir logger de errores y auditoría técnica.

