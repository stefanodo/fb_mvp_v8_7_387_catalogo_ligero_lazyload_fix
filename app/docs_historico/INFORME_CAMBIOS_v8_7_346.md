# INFORME CAMBIOS v8_7_346 · OÍDO ALFI central práctico

## Objetivo
Hacer OÍDO ALFI más práctico y usable desde una pantalla clara, no solo como botón flotante, reforzando texto, dictado, respuesta hablada opcional y comprensión operativa.

## Cambios aplicados
- Pantalla `Operativa / OÍDO ALFI` rediseñada como panel central.
- Campo grande `Comando operativo` para escribir o dictar con micrófono del teclado.
- Botón `Ejecutar` para lanzar la acción segura.
- Botón `Prelectura` para revisar intención antes de ejecutar.
- Interruptor `Responder con voz` usando síntesis del navegador si está disponible.
- Botón `Grabar si está disponible` con fallback claro a dictado del teclado si Safari/iPhone bloquea micrófono directo.
- Botones rápidos por módulo: Producción, Merma, Pedido, Stock, Proveedor, Receta IA y Albarán IA.
- Resultado en texto con intención, texto limpio, elemento, cantidad, riesgo, confianza, campos faltantes y enlaces al módulo correcto.
- Panel flotante OÍDO ALFI actualizado con campo multilínea y acceso directo a la pantalla central.
- Corrección de consulta de stock: frases como `cuánto tomate hay en stock` ya no interpretan `stock` como insumo.

## Seguridad operativa
- Producciones, mermas y pedidos se crean solo como borradores/propuestas pendientes.
- No se confirma stock automáticamente.
- No se envían pedidos.
- No se validan albaranes/facturas.
- No se modifican recetas maestras.

## Archivos tocados
- `backend/app/templates/sections/operativa.html`
- `backend/app/static/js/operativa.js`
- `backend/app/static/css/operativa.css`
- `backend/app/templates/partials/voice_assistant.html`
- `backend/app/static/css/voice_assistant.css`
- `backend/app/services/oido_alfi_service.py`
- `backend/app/services/ai_orchestrator_service.py`

## Pruebas internas
- `python3 -m compileall -q backend/app`: OK.
- `node --check backend/app/static/js/operativa.js`: OK.
- `node --check backend/app/static/js/voice_assistant.js`: OK.
- Render HTTP 200: Inicio, Operativa, Pedidos, Producciones, Inventario.
- `/api/oido-alfi/suggest`: OK.
- `/api/oido-alfi/command`: OK.

## Simulacro comandos
- `quiero hacer una producción de pico de gallo` → PRODUCCIÓN, falta cantidad/lote/raciones.
- `hacer producción pico gallo` → PRODUCCIÓN, falta cantidad.
- `preparar pico de gallo` → PRODUCCIÓN, falta cantidad.
- `production of pico gallo` → PRODUCCIÓN corregido a español.
- `hay una merma de tomates` → MERMA, falta cantidad.
- `mima de tomate cuatro kilos por mal estado` → MERMA 4 kg TOMATE.
- `cuatro huevos rotos` → MERMA 4 ud HUEVOS.
- `faltan puerros` → PEDIDO, falta cantidad.
- `pide dos kilos de tomate` → PEDIDO 2 kg TOMATE.
- `cuánto tomate hay en stock` → consulta stock de TOMATE, no de `stock`.
- `de qué proveedor es bacalao` → CONSULTA_PROVEEDOR.
- `leer albarán por foto` → ALBARÁN_IA, abre flujo revisable.
- `importar receta por foto` → RECETA_IA, abre flujo revisable.

## Limitación no verificable aquí
No puedo confirmar audio físico real de iPhone/Mac desde este entorno. El sistema queda preparado con campo de texto + dictado del teclado como vía prioritaria y grabación directa solo cuando el navegador lo permita.
