# INFORME CAMBIOS · v8_7_326 · OÍDO ALFI + UI compacta

## Objetivo
Aplicar el bloque de correcciones visuales y operativas solicitado sin tocar OCR ni el dictado antiguo crítico del sistema.

## Cambios aplicados

### 1. OÍDO ALFI
- Se recupera el botón flotante, pero renombrado como **OÍDO ALFI**.
- El botón ahora es movible con ratón o dedo y guarda posición localmente en el navegador.
- Panel con pestañas:
  - Operar: pedidos, mermas, producciones, stock, inventario.
  - Consultar: stock, qué pedir, margen, ventas, control de mermas, dashboard.
  - IA / Recetas: accesos a receta por texto, foto, voz y borradores IA.
  - Ideas: ejemplos de uso operativo.
- Puede responder por voz mediante síntesis del navegador si está disponible.
- No confirma automáticamente pedidos, stock, producciones, mermas ni recetas maestras.

### 2. Inicio / dashboard
- Los bloques de dirección se compactan.
- Los paneles secundarios quedan plegables con botón “Ver detalle / Ocultar detalle”.
- Se reduce la sensación de tres pantallas de información cuando no hay datos.

### 3. Pedidos
- El bloque superior de creación queda en una fila armoniosa cuando hay ancho suficiente:
  Local / Responsable / Nota / Nuevo pedido.
- En pantallas pequeñas se apila ordenadamente.

### 4. Operativa y Mermas
- Reducción visual de tarjetas grandes.
- Menos blanco invasivo.
- Colores más alineados con System MAC: oscuro, antracita y acentos dorados.
- Inputs y paneles más integrados en la paleta principal.

### 5. Recetas IA LAB
- La pantalla de laboratorio IA deja de verse como una página blanca suelta.
- Ahora tiene layout propio profesional con navegación a Inicio, Laboratorio, IA Recetas y Borradores.
- Mantiene seguridad: crea borradores, no modifica recetas maestras salvo activación explícita.

### 6. Limpieza raíz
- Informes anteriores de v8_7_324 y v8_7_325 movidos a docs_historico/informes_historicos.
- En raíz queda solo la documentación útil de la versión actual y comandos esenciales.

## Validaciones realizadas
- Compilación Python backend/app: OK.
- Importación app principal: OK.
- Render Inicio: OK.
- Render Pedidos: OK.
- Render Operativa: OK.
- Render Mermas: OK.
- Render Recetas IA LAB: OK.
- OÍDO ALFI incluido en pantallas principales: OK.

## No tocado
- OCR de albaranes.
- Dictado/voz antiguo de mermas fuera de ajustes visuales.
- Conversión real de recetas IA a receta maestra.
- Lógica de stock/inventario ya validada.
