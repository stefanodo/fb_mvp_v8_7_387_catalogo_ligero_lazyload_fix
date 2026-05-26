# INFORME CAMBIOS v8_7_360

## Acceso móvil beta / QR
- Rehecha la pantalla `/movil` para no depender de un único QR.
- Añadidos dos accesos claros:
  - QR recomendado `.local` (`MacBook-Air-de-Mauro.local:8000`).
  - QR alternativo por IP LAN (`192.168.x.x:8000` o la IP activa).
- La pantalla avisa si se abre desde `127.0.0.1`: eso solo sirve en el Mac, no en el móvil.
- QR y HTML salen con `Cache-Control: no-store` para evitar QR viejo si cambia Wi‑Fi/hotspot.
- Añadido diagnóstico visible con IPs detectadas, enlace activo y cliente.
- Botones copiar enlace, revisar conexión y limpiar caché.

## Pruebas internas
- `compileall backend/app`: OK.
- Ruta `/movil`: código actualizado con doble QR y sin caché.
- Ruta `/mobile_qr.png?kind=local` y `?kind=ip`: generador parametrizado.

## Nota
- Si Safari/iPhone bloquea HTTP por “Solo HTTPS”, no se puede forzar desde una web local. En beta local usar `.local`, IP o Chrome; en producción final irá con dominio HTTPS real.
