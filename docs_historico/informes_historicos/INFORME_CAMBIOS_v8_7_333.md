# System MAC · Informe cambios v8_7_333

## Cambio principal
Se añadió configuración de OpenAI desde la interfaz del sistema:

- Admin → Probar IA permite pegar `OPENAI_API_KEY` una sola vez.
- La clave se guarda localmente en `.env` de la raíz y `backend/.env`.
- La clave se activa inmediatamente en el proceso actual sin reiniciar.
- Al reiniciar, `DESBLOQUEAR_y_INICIAR.command` lee `.env` y deja OpenAI activo.
- La clave no se guarda en base de datos ni se muestra completa.

## Para qué sirve
Activa la capa IA para:

- OÍDO ALFI / Operativa rápida.
- Transcripción de voz configurada vía OpenAI.
- IA Recetas LAB para lectura/importación de recetas por texto, foto o voz cuando el proveedor esté disponible.

## Seguridad aplicada

- No se imprime la clave en pantalla.
- En el panel solo se ve `••••xxxx`.
- Los ficheros `.env` se escriben con permiso `600` cuando el sistema operativo lo permite.
- Se mantiene `CONFIGURAR_IA_OPENAI.command` como alternativa.
- Se añade opción de quitar la clave local desde Admin.

## Validaciones

- Compilación `backend/app`: OK.
- Importación app principal: OK.
- Estado IA sin clave: OK.
- Escritura de `.env` mediante función de Admin: OK.
- Limpieza de `.env` de prueba antes de empaquetar: OK.

## No tocado

- OCR de albaranes.
- Dictado antiguo.
- Recetas maestras.
- Lógica crítica de stock/inventario/pedidos.
