# System MAC v8_7_353

Cambios aplicados:
- OÍDO ALFI móvil simplificado con tres vistas: Dictar, Resultado y Colas.
- Diagnóstico IA/voz plegado para no ensuciar la pantalla.
- Nuevo modo “Prueba voz 5 s” que transcribe y prelee sin crear pedidos, mermas ni producciones.
- Respuesta hablada recortada para evitar cortes largos.
- Pantalla IA técnica deja de mostrar JSON crudo como salida principal; ahora muestra respuesta humana y diagnóstico plegado.
- Acceso móvil beta añade aviso claro sobre HTTP/Solo HTTPS en Safari.

Reglas mantenidas:
- La IA no confirma stock ni cierra pedidos/producciones/mermas.
- Deepgram se usa como STT principal si hay key; OpenAI queda para comprensión y fallback.
