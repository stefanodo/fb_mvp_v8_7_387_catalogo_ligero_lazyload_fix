# REPORTE VALIDACIÓN v8_7_382

## Alcance validado

Se validó el paquete después de añadir el dashboard diario de negocio.

## Pruebas

- Compilación Python completa: OK
- Sintaxis JS estáticos: OK
- Importación de `app.main`: OK
- Render de Inicio con rango `2026-05-22`: OK
- Presencia del bloque `daily-business-panel`: OK
- Servicio `build_daily_business_dashboard`: OK

## Resultado de simulacro con datos existentes

Para el rango de prueba 2026-05-22, el servicio leyó ventas LAB existentes en `tpv_sales` y coste teórico asociado cuando pudo mapear recetas/cócteles.

El módulo separa:

- ventas,
- coste teórico,
- food cost %,
- compras/entradas,
- mermas,
- sugerencias.

## Limitaciones actuales

- Barra productiva real aún no tiene todas las tablas definitivas de bebidas por servicio en esta rama.
- Si no hay TPV normalizado real, el dashboard queda en modo lectura preparada.
- Las sugerencias por caducidad dependen de que producciones/botellas/caducidades tengan datos fiables.

## Recomendación siguiente

Conectar el dashboard con:

1. TPV real/importación normalizada.
2. Botellas abiertas Barra.
3. Caducidades reales de producciones Cocina y Barra.
4. Mermas Bar productivas.
5. Inventarios cerrados por día/rango.
