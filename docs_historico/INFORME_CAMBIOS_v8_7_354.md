# System MAC v8_7_354

## Cambios aplicados

1. Inicio / dashboard dirección
- Añadido selector de modo Mensual / Diario.
- Añadido campo Día junto a Mes y Año.
- El informe de inventario puede filtrar por día concreto sin romper el mensual.
- El filtro móvil queda en dos columnas y con ayuda visible.

2. Admin / IA
- Separada la prueba real de OpenAI y la prueba real de Deepgram.
- El estado ya no se interpreta solo como “key cargada”: los botones prueban conexión real.
- Si falla, devuelve proveedor, modelo, idioma, código y detalle técnico plegado.

3. Recetas
- Añadido aviso cuando una receta no tiene ingredientes.
- Evita que 0,00 € parezca un cálculo válido cuando falta la base de coste.

4. Centro IA
- Mantiene respuesta humana como salida principal.
- JSON queda relegado a diagnóstico técnico.

## Pruebas internas
- `python3 -m compileall -q backend/app`: OK.
- Import FastAPI: OK.
- Dashboard Inicio mensual/diario: HTTP 200.
- Admin: HTTP 200.
- Recetas: HTTP 200.
- Centro IA: HTTP 200.
- Mobile beta: HTTP 200.
- Simulación dashboard diario 2026-05-21: OK.

## Nota
- La prueba real de Deepgram necesita una clave Deepgram válida pegada en Admin > IA.
- La prueba real de OpenAI necesita clave y salida a internet desde el Mac.
