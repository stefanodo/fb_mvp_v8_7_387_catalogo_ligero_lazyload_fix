# INFORME CAMBIOS · v8_7_337 · OÍDO ALFI audio OpenAI + fallback iPhone

## Objetivo
Integrar el modo híbrido de voz para OÍDO ALFI:
- ordenador/Mac: grabación de audio desde el navegador y transcripción con OpenAI;
- iPhone/Safari: usar el mismo botón si el navegador permite micrófono; si Safari/PWA lo bloquea, usar el micrófono del teclado dentro del campo de texto;
- mantener respuesta por voz del navegador cuando esté disponible;
- mantener límites: no confirmar acciones críticas sin revisión humana.

## Cambios aplicados

### Backend
- Nuevo endpoint: `POST /api/oido-alfi/transcribe-audio`.
- Nueva función: `transcribe_oido_alfi_audio()` en `backend/app/services/ai_orchestrator_service.py`.
- El audio se guarda en archivo temporal, se manda a OpenAI STT y se elimina después.
- Modelo configurable con `OIDO_ALFI_STT_MODEL`, por defecto `gpt-4o-transcribe`.
- Tamaño máximo configurable con `OIDO_ALFI_AUDIO_MAX_MB`, por defecto 25 MB.
- Si no hay `OPENAI_API_KEY`, devuelve aviso claro sin romper el panel.

### Frontend
- `OÍDO ALFI` cambia de dictado puro a grabación de audio cuando el navegador lo permite.
- Botón actualizado: `Grabar voz` / `Parar y enviar`.
- Si `MediaRecorder/getUserMedia` falla, intenta dictado del navegador si existe.
- Si Safari/iPhone bloquea micrófono directo, informa que se use el micrófono del teclado en el campo.
- La transcripción se envía automáticamente al orquestador `/api/oido-alfi/command`.

## Reglas de seguridad mantenidas
- No valida albaranes/facturas.
- No mueve stock definitivo.
- No confirma mermas.
- No confirma producciones.
- No cierra pedidos.
- No modifica recetas maestras.
- Solo crea propuestas/borradores o consultas.

## Validaciones
- Compilación Python: OK.
- Importación FastAPI: OK.
- Endpoint `/api/oido-alfi/capabilities`: OK.
- Endpoint `/api/oido-alfi/transcribe-audio` sin clave: responde fallback controlado.
- Render Inicio con OÍDO ALFI: OK.
- Validación JS `voice_assistant.js`: OK.

## Limitación conocida
No se puede confirmar desde este entorno si Safari/iPhone permite `getUserMedia` en tu caso concreto por permisos/red/PWA. Por eso queda fallback explícito: micrófono del teclado dentro del campo de texto.
