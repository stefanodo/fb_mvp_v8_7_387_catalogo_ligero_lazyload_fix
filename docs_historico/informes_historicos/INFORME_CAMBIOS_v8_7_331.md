# INFORME CAMBIOS · v8_7_331

## Objetivo del hotfix
Corregir dos fallos operativos urgentes:

1. Inventario quedaba clavado en Producciones o no permitía cambiar entre Materias primas / Producciones / Limpieza / Líneas libres hasta tocar Familia.
2. Stock saltaba hacia arriba cada vez que se pulsaba un bloque.

## Cambios aplicados

### Inventario
- El cambio de bloque/rubro ya no depende de la familia.
- El almacén guardado en la sesión deja de bloquear la navegación de bloques.
- Se eliminó la restricción que forzaba el modo según almacén, que podía dejar la pantalla clavada en Producciones.
- Los botones de bloque quedan siempre navegables; el responsable sigue siendo obligatorio para guardar/conciliar, no para cambiar de vista.
- Al cambiar bloque se navega por GET limpio, sin POST previo ni guardado de sesión automático.
- La familia se resetea explícitamente por bloque:
  - Materias primas → Verduras
  - Producciones → Frío
  - Limpieza → Limpieza
  - Líneas libres → Libres
- Se mantiene el foco en la zona de trabajo de inventario sin salto agresivo al inicio.

### Stock
- Al pulsar botones de bloque en Stock, se conserva la posición aproximada de scroll.
- Se evita la sensación de salto brusco hacia arriba tras cambiar Frescos / Producciones / Congelados / Secos / Limpieza / etc.

## Archivos modificados
- backend/app/main.py
- backend/app/templates/sections/inventario.html
- backend/app/templates/partials/stock_actions.html
- VERSION_BUILD.txt
- app/VERSION_BUILD.txt

## Validación realizada
- Compilación backend/app: OK
- Importación app principal: OK
- Render Inventario Materias primas: HTTP 200
- Render Inventario Producciones: HTTP 200
- Render Inventario Limpieza: HTTP 200
- Render Stock Frescos: HTTP 200

## No tocado
- OCR
- Dictado/voz antiguo
- Recetas IA funcionalmente
- Recetas maestras
- Cálculos de stock/merma/producción
