# System MAC · v8_7_355

## Bloque reparado: Inventario · filtros y estado de navegación

### Causa detectada
El problema no era de cálculo de stock, sino de estado de filtros en Inventario:

- El almacén físico seleccionado quedaba guardado en la sesión.
- Al cambiar entre Cocina / Economato / Cámara y después cambiar bloque/familia, la familia anterior podía heredarse aunque ya no correspondiera.
- Ejemplo incorrecto: Cocina + Secos o Cámara + Secos.
- La pantalla podía enseñar una lista coherente con el filtro antiguo, mientras arriba parecía estar seleccionado otro contexto.
- Además no había diagnóstico visible para saber si se estaban mostrando 8 líneas porque realmente solo había 8, o porque el almacén/familia estaba filtrando.

### Corrección aplicada
- Normalización de familia según almacén físico:
  - Economato + Materias primas => Secos.
  - Cámara + Secos/Limpieza heredados => Verduras.
  - Cocina + Secos/Limpieza heredados => Verduras.
- El cambio de almacén añade marca anti-caché `inv_nav_ts`.
- El cambio de familia añade marca anti-caché `inv_nav_ts`.
- El backend vuelve a validar la combinación final antes de construir la vista.
- Se añade diagnóstico visible:
  - almacén activo;
  - bloque activo;
  - familia activa;
  - líneas visibles;
  - total de esa familia en todos los almacenes.

### Resultado esperado
- Ya no debe quedar una vista tipo “Cocina” mostrando Secos heredados de Economato.
- En Materias primas > Verduras se ve cuántas líneas muestra el filtro actual y cuántas existen en total para esa familia.
- Si falta producto por filtro de almacén, el sistema lo indica en pantalla en vez de ocultarlo sin explicación.

### Pruebas internas
- Compilación backend OK.
- Import FastAPI OK.
- Inventario HTTP 200:
  - Materias primas / Verduras.
  - Materias primas / Secos.
  - Producciones / Frío.
- Simulación interna:
  - Economato + Verduras se corrige a Secos.
  - Cocina + Secos se corrige a Verduras.
  - Cámara + Secos se corrige a Verduras.
  - Cámara + Verduras muestra 56 líneas de referencia en la base de prueba.
