# System MAC v8_7_332

Cambios aplicados:

- Inicio: filtros Mes/Año del dashboard mensual rediseñados en HTML/CSS real, con fondo más visible, más anchura y botones Ver/Imprimir alineados.
- Recetas: zona de foto ajustada según referencia: marco limpio y botones Subir foto/Quitar foto justo debajo, alineados y desplazados ligeramente a la izquierda.
- Recetas: refuerzo visual de ingredientes en escritorio y móvil para reducir solapes.
- TPV: Modificadores TPV queda más claro como simulador/aprendizaje supervisado, plegado y no como carga manual diaria.
- Inventario: navegación de rubro reforzada con enlaces independientes, familia por defecto del bloque y navegación con cache-bust para evitar quedarse clavado.
- Stock: navegación de bloques mantiene posición de scroll y evita salto agresivo hacia arriba.
- Mermas: anular merma corregido con cancelación directa sin exigir artículo/cantidad; fecha y hora en chips separados; mejora de contraste en Control de Mermas.
- Operativa: contraste reforzado en Decir tarea y avisos más discretos.
- Pedidos: reglas de cabecera más armónicas y campos Responsable/Nota más amplios.

No tocado:

- OCR de albaranes.
- Dictado/voz antiguo.
- Recetas maestras.

Validación:

- Compilación Python backend/app OK.
- Importación app principal OK.
- Render Inicio, Inventario, Stock, Recetas, Mermas, Control Mermas, Pedidos, Admin OK.
