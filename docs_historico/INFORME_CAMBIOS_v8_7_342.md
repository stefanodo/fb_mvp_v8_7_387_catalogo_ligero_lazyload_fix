# INFORME CAMBIOS · v8_7_342_recetas_ia_heic_iphone_fix

## Corrección aplicada

### Recetas IA · Importar por foto
- Se corrige el error observado en Safari/iPhone/Mac: `{"detail":"Formato no permitido: .heic"}`.
- El importador de foto de Recetas IA ahora acepta:
  - JPG / JPEG
  - PNG
  - WEBP
  - HEIC
  - HEIF
- Las imágenes se normalizan a JPG antes de enviarse al lector IA.
- Para HEIC/HEIF se reutiliza el normalizador común del sistema, con conversión mediante `sips` en Mac cuando Pillow no pueda abrir el archivo.
- La pantalla de subida informa explícitamente que acepta HEIC/HEIF de iPhone.

### Blindaje UI
- Si la imagen no se puede leer o convertir, ya no se muestra JSON crudo en la pantalla.
- Se renderiza una tarjeta HTML de error controlado con botón para reintentar.
- No se crea borrador vacío si falla la importación de imagen.

## Pruebas internas
- `python3 -m compileall -q backend/app`: OK.
- GET `/recipe-ai/ui/import-image`: HTTP 200 y formulario con HEIC/HEIF aceptado.
- POST `/recipe-ai/ui/import-image` con HEIC inválido: HTTP 400 controlado en HTML, no JSON crudo.
- POST `/recipe-ai/import/image` con JPG válido: HTTP 200 y flujo de borrador operativo.
- Base de datos restaurada después de prueba para no empaquetar borradores de test.

## No confirmado
- No puedo confirmar conversión real de una foto HEIC física de iPhone dentro de este entorno Linux. En Mac el sistema usa `sips`, que es la vía prevista para HEIC/HEIF.
