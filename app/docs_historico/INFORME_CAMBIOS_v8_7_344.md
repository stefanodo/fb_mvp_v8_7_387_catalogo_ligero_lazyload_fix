# System MAC · v8_7_344 · Limpieza profunda producciones/pedidos/inventario/recetas

## Cambios aplicados
- Producciones: limpieza profunda de candidatos. Se excluyen platos finales, ingredientes sueltos, fotos/importaciones tipo IMG y elementos sin clasificación producible.
- Producciones por rubro: Fríos/Calientes/Postres quedan como temperatura; Salsas/Guarniciones/Bases/Masas/Pastelería/Porcionados como partida operativa.
- Inventario > Producciones: reutiliza el mismo filtro limpio para no listar platos finales como Salmón con puré, Solomillo con patatas o Patatas al cabrales salvo que se marquen explícitamente como producibles.
- Pedidos: cabecera reforzada para evitar solapes; Producciones se muestran por rubro; Libres añade bloc de ideas/notas que no afectan stock ni pedidos reales hasta revisión.
- Recetas: columna de coste más humana, con €/kg o €/l cuando procede; foto subida y ampliada con botones debajo sin mezclarse.
- Inventario: cabecera de sesión más clara, estado editable con ayuda, y explicación de Guardar sesión/Nueva sesión.

## Pruebas internas
- compileall backend/app: OK.
- Import FastAPI: OK.
- Render HTTP 200: Inicio, Recetas, Producciones, Pedidos, Inventario y Mermas.
- Búsqueda HTML: se bloquean en Producciones/Inventario/Pedidos nombres tipo IMG, ingredientes sueltos y platos finales observados.

## Nota
No puedo confirmar audio físico real de iPhone/Mac desde este entorno; se mantiene el fallback de texto/dictado y español estricto del build anterior.
