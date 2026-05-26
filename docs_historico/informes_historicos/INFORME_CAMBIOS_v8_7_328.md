# System MAC v8_7_328 · UI contraste + Inventario navegación + IA Recetas navegación

## Cambios aplicados

1. Inventario
- El cambio de bloque ya no dispara guardado de sesión antes de navegar.
- Se evita el parpadeo/recarga doble por POST 303 + GET.
- Se elimina la etiqueta “SELECCIONADO” dentro del botón.
- El bloque activo queda solo iluminado de forma sutil.
- Se conserva ancla de trabajo sin subir al inicio de forma agresiva.

2. Contraste y colores
- Operativa y Mermas reciben overrides oscuros para reducir paneles blancos.
- Tarjetas y KPIs pasan a tonos System MAC: fondo oscuro, borde suave, acento dorado limitado.
- Inputs y avisos armonizados con el resto del sistema.

3. Recetas móvil
- Foto y botones se refuerzan con layout móvil más estable.
- Líneas de ingredientes se reorganizan en móvil para evitar solapes.

4. IA Recetas LAB
- Se mantiene como laboratorio aislado.
- Navegación visible: Inicio, Laboratorio, IA Recetas, Borradores.

## No tocado
- OCR de albaranes.
- Dictado/voz antiguo.
- Conversión automática de Recetas IA a receta maestra.
- Lógica crítica de stock, producción y pedidos.

## Validaciones
- Compilación Python backend/app: OK.
- Importación app principal: OK.
- Revisión estática de rutas y plantillas: OK.
