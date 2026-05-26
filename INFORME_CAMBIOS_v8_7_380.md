# INFORME CAMBIOS · v8_7_380

Build: `v8_7_380_auditoria_global_cocteleria_unidades_costes`
Fecha: 22/05/2026

## Cambios aplicados antes del ZIP

### Coctelería / Barra · editor de cócteles

1. **Unidad controlada**
   - El campo `Unidad` en líneas de escandallo ya no es texto libre.
   - Ahora se renderiza como selector controlado: `ml`, `gr`, `ud`.
   - El backend fuerza la unidad base real del ingrediente/preparado si el usuario intenta enviar otra unidad.
   - Ejemplo validado: `Sal` enviada como `ml` queda guardada como `gr`.

2. **Coste automático no editable normal**
   - El coste unitario se toma automáticamente desde `Stock Bar` o `Producción Bar`.
   - El campo visible de coste pasa a ser informativo.
   - El backend ignora overrides normales desde UI para evitar errores de coste manual.
   - Ejemplo validado: `Sal 10 gr` ignora `999 €/u` enviado en formulario y guarda `0,0005 €/gr`.

3. **Crear cóctel sin código fantasma**
   - `Crear cóctel` abre ficha visual vacía.
   - No crea registro ni código hasta pulsar `Guardar ficha` con nombre informado.
   - Si falta nombre, devuelve `Nombre requerido`.
   - Se añadió control de nombre duplicado por nombre normalizado en negocio/local/bar demo.

4. **Build ID actualizado**
   - Se actualizó `VERSION_BUILD.txt` y `BUILD_ID` interno.

## Simulacro interno

Validado con `FB_MVP_RUNTIME_DIR` apuntando a la base empaquetada del ZIP:

- `/` OK
- `/?page=laboratorio` OK
- `/?page=operativa` OK
- `/?page=stock` OK
- `/?page=recetas` OK
- `/?page=producciones` OK
- `/?page=pedidos` OK
- `/?page=albaranes` OK
- `/?page=inventario` OK
- `/?page=mermas` OK
- `/?page=admin` OK
- `/api/lab/bar/summary` OK
- `/api/lab/bar/editor-options` OK
- `/api/lab/bar/cocktails/search?q=cuba` OK
- `/api/lab/bar/stock/summary` OK
- `/api/lab/bar/inventory/summary` OK
- `/api/lab/tpv/summary` OK

Prueba específica:

- Crear ficha sin nombre: bloqueado correctamente.
- Crear ficha temporal con nombre: genera código al guardar.
- Añadir línea `Sal 10` enviando unidad incorrecta `ml`: backend guarda `gr`.
- Enviar coste manual falso `999`: backend guarda coste automático real `0,0005`.
- Registro temporal de prueba eliminado de la base empaquetada.

