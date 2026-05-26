# INFORME CAMBIOS v8_7_345

## Inventario · guardado real blindado
- El botón de conteo ahora se llama claramente **Guardar conteo real**.
- Añadido aviso visible: escribir cantidad real + guardar conteo real.
- Añadido botón inferior sticky para no perder la acción al bajar por la lista.
- Al escribir cantidad, la línea se marca automáticamente como contada.
- El backend ya no crea líneas vacías nuevas sin cantidad/check/nota.
- Si una línea llega sin almacén pero la sesión tiene almacén válido, se usa el almacén de la sesión para poder guardar y conciliar.
- Cierre y conciliación también usan el almacén de sesión como fallback cuando la línea no trae almacén.

## Pruebas
- Compilación backend: OK.
- Import FastAPI: OK.
- Render Inventario: OK.
- Simulacro POST /inventory/counts/save_form: OK.
