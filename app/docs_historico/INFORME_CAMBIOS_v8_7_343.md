# System MAC · v8_7_343 · OÍDO ALFI español estricto

Cambios aplicados:
- STT operativo fuerza `language=es` y añade prompt explícito de español de España.
- Se bloquea el sesgo de OpenAI a inglés en transcripción y comprensión: production/waste/order/tomato se normalizan a producción/merma/pedido/tomate cuando el contexto es cocina.
- El intérprete de Operativa exige campos textuales en español y prohíbe devolver productos traducidos al inglés.
- OÍDO ALFI normaliza el texto transcrito antes de ejecutar la acción real.
- Recetas IA por voz también fuerza español en transcripción y limpieza.
- `.env.example` y configuración desde Admin guardan banderas de idioma español.

Blindaje:
- No se inventan cantidades, unidades ni responsables.
- Si falta dato operativo, se mantiene borrador/propuesta pendiente.
- No se confirma stock ni receta maestra sin humano.
