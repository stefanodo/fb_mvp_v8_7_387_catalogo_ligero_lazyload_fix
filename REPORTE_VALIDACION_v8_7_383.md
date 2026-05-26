# Validación v8_7_383

## Alcance validado
Se validó que la nueva pestaña financiera carga sin romper navegación general.

## Tests ejecutados
- `python3 -m compileall app`
- `node --check app/static/js/core.js`
- `node --check app/static/js/laboratory.js`
- FastAPI TestClient:
  - `/`
  - `/?page=finanzas`
  - `/?page=finanzas&own_capital=100000&financed_capital=50000&interest_rate=0.05&labor_cost_daily=1000&fixed_opex_daily=400&labor_liability=25000&cash_available=20000`
  - `/?page=inicio`
  - `/?page=stock`
  - `/?page=laboratorio`

## Limitaciones honestas
- La pestaña calcula con ventas normalizadas si existen; si no hay TPV/importación real, muestra estado preparado y no inventa ventas.
- Las variables financieras por local todavía no se guardan en tabla propia; en esta versión son hipótesis de simulador introducidas por pantalla.
- El acceso se marca como restringido en UI, pero el sistema de roles/login real sigue siendo pendiente futuro.

## Próximo paso recomendado
Crear tabla de configuración financiera por local:

- capital propio;
- capital financiado;
- tipo de interés;
- pasivo laboral;
- costes fijos diarios;
- coste laboral diario;
- caja disponible;
- objetivos de ROIC/EBITDA.

Después conectar con contabilidad real, nóminas, TPV y facturas.
