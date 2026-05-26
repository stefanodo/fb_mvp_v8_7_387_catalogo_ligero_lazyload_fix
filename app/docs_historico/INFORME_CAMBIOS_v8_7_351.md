# INFORME CAMBIOS · v8_7_351

## Objetivo
Preparar el siguiente paquete acumulado sin pagos automáticos ni confirmaciones críticas.

## Voz / OÍDO ALFI
- Añadido selector de proveedor STT: `STT_PROVIDER=deepgram|openai|auto|local`.
- Deepgram queda preparado como motor principal de transcripción de voz.
- OpenAI queda para comprensión/IA y como fallback de STT si Deepgram falla.
- Admin > IA permite pegar `DEEPGRAM_API_KEY` desde interfaz.
- Idioma configurable: español por defecto; preparado para francés, italiano, portugués, inglés y multilingüe.
- Diagnóstico de voz muestra proveedor, modelo e idioma.
- No se inventa texto si no hay STT configurado: mantiene fallback de micrófono del teclado + Ejecutar.

## Acceso móvil beta local
- Añadida pantalla `/mobile-beta`.
- Muestra URL actual de acceso móvil, QR dinámico y botón copiar enlace.
- Detecta IP LAN/hotspot activa del Mac.
- Añade diagnóstico `/api/mobile-beta/status`.
- Añade botón para limpiar caché/service worker móvil y recargar.
- Se deja claro que el QR es solo beta local; final será dominio/PWA/login.

## Proveedores / documentos / contabilidad futura
- Proveedores preparados con datos fiscales y financieros: NIF/CIF, dirección, CP, ciudad, registro sanitario, condiciones de pago, frecuencia, regla de vencimiento, forma de pago, IBAN y email contable.
- Añadidas tablas base:
  - `supplier_documents`
  - `supplier_document_reconciliations`
  - `supplier_payment_proposals`
  - `accounting_export_batches`
- Preparado flujo futuro: albarán → factura → conciliación → vencimiento → propuesta de pago → validación humana.
- Regla crítica mantenida: ningún pago se ejecuta automáticamente.

## Pruebas internas
- `python -m compileall backend/app`: OK.
- Import FastAPI: OK.
- Render Inicio / Operativa / Admin: HTTP 200.
- `/mobile-beta`: HTTP 200.
- `/mobile-beta/qr.png`: HTTP 200.
- `/api/mobile-beta/status`: OK.
- `/api/oido-alfi/audio-diagnostics`: OK.
- Migración de tablas documentales: OK.
- Guardado simulado de clave Deepgram desde Admin: OK.

## Limitación no verificable aquí
No puedo confirmar audio físico real desde iPhone/Mac ni llamada real a Deepgram sin una API key real. El paquete queda preparado para que el usuario pegue la key en Admin > IA y pruebe desde OÍDO ALFI.
