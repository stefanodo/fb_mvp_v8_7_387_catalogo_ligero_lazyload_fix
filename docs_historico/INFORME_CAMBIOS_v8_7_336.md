# System MAC · v8_7_336 · OÍDO ALFI IA orquestadora

## Objetivo
Empezar la integración real de OÍDO ALFI como capa central de IA dentro del sistema, no solo como clave OpenAI ni como botón decorativo.

## Cambios aplicados
- Nuevo servicio `backend/app/services/ai_orchestrator_service.py`.
- Nuevo router `backend/app/routers/ai_system.py`.
- Nuevo panel directo `/ai-system/ui`.
- Nuevos endpoints:
  - `GET /api/oido-alfi/capabilities`
  - `POST /api/oido-alfi/command`
  - `POST /api/oido-alfi/document`
- OÍDO ALFI ahora pasa primero por una capa central que decide:
  - consulta segura,
  - apertura de módulo,
  - creación de propuesta pendiente,
  - lectura documental pendiente de revisión,
  - o aclaración si no hay seguridad.

## Límites programados
- La IA no valida albaranes/facturas.
- La IA no mueve stock definitivo.
- La IA no confirma mermas, producciones ni pedidos.
- La IA no modifica recetas maestras sin revisión humana.
- La IA puede crear borradores/propuestas pendientes y guardar documentos en revisión.

## Módulos conectados en esta primera capa
- Stock: consulta y apertura.
- Proveedores: consulta de contacto, reparto y mínimos.
- Pedidos: propuesta pendiente.
- Producciones: propuesta pendiente.
- Mermas: propuesta pendiente.
- Recetas IA: apertura y borradores.
- Albaranes/facturas: recepción de documento y cola de revisión.
- TPV: preparación como módulo de aprendizaje, sin impacto automático no validado.
- Control/Dashboard: apertura de consulta.

## Pendiente posterior
- Conectar lectura de PDF multipágina a OCR/document AI supervisado.
- Mostrar listado visual de `ai_document_reviews` dentro de Admin/Laboratorio.
- Convertir extracción de albarán/factura en líneas OCR revisables del módulo Albaranes.
- Convertir lectura de receta en borrador IA completo cuando haya confianza suficiente.
- Mejorar respuesta hablada con confirmaciones cortas por módulo.
