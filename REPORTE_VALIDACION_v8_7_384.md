# Validación v8_7_384

Validación técnica realizada:
- Python compileall OK.
- Importación de app OK.
- Render de Finanzas OK.
- Ruta `/ ?page=finanzas` comprobada.
- Servicio financiero ejecutivo devuelve `ceo_kpis`, matriz por local y KPIs estratégicos.

Pendiente funcional futuro:
- Integrar contabilidad real, nóminas, deuda real y pasivo laboral real por local.
- Separar permisos por rol para que Finanzas sea visible solo a dueño/CEO/CFO/inversor.
- Añadir comparativas históricas reales mes contra mes y año contra año cuando haya ventas normalizadas suficientes.
