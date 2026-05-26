# INFORME CAMBIOS · v8_7_364

## Cambios aplicados

1. Se integra el bloque nuevo **Coctelería / Barra** dentro de Laboratorio como módulo separado de Cocina.
2. Se crean tablas propias de Barra: `bar_items`, `bar_stock_movements`, `bar_productions`, `bar_production_lines`, `bar_production_stock_movements`, `cocktail_recipes`, `cocktail_recipe_lines`, `cocktail_recipe_steps`, `cocktail_cost_history`, `bar_alerts` y `bar_tpv_mappings`.
3. Se carga demo no productiva de Barra con flags `demo_data=true`, `non_productive_demo=true` y marca `DATOS_DEMO_NO_PRODUCTIVOS`.
4. Barra mantiene unidades propias en `ml` y `gr`; no hereda la visualización de Cocina que normaliza líquidos a peso.
5. Se cargan 24 insumos demo de Barra, incluidos Agua filtrada y Vermut Rojo/Seco separados.
6. Se cargan 24 movimientos iniciales demo de Stock Bar.
7. Se cargan 6 Producciones Bar/subrecetas internas: syrup simple, zumos exprimidos y garnishes. Todas quedan `es_vendible=false`.
8. Se cargan 10 recetas clásicas de cócteles con escandallo, coste neto/bruto, margen, precio sugerido, histórico de coste, foto pendiente y avisos.
9. Se corrige TPV LAB para resolver consumo teórico con columnas reales `qty_gross`, `qty_net`, `yield_final_qty`, `yield_final_unit` y conversión de coste por unidad base.
10. TPV LAB sigue en modo `PREVIEW`: no conecta TPV real, no descuenta stock real y no modifica movimientos definitivos.

## Simulacro realizado

- `/api/lab/bar/summary` responde OK.
- `/api/lab/bar/load-demo` responde OK.
- `/api/lab/tpv/simulate` con TORTILLA DE PATATA calcula consumo y convierte correctamente `15000 g` de patata a `15 kg` para coste.
- `/ ?page=laboratorio` carga sin error.

## Reglas blindadas

- No tocar Stock Cocina desde Barra.
- No mezclar Recetas Cocina con Cócteles.
- Producciones Bar son insumos internos a coste salvo marca explícita `es_vendible=true`.
- Los precios 2025/2026 son orientativos/demo y deben sustituirse por albaranes reales antes de uso productivo.
- TPV LAB queda como simulador/preparación futura, no integración real.
