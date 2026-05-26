# INFORME CAMBIOS v8_7_347 · OÍDO ALFI STT servidor + diagnóstico voz

## Objetivo
Endurecer la comprensión de voz en ordenador y móvil usando una capa extra de transcripción en servidor, sin depender solo de Web Speech Recognition/Safari.

## Cambios aplicados
- OÍDO ALFI usa endpoint `/api/oido-alfi/transcribe-audio` con STT servidor vía OpenAI cuando hay `OPENAI_API_KEY`.
- Eliminada dependencia obligatoria del SDK Python de OpenAI para transcribir: se usa multipart HTTPS interno para evitar fallos por paquete no instalado.
- Forzado operativo a español España (`language=es`, prompt español, limpieza anti-inglés).
- Si el navegador bloquea grabación directa, el sistema informa y mantiene fallback por micrófono del teclado + botón Ejecutar.
- Nuevo endpoint `/api/oido-alfi/audio-diagnostics` para mostrar estado de STT servidor, modelo, idioma y aviso de navegador.
- Pantalla Operativa/OÍDO ALFI muestra diagnóstico visible de voz: grabación navegador y STT servidor.
- Corrección de parser: frases tipo “waste tomatoes four kilos bad condition” o “merma de tomate cuatro kilos mal estado” ya no interpretan “mal estado” como artículo; conservan TOMATE como entidad.

## Pruebas internas
- `python3 -m compileall backend/app`: OK.
- `node --check backend/app/static/js/operativa.js`: OK.
- `node --check backend/app/static/js/voice_assistant.js`: OK.
- Import FastAPI: OK.
- Simulacro texto/voz normalizada:
  - `production of pico gallo` → PRODUCCIÓN / PICO DE GALLO.
  - `waste tomatoes four kilos bad condition` → MERMA / TOMATE / 4 kg.
  - `mima de tomate cuatro kilos` → MERMA / TOMATE / 4 kg.
  - `cuatro huevos rotos` → MERMA / HUEVOS / 4 ud.
  - `faltan puerros` → PEDIDO / PUERRO / falta cantidad.
  - `qué proveedor vende bacalao` → CONSULTA_PROVEEDOR.

## Limitación verificada
No puedo confirmar audio físico real de iPhone/Mac desde este entorno. El build queda preparado para: grabación directa si navegador lo permite, STT servidor si hay OpenAI configurado, y fallback estable por dictado del teclado.
