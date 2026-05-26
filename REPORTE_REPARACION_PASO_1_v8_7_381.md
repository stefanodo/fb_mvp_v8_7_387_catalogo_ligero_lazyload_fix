# REPORTE REPARACIÓN PASO 1 · v8_7_381

## Prioridad tratada
Se repararon los dos fallos críticos detectados en auditoría exhaustiva v8_7_380:

1. `backend/app/static/js/core.js` roto por doble declaración de constantes.
2. `backend/app/static/js/albaranes.js` roto por plantilla Jinja dentro de archivo JS estático.

## Resultado técnico
Todos los archivos JavaScript estáticos pasan validación sintáctica con `node --check`.

## Impacto esperado
- Recuperación de JavaScript global en pantallas que dependan de `core.js`.
- Menor riesgo de botones que no reaccionen, filtros que no funcionen o formularios dinámicos rotos.
- Recuperación de JavaScript en Albaranes/OCR para proveedor OCR y revisión.

## Riesgos pendientes
- Las páginas de Admin, Stock e Inventario siguen siendo muy pesadas.
- Hay riesgo de saltos visuales y lentitud por exceso de formularios/render inicial.
- La auditoría visual real en navegador/móvil sigue pendiente.
- Producciones/Pedidos/Mermas necesitan datos demo completos para probar flujos completos.

## Verificaciones realizadas
- Python compileall OK.
- Import app OK.
- JS check OK para todos los JS.
- Rutas principales OK.
- APIs LAB principales OK.

## Decisión
Este ZIP debe considerarse un hotfix de estabilidad JS, no una versión funcional nueva.
