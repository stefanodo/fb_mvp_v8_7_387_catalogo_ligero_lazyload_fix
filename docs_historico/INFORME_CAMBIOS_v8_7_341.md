# INFORME CAMBIOS · v8_7_341

## Objetivo
Endurecer el núcleo de OÍDO ALFI/System MAC para que la voz, el texto dictado, la comprensión de intención y las sugerencias operativas sean más robustas sin confirmar acciones críticas.

## Cambios aplicados
- Normalización previa más fuerte para dictados incompletos o mal transcritos.
- Diccionario gastronómico ampliado: pico de gallo, tomate/tomates/tom., merma/mima, preparar/hacer/producir, pedir/encargar/solicitar y errores comunes de iPhone/Safari.
- El orquestador usa intención pública obligatoria: PRODUCCIÓN, MERMA, PEDIDO, CONSULTA_STOCK, CONSULTA_PROVEEDOR, RECETA_IA, ALBARÁN_IA o NO_ENTENDIDO.
- Si entiende producción/merma/pedido con confianza suficiente, crea propuesta/borrador pendiente; no confirma stock ni cierra operaciones.
- Si la transcripción es rara, sin producto claro o confianza demasiado baja, pide confirmación antes de crear nada.
- Producciones tipo “preparar pico de gallo”, “hacer producción pico gallo” y “producción de pico” normalizan a PRODUCCIÓN de PICO DE GALLO.
- Mermas tipo “hay una merma de tomates”, “tirar tomates mal estado” o “mima de tomates” normalizan a MERMA de TOMATE.
- Añadido endpoint `/api/oido-alfi/suggest` para prelectura/sugerencias sin ejecutar.
- El panel OÍDO ALFI muestra intención detectada, texto limpio y accesos sugeridos al módulo correcto.
- La transcripción OpenAI recibe prompt STT específico de cocina/restaurante para proteger términos como pico de gallo, tomate, merma, producción, pedido, albarán y proveedor.

## Seguridad operativa
- No valida albaranes.
- No descuenta stock desde merma hasta confirmación humana.
- No confirma producciones.
- No envía pedidos.
- No modifica recetas maestras.
- Cualquier acción dudosa queda en confirmación/revisión.

## Pruebas internas realizadas
- `python3 -m compileall backend/app`: OK.
- Import de `app.main`: OK.
- Endpoint `/api/oido-alfi/command`: OK.
- Endpoint `/api/oido-alfi/suggest`: OK.
- Render HTTP 200: Inicio, Mermas y Operativa.
- Casos probados:
  - “quiero hacer una producción de pico de gallo” → PRODUCCIÓN + borrador pendiente.
  - “hacer producción pico gallo” → PRODUCCIÓN + borrador pendiente.
  - “preparar pico de gallo” → PRODUCCIÓN + borrador pendiente.
  - “producción de pico” → PRODUCCIÓN + borrador pendiente.
  - “hay una merma de tomates” → MERMA + borrador pendiente, sin descontar stock.
  - “tirar tomates mal estado” → MERMA + borrador pendiente, sin descontar stock.
  - “producción rara zzx” → pide confirmación, no crea borrador.

## No confirmado en este entorno
- Audio real de iPhone/Mac con micrófono físico. El código queda preparado con grabación directa cuando el navegador lo permita y fallback al micrófono del teclado/campo de texto.
