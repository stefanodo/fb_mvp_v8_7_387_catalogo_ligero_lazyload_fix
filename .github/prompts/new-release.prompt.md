---
name: "Nueva Release System MAC"
description: "Crea una nueva release: actualiza BUILD_ID en core.py, VERSION_BUILD.txt, y genera el INFORME_CAMBIOS correspondiente."
argument-hint: "NNN descripcion_corta — p.ej. 388 stock_alertas_criticas"
agent: "agent"
---

Ejecuta el proceso completo de nueva release para System MAC F&B MVP.

## Argumento esperado
`$ARGUMENTS` debe seguir el formato: `NNN descripcion_corta`
- `NNN` = número de build (ej. `388`)
- `descripcion_corta` = slug con guiones bajos (ej. `stock_alertas_criticas`)

Si el argumento está vacío, extrae el siguiente número a partir del `BUILD_ID` actual en [core.py](../../backend/app/core.py) y pide la descripción.

## Pasos a ejecutar

### 1. Leer estado actual
- Leer `BUILD_ID` en [backend/app/core.py](../../backend/app/core.py) — línea `BUILD_ID = "v8_7_..."`.
- Leer [VERSION_BUILD.txt](../../VERSION_BUILD.txt).
- Confirmar que el número nuevo es mayor que el actual.

### 2. Calcular nuevo BUILD_ID
Formato: `v8_7_NNN_descripcion_corta`

### 3. Actualizar BUILD_ID en core.py
Cambiar únicamente la línea:
```python
BUILD_ID = "v8_7_NNN_descripcion_corta"
```

### 4. Actualizar VERSION_BUILD.txt
Reemplazar el contenido con exactamente:
```
v8_7_NNN_descripcion_corta
```

### 5. Crear INFORME_CAMBIOS_v8_7_NNN.md en la raíz
Usar esta plantilla — rellenar las secciones con los cambios reales de la sesión:

```markdown
# INFORME CAMBIOS v8_7_NNN · <Título legible>

## Objetivo
<Descripción del objetivo de esta release.>

## Cambios realizados

### Backend
- 

### Templates / Frontend
- 

### Nuevas tablas o columnas DB
- Ninguna / <lista>

### Endpoints añadidos o modificados
- Ninguno / <lista>

## Archivos modificados
- backend/app/core.py — BUILD_ID bump
- VERSION_BUILD.txt
- <otros archivos>

## Compatibilidad
- Sin migraciones destructivas.
- Compatible con DB existente en ~/Documents/F&B_MAC_RUNTIME/.
```

### 6. Confirmar
Mostrar un resumen con:
- BUILD_ID anterior → nuevo
- Archivos tocados
