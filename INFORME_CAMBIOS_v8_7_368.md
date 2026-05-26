# INFORME CAMBIOS v8_7_368

## Añadido
- Laboratorio > Coctelería / Barra: simulador de albarán único compartido de proveedor para verduras/frutas/secos comunes.
- Reparto por prioridad: pedido previo Cocina/Barra -> porcentaje configurado por artículo/proveedor/local -> revisión.
- Documento único: no crea dos albaranes artificiales.
- Split interno hacia Stock Cocina y Stock Bar en modo LAB/no productivo.

## Seguridad
- No toca stock productivo.
- No crea pedidos reales.
- No mezcla Stock Cocina y Stock Bar.
- Todo queda marcado demo/no productivo.
