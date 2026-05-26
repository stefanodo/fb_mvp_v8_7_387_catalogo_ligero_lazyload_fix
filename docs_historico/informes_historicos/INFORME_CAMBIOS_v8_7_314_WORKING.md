# INFORME CAMBIOS · v8_7_314_WORKING · Dashboard mensual dirección

## Estado
Cambios aplicados en carpeta de trabajo. ZIP no generado por instrucción del usuario.

## Objetivo
Añadir una vista mensual de dirección para evaluar inventarios cerrados por proveedor, rubro y local, con valor económico de pérdidas/sobrantes y recomendaciones operativas.

## Cambios aplicados

### 1. Servicio nuevo
Archivo: `backend/app/services/monthly_direction_dashboard_service.py`

Funciones:
- `build_monthly_direction_dashboard(center_id=None, year=None, month=None)`
- Agrupa diferencias de inventario cerrado por:
  - proveedor habitual,
  - rubro: Frescos, Secos, Congelados, Limpieza, Producciones, Sin clasificación, Otros,
  - local/centro.
- Calcula:
  - pérdidas €,
  - sobrantes €,
  - neto €,
  - líneas graves,
  - artículos sin proveedor,
  - artículos sin rubro claro,
  - mayores pérdidas,
  - mayores sobrantes,
  - recomendaciones.

### 2. Inicio / Dashboard
Archivo: `backend/app/templates/sections/inicio.html`

Añadido bloque:
`Dashboard mensual de dirección · inventario`

Muestra:
- periodo mensual,
- pérdidas,
- sobrantes,
- neto,
- diferencias graves,
- tabla por proveedor alfabética,
- tabla por rubro alfabética,
- locales con mayor riesgo,
- mayores pérdidas,
- evaluación recomendada.

### 3. Integración app
Archivo: `backend/app/main.py`

Añadido contexto `direction_monthly` para el template principal.

### 4. Estilos
Archivo: `backend/app/static/style.css`

Añadidos estilos compactos para tablas directivas y vista móvil.

## Validaciones realizadas
- `python -m compileall -q backend/app`: OK
- `init_db()` sobre runtime temporal: OK
- importación `build_monthly_direction_dashboard`: OK
- importación app principal: OK
- TestClient GET `/`: HTTP 200 OK
- Texto `Dashboard mensual` presente en HTML: OK

## No tocado
- OCR.
- Dictado/voz.
- Confirmación/envío automático de pedidos.
- Lógica de stock por fuera de movimientos.

## Observaciones
El informe mensual lee inventarios cerrados existentes. Si no hay inventarios cerrados en el periodo, muestra mensaje informativo y no inventa datos.
