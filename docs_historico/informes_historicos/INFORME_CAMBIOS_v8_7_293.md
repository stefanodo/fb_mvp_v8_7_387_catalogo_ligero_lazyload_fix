# System MAC · Informe técnico v8_7_293

## Alcance aplicado

Se trabajó sobre la base `v8_7_292_audit_yield_fix_no_ocr_no_voice`.
No se modificó el motor OCR ni el dictado por voz.

## 1. Líquidos en albarán con cálculo interno en kg

Cambio aplicado:
- En carga manual de albaranes se añadieron unidades `l` y `ml`.
- Si el artículo trabaja internamente en `kg` o `g`, el sistema convierte:
  - `1 l = 1 kg`
  - `1 ml = 1 g`
- El precio de proveedor y el precio actual se normalizan contra la unidad base del artículo.
- Se añadió bloqueo para evitar validar litros/ml contra artículos de unidad `ud` o `manojo`.

Ejemplo esperado:
- Albarán: aceite 5 l a 6 €/l.
- Interno: 5 kg.
- Precio interno si el artículo está en kg: 6 €/kg.

## 2. Árbol duplicado congelado

Cambio aplicado:
- Se eliminó el backend duplicado `app/backend`.
- El único backend vivo queda en `backend/`.
- Los comandos dentro de `app/` redirigen al comando equivalente de la raíz.
- Se añadió `app/ARBOL_BACKEND_CONGELADO.txt` para documentar la decisión.
- Se limpiaron referencias activas de scripts de mantenimiento a bases duplicadas en `app/backend/runtime`.

Motivo:
- Evitar divergencia entre dos árboles de código y dos bases locales.
- Reducir riesgo de que el usuario arranque una versión vieja sin darse cuenta.

## 3. Producciones descuentan desde almacenes reales

Cambio aplicado:
- Al confirmar producción, las líneas `OUT` ya no se descuentan ciegamente solo del almacén elegido en la producción.
- El sistema busca stock real del artículo dentro del centro y descuenta por prioridad operativa:
  1. Cámara
  2. Almacén / Economato
  3. Cocina
  4. Almacén elegido para la producción
  5. Otros almacenes del centro
- Si no hay stock suficiente, el residual se registra como faltante visible para no ocultar negativos.
- Las líneas `IN` del elaborado terminado siguen entrando en el almacén elegido para la producción.

Prueba técnica ejecutada:
- Stock inicial: 2 kg en Cámara y 3 kg en Economato.
- Producción consume 4 kg.
- Resultado: salida de 2 kg desde Cámara y 2 kg desde Economato.

## 4. Inventario físico con conciliación automática

Cambio aplicado:
- Se añadió botón `Cerrar y conciliar stock`.
- Al cerrar, el sistema revisa solo líneas contadas (`is_checked=1`).
- Para cada línea contada, compara stock actual real en movements contra físico introducido.
- Crea movimiento automático de ajuste:
  - `ENTRADA` si el físico es mayor que el teórico real.
  - `SALIDA` si el físico es menor que el teórico real.
- Marca la sesión como `CLOSED`.
- Si la sesión ya está cerrada, no vuelve a conciliar para evitar duplicados.

Prueba técnica ejecutada:
- Stock inicial: 5 kg.
- Inventario físico contado: 4 kg.
- Resultado: ajuste de salida de 1 kg y stock final 4 kg.

## 5. Mano de obra en recetas

Cambio aplicado:
- Se unificó el bloque de tiempo y mano de obra en una sola tarjeta visual.
- Al cambiar cualquiera de estas variables, se actualiza en pantalla automáticamente:
  - Prep. min
  - Cocción min
  - Reposo min
  - Personas
  - €/h mano de obra
  - Raciones
  - Contingencia
  - Precio/manual/food cost
- La mano de obra sigue como análisis operativo y no modifica el food cost de materia prima.

Fórmula:

```text
coste_mano_obra = (prep + cocción + reposo) / 60 × personas × coste_hora
```

## Validaciones ejecutadas

- `python3 -m py_compile` sobre módulos modificados: OK.
- Importación de `app.main`: OK.
- Conversión `l -> kg`: OK.
- Conversión `ml -> g`: OK.
- Confirmación de producción multi-almacén: OK.
- Cierre de inventario con conciliación automática: OK.

## Pendientes no tocados

- OCR: no modificado por instrucción expresa.
- Dictado por voz: no modificado por instrucción expresa.
- No se hizo rediseño profundo del motor de categorías; solo se reforzó el flujo solicitado.
