# INFORME CAMBIOS v8_7_319 WORKING

Estado: carpeta de trabajo, sin ZIP.

## Bloques aplicados

1. Ranking mensual de ventas de platos en apartado separado.
   - Fuente preparada: `pos_sales_item_daily`.
   - No inventa ventas si no hay TPV/importación.
   - Muestra unidades vendidas, venta neta, coste de receta, margen bruto y riesgo de margen.

2. Preparación TPV multi-negocio.
   - Tablas neutrales añadidas: `pos_integrations`, `pos_sales_daily`, `pos_sales_item_daily`.
   - Preparado para restaurante, bar, delivery, retail, hotel, catering, cocina central y otros.

3. Informe imprimible.
   - Nueva ruta: `/direction/recipe-sales/print`.
   - Ranking por unidades, venta neta, margen, canal y tipo de negocio.

4. Mejoras opcionales preparadas.
   - Mapa TPV ↔ recetas.
   - Canales: salón, barra, delivery, take away, eventos, catering y hotel.
   - Venta prevista para producción y pedidos sugeridos.
   - Ingeniería de menú.
   - Alertas de precio para platos muy vendidos.

## Blindajes

- No modifica stock.
- No modifica recetas.
- No confirma pedidos.
- No acopla TPV real todavía.
- No inventa ventas ni ranking si no hay datos.
- OCR no tocado.
- Dictado/voz no tocado.
- Recetas IA laboratorio no acoplado.
