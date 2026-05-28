from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.core import db
from app.services.daily_business_dashboard_service import build_daily_business_dashboard


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _pct(n: float, d: float) -> float:
    return (n / d * 100.0) if d else 0.0


def _norm_date(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value[:10]).date().isoformat()
    except Exception:
        return None


def _period(start_date: str | None, end_date: str | None) -> tuple[str, str, str]:
    today = date.today().isoformat()
    start = _norm_date(start_date)
    end = _norm_date(end_date)
    if not start and not end:
        start = end = today
    elif start and not end:
        end = start
    elif end and not start:
        start = end
    if start and end and start > end:
        start, end = end, start
    label = start if start == end else f"{start} → {end}"
    return start or today, end or today, label


def _days_between(start: str, end: str) -> int:
    try:
        a = datetime.fromisoformat(start[:10]).date()
        b = datetime.fromisoformat(end[:10]).date()
        return max(1, (b - a).days + 1)
    except Exception:
        return 1


def _center_rows() -> list[dict[str, Any]]:
    conn = db()
    try:
        cur = conn.cursor()
        rows = cur.execute("SELECT id,name FROM centers ORDER BY LOWER(name)").fetchall()
        return [{"id": int(r["id"] or 0), "name": r["name"] or f"Local {r['id']}"} for r in rows]
    finally:
        conn.close()


def _status_for(row: dict[str, Any]) -> str:
    if not row.get("has_sales"):
        return "sin_ventas"
    if row.get("net_result_daily", 0.0) < 0 or row.get("roic_annualized_pct", 0.0) < 3:
        return "critico"
    if (
        row.get("roic_annualized_pct", 0.0) < 7
        or row.get("food_cost_pct", 0.0) > 35
        or row.get("labor_cost_pct", 0.0) > 35
        or row.get("prime_cost_pct", 0.0) > 65
        or row.get("cash_coverage_days", 0.0) < 15
    ):
        return "atencion"
    return "ok"


def _decision_label(row: dict[str, Any]) -> str:
    if not row.get("has_sales"):
        return "Cargar ventas para medir"
    if row.get("net_result_daily", 0.0) < 0:
        return "Intervenir margen/costes"
    if row.get("roic_annualized_pct", 0.0) < 3:
        return "Revisar capital invertido"
    if row.get("prime_cost_pct", 0.0) > 65:
        return "Reducir prime cost"
    if row.get("cash_coverage_days", 0.0) < 15:
        return "Proteger liquidez"
    if row.get("roic_annualized_pct", 0.0) >= 10 and row.get("net_margin_pct", 0.0) >= 8:
        return "Modelo a potenciar"
    return "Vigilar evolución"


def _diagnosis(row: dict[str, Any]) -> list[str]:
    out: list[str] = []
    if not row.get("has_sales"):
        out.append("Sin ventas normalizadas en el periodo: no se calcula rendimiento real.")
        return out
    if row.get("food_cost_pct", 0.0) > 35:
        out.append("Food cost alto: revisar subidas de proveedor, gramajes, mermas y precio de venta.")
    if row.get("labor_cost_pct", 0.0) > 35:
        out.append("Coste laboral alto frente a ventas: revisar turnos, productividad y pasivo laboral.")
    if row.get("prime_cost_pct", 0.0) > 65:
        out.append("Prime cost elevado: producto + personal consumen demasiado margen operativo.")
    if row.get("waste_pct_sales", 0.0) > 2:
        out.append("Mermas elevadas: analizar productos, responsables, caducidad y producción sobrante.")
    if row.get("finance_cost_daily", 0.0) > max(1.0, row.get("ebitda_daily", 0.0) * 0.1):
        out.append("Coste financiero relevante: revisar deuda, interés o estructura de capital.")
    if row.get("cash_coverage_days", 0.0) < 15 and row.get("cash_available", 0.0) > 0:
        out.append("Cobertura de caja baja: revisar pagos próximos, compras, financiación y cobros.")
    if row.get("roic_annualized_pct", 0.0) < 5:
        out.append("Rendimiento del capital bajo: comparar inversión, ventas, margen y estructura de costes.")
    if not out:
        out.append("Estructura sana en simulación: mantener control de margen, compras, rotación y capital.")
    return out[:5]


def _ceo_kpis(portfolio: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    sales = portfolio.get("sales", 0.0)
    invested = portfolio.get("invested_capital", 0.0)
    financed = portfolio.get("financed_capital", 0.0)
    own = portfolio.get("own_capital", 0.0)
    labor_liability = portfolio.get("labor_liability", 0.0)
    critical = sum(1 for r in rows if r.get("status") == "critico")
    attention = sum(1 for r in rows if r.get("status") == "atencion")
    best = max((r for r in rows if r.get("has_sales")), key=lambda r: r.get("roic_annualized_pct", -999), default=None)
    worst = min((r for r in rows if r.get("has_sales")), key=lambda r: r.get("roic_annualized_pct", 999), default=None)
    return {
        "quick": [
            {"label": "Ventas grupo", "value": sales, "type": "money", "hint": "Volumen del periodo visible."},
            {"label": "EBITDA operativo/día", "value": portfolio.get("ebitda_daily", 0.0), "type": "money", "hint": "Resultado operativo antes de financiación."},
            {"label": "Resultado neto est./día", "value": portfolio.get("net_result_daily", 0.0), "type": "money", "hint": "EBITDA operativo menos coste financiero."},
            {"label": "ROIC anualizado", "value": portfolio.get("roic_annualized_pct", 0.0), "type": "pct", "hint": "Retorno estimado sobre capital invertido."},
            {"label": "Prime cost", "value": portfolio.get("prime_cost_pct", 0.0), "type": "pct", "hint": "Producto + personal / ventas."},
            {"label": "Caja cubierta", "value": portfolio.get("cash_coverage_days", 0.0), "type": "days", "hint": "Días de operación cubiertos con caja disponible."},
        ],
        "strategic": [
            {"label": "Capital invertido", "value": invested, "type": "money", "hint": "Fondos propios + financiados."},
            {"label": "Fondos propios", "value": own, "type": "money", "hint": "Aporte propio informado."},
            {"label": "Capital financiado", "value": financed, "type": "money", "hint": "Capital ajeno informado."},
            {"label": "Deuda / capital", "value": _pct(financed, invested), "type": "pct", "hint": "Peso de financiación externa."},
            {"label": "Pasivo laboral", "value": labor_liability, "type": "money", "hint": "Riesgo laboral informado."},
            {"label": "Pasivo laboral / EBITDA anual", "value": portfolio.get("labor_liability_ratio_pct", 0.0), "type": "pct", "hint": "Riesgo laboral frente a capacidad operativa."},
        ],
        "board": [
            {"label": "Locales críticos", "value": critical, "type": "int", "hint": "Requieren explicación ejecutiva."},
            {"label": "Locales en atención", "value": attention, "type": "int", "hint": "Revisar antes de cierre."},
            {"label": "Mejor ROIC", "value": (best or {}).get("center_name", "—"), "type": "text", "hint": f"{(best or {}).get('roic_annualized_pct', 0):.1f}%" if best else "Sin ventas."},
            {"label": "Peor ROIC", "value": (worst or {}).get("center_name", "—"), "type": "text", "hint": f"{(worst or {}).get('roic_annualized_pct', 0):.1f}%" if worst else "Sin ventas."},
        ],
    }


def _portfolio_recommendation(portfolio: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    if not rows or not any(r.get("has_sales") for r in rows):
        return "Cargar ventas normalizadas por local para que la pestaña pueda comparar rendimiento real."
    if portfolio.get("net_result_daily", 0.0) < 0:
        return "Prioridad CEO: proteger resultado neto. Revisar food cost, personal, gastos fijos y financiación."
    if portfolio.get("roic_annualized_pct", 0.0) < 5:
        return "Prioridad CEO: revisar capital invertido frente a rentabilidad. Identificar locales con alto beneficio absoluto pero bajo retorno."
    if portfolio.get("prime_cost_pct", 0.0) > 65:
        return "Prioridad CEO: reducir prime cost. Producto y personal están absorbiendo demasiada venta."
    if portfolio.get("cash_coverage_days", 0.0) < 15 and portfolio.get("cash_available", 0.0) > 0:
        return "Prioridad CEO: reforzar liquidez y calendario de pagos."
    return "Prioridad CEO: escalar prácticas de los locales con mejor ROIC y vigilar subidas de proveedores/pasivo laboral."


def build_executive_finance_dashboard(
    center_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    own_capital: float = 0.0,
    financed_capital: float = 0.0,
    interest_rate: float = 0.05,
    labor_liability: float = 0.0,
    labor_cost_daily: float = 0.0,
    fixed_opex_daily: float = 0.0,
    cash_available: float = 0.0,
) -> dict[str, Any]:
    """Executive finance scorecard: CEO KPIs, EBITDA, ROIC and capital structure.

    The screen is a decision layer. It uses real normalized operating data when present,
    but capital, labor liability and fixed opex remain explicit simulator inputs until
    accounting/payroll modules exist.
    """
    start, end, label = _period(start_date, end_date)
    days = _days_between(start, end)
    centers = _center_rows()
    if center_id:
        centers = [c for c in centers if int(c["id"]) == int(center_id)]
    active_centers = max(1, len(centers))

    own_total = max(0.0, _f(own_capital))
    financed_total = max(0.0, _f(financed_capital))
    labor_liability_total = max(0.0, _f(labor_liability))
    labor_daily_total = max(0.0, _f(labor_cost_daily))
    fixed_opex_daily_total = max(0.0, _f(fixed_opex_daily))
    cash_total = max(0.0, _f(cash_available))
    interest = max(0.0, _f(interest_rate, 0.05))

    per_factor = 1.0 if center_id else (1.0 / active_centers)
    rows: list[dict[str, Any]] = []
    portfolio = {
        "sales": 0.0,
        "theoretical_cost": 0.0,
        "gross_profit": 0.0,
        "waste": 0.0,
        "purchases": 0.0,
        "labor_cost": 0.0,
        "fixed_opex": 0.0,
        "finance_cost_daily": 0.0,
        "ebitda_daily": 0.0,
        "net_result_daily": 0.0,
        "prime_cost": 0.0,
        "own_capital": own_total,
        "financed_capital": financed_total,
        "invested_capital": own_total + financed_total,
        "labor_liability": labor_liability_total,
        "cash_available": cash_total,
    }

    for c in centers:
        daily = build_daily_business_dashboard(center_id=int(c["id"]), start_date=start, end_date=end)
        total = daily.get("total") or {}
        sales = _f(total.get("sales"))
        theoretical_cost = _f(total.get("theoretical_cost"))
        waste = _f(total.get("waste"))
        purchases = _f(total.get("purchases"))
        gross_profit = sales - theoretical_cost

        own = own_total * per_factor
        financed = financed_total * per_factor
        labor_liab = labor_liability_total * per_factor
        labor_daily = labor_daily_total * per_factor
        fixed_daily = fixed_opex_daily_total * per_factor
        cash = cash_total * per_factor
        invested = own + financed
        finance_daily = financed * interest / 365.0
        ebitda_daily = sales - theoretical_cost - waste - labor_daily - fixed_daily
        net_result_daily = ebitda_daily - finance_daily
        ebitda_period = ebitda_daily * days
        net_result_period = net_result_daily * days
        annualized_ebitda = ebitda_daily * 365.0
        annualized_net_result = net_result_daily * 365.0
        roic = _pct(annualized_ebitda, invested) if invested > 0 else 0.0
        net_roic = _pct(annualized_net_result, invested) if invested > 0 else 0.0
        capital_return_daily = _pct(ebitda_daily, invested) if invested > 0 else 0.0
        prime_cost = theoretical_cost + labor_daily
        operating_burn = theoretical_cost + waste + labor_daily + fixed_daily + finance_daily
        cash_need_30 = max(0.0, operating_burn * 30.0 - cash)
        working_capital_gap_30 = cash - (operating_burn * 30.0)
        cash_coverage_days = cash / max(1.0, operating_burn) if cash > 0 else 0.0
        row = {
            "center_id": c["id"],
            "center_name": c["name"],
            "sales": sales,
            "theoretical_cost": theoretical_cost,
            "food_cost_pct": _pct(theoretical_cost, sales),
            "gross_profit": gross_profit,
            "gross_margin_pct": _pct(gross_profit, sales),
            "waste": waste,
            "waste_pct_sales": _pct(waste, sales),
            "purchases": purchases,
            "labor_cost_daily": labor_daily,
            "labor_cost_pct": _pct(labor_daily, sales),
            "prime_cost": prime_cost,
            "prime_cost_pct": _pct(prime_cost, sales),
            "fixed_opex_daily": fixed_daily,
            "finance_cost_daily": finance_daily,
            "finance_cost_monthly": finance_daily * 30.0,
            "ebitda_daily": ebitda_daily,
            "net_result_daily": net_result_daily,
            "net_margin_pct": _pct(net_result_daily, sales),
            "ebitda_period": ebitda_period,
            "net_result_period": net_result_period,
            "annualized_ebitda": annualized_ebitda,
            "annualized_net_result": annualized_net_result,
            "own_capital": own,
            "financed_capital": financed,
            "invested_capital": invested,
            "debt_to_capital_pct": _pct(financed, invested),
            "labor_liability": labor_liab,
            "labor_liability_ratio_pct": _pct(labor_liab, max(1.0, annualized_ebitda)),
            "roic_annualized_pct": roic,
            "net_roic_annualized_pct": net_roic,
            "capital_return_daily_pct": capital_return_daily,
            "sales_to_capital_annualized_pct": _pct(sales * 365.0, invested) if invested > 0 else 0.0,
            "cash_available": cash,
            "cash_need_30": cash_need_30,
            "working_capital_gap_30": working_capital_gap_30,
            "cash_coverage_days": cash_coverage_days,
            "has_sales": sales > 0,
        }
        row["status"] = _status_for(row)
        row["decision"] = _decision_label(row)
        row["diagnosis"] = _diagnosis(row)
        rows.append(row)
        for k in ("sales", "theoretical_cost", "gross_profit", "waste", "purchases", "labor_cost_daily", "fixed_opex_daily", "finance_cost_daily", "ebitda_daily", "net_result_daily", "prime_cost"):
            portfolio_key = "labor_cost" if k == "labor_cost_daily" else ("fixed_opex" if k == "fixed_opex_daily" else k)
            portfolio[portfolio_key] = portfolio.get(portfolio_key, 0.0) + row[k]

    portfolio["food_cost_pct"] = _pct(portfolio["theoretical_cost"], portfolio["sales"])
    portfolio["gross_margin_pct"] = _pct(portfolio["gross_profit"], portfolio["sales"])
    portfolio["labor_cost_pct"] = _pct(portfolio["labor_cost"], portfolio["sales"])
    portfolio["prime_cost_pct"] = _pct(portfolio["prime_cost"], portfolio["sales"])
    portfolio["net_margin_pct"] = _pct(portfolio["net_result_daily"], portfolio["sales"])
    portfolio["annualized_ebitda"] = portfolio["ebitda_daily"] * 365.0
    portfolio["annualized_net_result"] = portfolio["net_result_daily"] * 365.0
    portfolio["roic_annualized_pct"] = _pct(portfolio["annualized_ebitda"], portfolio["invested_capital"])
    portfolio["net_roic_annualized_pct"] = _pct(portfolio["annualized_net_result"], portfolio["invested_capital"])
    portfolio["debt_to_capital_pct"] = _pct(portfolio["financed_capital"], portfolio["invested_capital"])
    portfolio["finance_cost_monthly"] = portfolio["finance_cost_daily"] * 30.0
    portfolio["labor_liability_ratio_pct"] = _pct(portfolio["labor_liability"], max(1.0, portfolio["annualized_ebitda"]))
    portfolio["cash_coverage_days"] = portfolio["cash_available"] / max(1.0, portfolio["theoretical_cost"] + portfolio["waste"] + portfolio["labor_cost"] + portfolio["fixed_opex"] + portfolio["finance_cost_daily"]) if portfolio["cash_available"] > 0 else 0.0
    portfolio["cash_need_30"] = max(0.0, (portfolio["theoretical_cost"] + portfolio["waste"] + portfolio["labor_cost"] + portfolio["fixed_opex"] + portfolio["finance_cost_daily"]) * 30.0 - portfolio["cash_available"])
    portfolio["working_capital_gap_30"] = portfolio["cash_available"] - ((portfolio["theoretical_cost"] + portfolio["waste"] + portfolio["labor_cost"] + portfolio["fixed_opex"] + portfolio["finance_cost_daily"]) * 30.0)

    ranked_by_roic = sorted(rows, key=lambda r: (r["has_sales"], r["roic_annualized_pct"]), reverse=True)
    ranked_by_ebitda = sorted(rows, key=lambda r: r["ebitda_daily"], reverse=True)
    ranked_by_net = sorted(rows, key=lambda r: r["net_result_daily"], reverse=True)
    risk_rows = sorted(rows, key=lambda r: (r["status"] == "critico", r["status"] == "atencion", -r["roic_annualized_pct"]), reverse=True)
    ceo_kpis = _ceo_kpis(portfolio, rows)
    notes = [
        "Beneficio absoluto, EBITDA, resultado neto y rendimiento del capital se muestran separados: vender más no implica rentar mejor.",
        "El interés base del capital financiado es 5% anual salvo cambio manual en el simulador.",
        "EBITDA operativo no descuenta coste financiero; resultado neto estimado sí descuenta el coste financiero del capital financiado.",
        "Los datos de capital propio, capital financiado, pasivo laboral y gastos fijos son hipótesis explícitas hasta integrar contabilidad real.",
    ]
    if not any(r["has_sales"] for r in rows):
        notes.append("Sin ventas normalizadas por local: la pestaña queda preparada, pero no puede calcular rendimiento real todavía.")

    return {
        "period": label,
        "start_date": start,
        "end_date": end,
        "days": days,
        "interest_rate": interest,
        "assumptions": {
            "own_capital": own_total,
            "financed_capital": financed_total,
            "interest_rate": interest,
            "labor_liability": labor_liability_total,
            "labor_cost_daily": labor_daily_total,
            "fixed_opex_daily": fixed_opex_daily_total,
            "cash_available": cash_total,
            "split_mode": "por local seleccionado" if center_id else "dividido proporcionalmente entre locales visibles",
        },
        "portfolio": portfolio,
        "rows": rows,
        "ranked_by_roic": ranked_by_roic,
        "ranked_by_ebitda": ranked_by_ebitda,
        "ranked_by_net": ranked_by_net,
        "risk_rows": risk_rows,
        "ceo_kpis": ceo_kpis,
        "portfolio_recommendation": _portfolio_recommendation(portfolio, rows),
        "notes": notes,
    }
