# Manual de usuario · System MAC / F&B MAC

Versión viva del manual. Este documento debe actualizarse en cada ZIP cuando se añadan o cambien funciones.

## 1. Primer arranque
1. Descomprime el ZIP.
2. Abre `DESBLOQUEAR_y_INICIAR.command`.
3. Espera a que aparezca el servidor local.
4. En Mac entra por `http://127.0.0.1:8000`.
5. En beta móvil local usa la pantalla `Acceso móvil beta`; en versión final online se usará dominio, login y PWA.

## 2. Principio de seguridad
System MAC prioriza no romper stock, recetas maestras ni datos contables. Las acciones críticas quedan en borrador, revisión o PREVIEW hasta validación humana.

## 3. Catálogo
### Artículos
Sirve para crear y editar materias primas y preparaciones.
- `Insumo`: materia prima comprable/inventariable.
- `Preparación`: elaboración interna/subreceta con posible stock propio.
- `Guardar todas las modificaciones`: permite editar varias filas y guardar en bloque sin perder cambios.

### Comparativa proveedores
Antes llamada `Precios proveedor`. Sirve para comparar precios por artículo/proveedor, proveedor habitual, último precio, fecha y diferencias. El Dashboard muestra alertas; esta pestaña permite revisar el detalle.

## 4. Recetas
Permite crear fichas técnicas con ingredientes, mermas, coste, foto, alérgenos, rendimiento y carga estructural. Si no hay ingredientes, el sistema debe avisar que no puede calcular coste real.

## 5. Producciones
Debe mostrar solo elaboraciones internas producibles, no platos finales de carta salvo que estén marcados como producibles.

## 6. Pedidos
Flujo recomendado:
1. Selecciona local, responsable y nota opcional.
2. Crea o abre pedido.
3. Añade líneas por bloque: frescos, secos, limpieza, producciones o libres.
4. Revisa detalle.
5. No se envía automáticamente sin validación.

## 7. Mermas
Permite registrar pérdidas por artículo o elaboración. En modo pendiente no descuenta stock definitivo hasta confirmación.

## 8. Inventario
Flujo recomendado:
1. Selecciona almacén: Todos, Cocina, Cámara o Economato.
2. Selecciona responsable.
3. Estado normal: `En conteo`.
4. Pulsa `Guardar sesión` para cabecera.
5. Elige bloque/familia.
6. Cuenta líneas y pulsa `Guardar conteo real`.
7. Al terminar, usa `Cerrar y conciliar stock`.
8. `Nueva sesión desde cero` crea otra sesión; no guarda el conteo actual.

## 9. OÍDO ALFI
Pantalla operativa para escribir o dictar comandos. En móvil se recomienda usar el micrófono del teclado y luego `Ejecutar`. Las acciones críticas se crean como borrador o pendiente.

## 10. Laboratorio
Laboratorio no debe tocar producción real salvo que el sistema lo indique explícitamente. Sirve para probar y preparar futuro.

### Integraciones TPV / Ventas
- Simula ventas desde TPV.
- Preserva venta cruda.
- Mapea producto TPV a receta/artículo.
- Interpreta modificadores.
- Genera consumo teórico en `PREVIEW`.
- No descuenta stock real.
- No modifica recetas maestras.

### Continuidad / Anti-caída
- Simula trabajo sin internet.
- Guarda eventos offline.
- Sincroniza en modo LAB.
- Eventos críticos van a conflicto/revisión.
- Recomendación futura por local: router dual WAN con SIM 4G/5G y SAI para router, TPV, servidor local e impresora.

### Conciliación albarán/factura/pago proveedor
- Prepara relación documental por proveedor.
- Compara albarán OCR contra factura.
- Genera propuesta de vencimiento/pago.
- No ejecuta pagos reales.
- Requiere validación humana final.

## 11. Albaranes y facturas para gestoría
Objetivo futuro: agrupar documentos por proveedor, fecha, mes, local, estado OCR, estado de conciliación y estado contable para crear paquete PDF imprimible/enviable.

## 12. Versión final online
La beta local usa IP/QR. La versión final debe funcionar con dominio, HTTPS, servidor web, base central, login, roles, permisos, sesión persistente y PWA en iPhone, Android, Mac, Windows y tablets.
