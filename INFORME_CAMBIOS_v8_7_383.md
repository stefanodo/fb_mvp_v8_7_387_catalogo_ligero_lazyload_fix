# System MAC · v8_7_383 · Finanzas ejecutivas / ROIC / Capital

## Cambio principal
Se añade una nueva pestaña `Finanzas` orientada a dueño, CEO, CFO o inversor.

La pantalla sintetiza por local y por grupo:

- ventas del periodo;
- beneficio bruto;
- EBITDA diario estimado;
- capital propio;
- capital financiado;
- tipo de interés anual del capital financiado, por defecto 5%;
- coste financiero diario;
- capital invertido;
- rendimiento del capital / ROIC anualizado estimado;
- pasivo laboral estimado;
- necesidad de caja a 30 días;
- cobertura de caja;
- causa probable de bajada/subida de rendimiento.

## Regla de lectura ejecutiva
El bloque separa beneficio absoluto de rendimiento del capital.

Ejemplo conceptual:

- un local puede ganar más euros absolutos y tener menor ROIC;
- otro local puede ganar menos, pero rentar mejor sobre el capital invertido;
- la pantalla ayuda a identificar por qué: food cost, coste laboral, financiación, pasivo laboral, merma, ventas o costes fijos.

## Seguridad
- No modifica stock.
- No modifica recetas.
- No modifica precios.
- No ejecuta acciones automáticas.
- Los campos de capital/pasivo/gastos son hipótesis explícitas hasta integrar contabilidad real.

## Archivos tocados
- `backend/app/services/executive_finance_dashboard_service.py`
- `backend/app/main.py`
- `backend/app/templates/index.html`
- `backend/app/templates/sections/finanzas.html`
- `backend/app/static/style.css`
- `backend/app/core.py`
- `app/VERSION_BUILD.txt`

## Validación rápida
- Python compileall OK.
- JS principales OK.
- `/` OK.
- `/?page=finanzas` OK.
- `/?page=finanzas` con hipótesis financieras OK.
