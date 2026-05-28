"""Dashboard mensual · ranking de ventas de platos y margen.

Lectura pura. Prepara terreno para TPV multi-negocio sin acoplar un proveedor concreto.
Si no hay ventas TPV cargadas, informa falta de datos y no inventa ranking.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.core import db, ensure_columns, recipe_with_calc, table_exists as core_table_exists, db_coalesce_text
from app.services.pos_modifiers_service import build_monthly_modifier_dashboard


def _rowdict(row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()} if row is not None and hasattr(row, "keys") else dict(row or {})


def _safe_float(v: Any) -> float:
    try:
        return float(v or 0.0)
    except Exception:
        return 0.0


def _safe_int(v: Any) -> int:
    try:
        return int(v or 0)
    except Exception:
        return 0


def _month_bounds(year: int | None = None, month: int | None = None) -> tuple[str, str, str]:
    today = date.today()
    y = int(year or today.year)
    m = int(month or today.month)
    if m < 1 or m > 12:
        y, m = today.year, today.month
    start = date(y, m, 1)
    end = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return start.isoformat(), end.isoformat(), f"{y:04d}-{m:02d}"


def _table_exists(cur, name: str) -> bool:
    return core_table_exists(cur, name)


def _recipe_cost(cur, recipe_id: int) -> dict[str, Any]:
    try:
        payload = recipe_with_calc(cur, int(recipe_id)) or {}
        calc = payload.get("calc", {}) or {}
    except Exception:
        calc = {}
    food_cost = _safe_float(calc.get("total_cost") or calc.get("cost_total") or calc.get("food_cost_total"))
    food_cost_pct = _safe_float(calc.get("food_cost_pct"))
    return {"food_cost": food_cost, "food_cost_pct": food_cost_pct}


def _action_for_row(row: dict[str, Any]) -> str:
    fc = _safe_float(row.get("food_cost_pct"))
    margin = _safe_float(row.get("gross_margin_pct"))
    if row.get("missing_recipe_link"):
        return "Vincular venta TPV con receta real antes de evaluar margen."
    if row.get("net_sales") and _safe_float(row.get("food_cost_total")) <= 0:
        return "Revisar escandallo/precio: venta con coste de receta incompleto."
    if fc >= 45 or margin <= 45:
        return "Revisar precio de venta, gramaje, merma o proveedor causante."
    if fc >= 35 or margin <= 55:
        return "Vigilar margen; comparar con ventas y subida de ingredientes."
    return "OK. Mantener seguimiento mensual."


def build_monthly_recipe_sales_dashboard(center_id: int | None = None, year: int | None = None, month: int | None = None) -> dict[str, Any]:
    """Ranking mensual de ventas por plato.

    Fuente futura normalizada: pos_sales_item_daily. No modifica datos.
    Espera columnas flexibles y tolera esquemas incompletos:
      sale_date, center_id, recipe_id, recipe_name, qty_sold, net_sales, gross_sales, channel, business_type.
    """
    start, end, period = _month_bounds(year, month)
    conn = db(); cur = conn.cursor(); ensure_columns(cur)

    if not _table_exists(cur, "pos_sales_item_daily"):
        conn.close()
        return {
            "period": period,
            "has_data": False,
            "source_ready": False,
            "total_qty": 0.0,
            "total_net_sales": 0.0,
            "total_food_cost": 0.0,
            "gross_margin_value": 0.0,
            "gross_margin_pct": 0.0,
            "top_by_units": [],
            "top_by_sales": [],
            "top_margin_risk": [],
            "unlinked_sales": [],
            "by_channel": [],
            "by_business_type": [],
            "recommendations": [
                "Ranking de ventas preparado, pero aún no hay tabla de ventas TPV normalizada.",
                "Cuando se conecte un TPV, cargar ventas por receta/plato en pos_sales_item_daily.",
            ],
            "optional_improvements": _optional_improvements(),
            "modifier_dashboard": build_monthly_modifier_dashboard(center_id=center_id, year=year, month=month),
        }

    params: list[Any] = [start, end]
    center_clause = ""
    if center_id:
        center_clause = " AND ps.center_id=?"
        params.append(int(center_id))

    try:
        rows = cur.execute(
            f"""
            SELECT COALESCE(ps.recipe_id,0) recipe_id,
                   COALESCE(ps.recipe_name, r.name, 'Venta sin receta vinculada') recipe_name,
                   COALESCE(r.category,'') category,
                   COALESCE(r.subcategory,'') subcategory,
                   COALESCE(ps.channel,'') channel,
                   COALESCE(ps.business_type,'') business_type,
                   COALESCE(c.name,'') center_name,
                   SUM(COALESCE(ps.qty_sold,0)) qty_sold,
                   SUM(COALESCE(ps.net_sales,0)) net_sales,
                   SUM(COALESCE(ps.gross_sales,0)) gross_sales,
                   COUNT(*) days_or_rows
              FROM pos_sales_item_daily ps
              LEFT JOIN recipes r ON r.id=ps.recipe_id
              LEFT JOIN centers c ON c.id=ps.center_id
                         WHERE date(COALESCE({db_coalesce_text('ps.sale_date', cur_or_conn=cur)},'')) >= date(?)
                             AND date(COALESCE({db_coalesce_text('ps.sale_date', cur_or_conn=cur)},'')) < date(?)
               {center_clause}
             GROUP BY COALESCE(ps.recipe_id,0), COALESCE(ps.recipe_name, r.name, 'Venta sin receta vinculada'),
                      COALESCE(ps.channel,''), COALESCE(ps.business_type,''), COALESCE(ps.center_id,0)
             ORDER BY net_sales DESC, qty_sold DESC
            """,
            tuple(params),
        ).fetchall()
    except Exception:
        rows = []

    sales_rows: list[dict[str, Any]] = []
    for raw in rows:
        r = _rowdict(raw)
        recipe_id = _safe_int(r.get("recipe_id"))
        qty = _safe_float(r.get("qty_sold"))
        net_sales = _safe_float(r.get("net_sales"))
        cost_info = _recipe_cost(cur, recipe_id) if recipe_id else {"food_cost": 0.0, "food_cost_pct": 0.0}
        food_cost_unit = _safe_float(cost_info.get("food_cost"))
        food_cost_total = food_cost_unit * qty if qty > 0 else 0.0
        gross_margin_value = net_sales - food_cost_total
        gross_margin_pct = (gross_margin_value / net_sales * 100.0) if net_sales > 0 else 0.0
        food_cost_pct = (food_cost_total / net_sales * 100.0) if net_sales > 0 and food_cost_total > 0 else _safe_float(cost_info.get("food_cost_pct"))
        row = {
            "recipe_id": recipe_id,
            "recipe_name": r.get("recipe_name") or "Venta sin receta vinculada",
            "center_name": r.get("center_name") or "",
            "category": r.get("category") or "",
            "subcategory": r.get("subcategory") or "",
            "channel": r.get("channel") or "sin canal",
            "business_type": r.get("business_type") or "sin tipo",
            "qty_sold": qty,
            "net_sales": net_sales,
            "gross_sales": _safe_float(r.get("gross_sales")),
            "food_cost_unit": food_cost_unit,
            "food_cost_total": food_cost_total,
            "food_cost_pct": food_cost_pct,
            "gross_margin_value": gross_margin_value,
            "gross_margin_pct": gross_margin_pct,
            "missing_recipe_link": recipe_id <= 0,
            "days_or_rows": _safe_int(r.get("days_or_rows")),
        }
        row["recommended_action"] = _action_for_row(row)
        sales_rows.append(row)

    total_qty = sum(_safe_float(x.get("qty_sold")) for x in sales_rows)
    total_net = sum(_safe_float(x.get("net_sales")) for x in sales_rows)
    total_cost = sum(_safe_float(x.get("food_cost_total")) for x in sales_rows)
    total_margin = total_net - total_cost
    total_margin_pct = (total_margin / total_net * 100.0) if total_net > 0 else 0.0

    def _group(key: str) -> list[dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for x in sales_rows:
            name = str(x.get(key) or "sin clasificar")
            g = out.setdefault(name, {"name": name, "qty_sold": 0.0, "net_sales": 0.0, "food_cost_total": 0.0, "gross_margin_value": 0.0})
            g["qty_sold"] += _safe_float(x.get("qty_sold"))
            g["net_sales"] += _safe_float(x.get("net_sales"))
            g["food_cost_total"] += _safe_float(x.get("food_cost_total"))
            g["gross_margin_value"] += _safe_float(x.get("gross_margin_value"))
        for g in out.values():
            ns = _safe_float(g.get("net_sales"))
            g["gross_margin_pct"] = (_safe_float(g.get("gross_margin_value")) / ns * 100.0) if ns > 0 else 0.0
        return sorted(out.values(), key=lambda z: _safe_float(z.get("net_sales")), reverse=True)

    top_by_units = sorted(sales_rows, key=lambda x: (_safe_float(x.get("qty_sold")), _safe_float(x.get("net_sales"))), reverse=True)[:15]
    top_by_sales = sorted(sales_rows, key=lambda x: (_safe_float(x.get("net_sales")), _safe_float(x.get("qty_sold"))), reverse=True)[:15]
    top_margin_risk = sorted(
        [x for x in sales_rows if x.get("missing_recipe_link") or _safe_float(x.get("food_cost_pct")) >= 35 or _safe_float(x.get("gross_margin_pct")) <= 55],
        key=lambda x: (_safe_float(x.get("food_cost_pct")), -_safe_float(x.get("gross_margin_pct")), _safe_float(x.get("net_sales"))),
        reverse=True,
    )[:15]
    unlinked_sales = [x for x in sales_rows if x.get("missing_recipe_link")][:15]

    recommendations: list[str] = []
    if not sales_rows:
        recommendations.append("No hay ventas TPV normalizadas para este periodo; el ranking queda listo para cuando se importen ventas.")
    else:
        recommendations.append("Revisar primero platos con mucha venta y margen bajo: son los que más afectan el resultado mensual.")
        if unlinked_sales:
            recommendations.append("Hay ventas sin receta vinculada: no se puede calcular margen completo hasta mapear plato TPV ↔ receta.")
        if top_margin_risk:
            recommendations.append("Priorizar acciones: subir precio, revisar gramaje, revisar merma o buscar proveedor alternativo según causa.")

    conn.close()
    modifier_dashboard = build_monthly_modifier_dashboard(center_id=center_id, year=year, month=month)
    return {
        "period": period,
        "has_data": bool(sales_rows),
        "source_ready": True,
        "total_qty": total_qty,
        "total_net_sales": total_net,
        "total_food_cost": total_cost,
        "gross_margin_value": total_margin,
        "gross_margin_pct": total_margin_pct,
        "top_by_units": top_by_units,
        "top_by_sales": top_by_sales,
        "top_margin_risk": top_margin_risk,
        "unlinked_sales": unlinked_sales,
        "by_channel": _group("channel"),
        "by_business_type": _group("business_type"),
        "recommendations": recommendations,
        "optional_improvements": _optional_improvements(),
        "modifier_dashboard": modifier_dashboard,
    }


def _optional_improvements() -> list[dict[str, str]]:
    return [
        {"name": "Mapa TPV ↔ recetas", "value": "tabla para vincular nombres de venta de cada TPV con receta maestra real."},
        {"name": "Modificadores TPV", "value": "mapear sin pan, extra queso, guarnición, sin salsa o solo aceite como deltas de stock sobre la receta base."},
        {"name": "Canales", "value": "separar salón, barra, delivery, take away, eventos, catering y hotel."},
        {"name": "Venta prevista", "value": "usar ranking histórico para alimentar pedidos sugeridos y producción prevista."},
        {"name": "Ingeniería de menú", "value": "clasificar platos estrella, caballo de batalla, puzzle y perro según margen y popularidad."},
        {"name": "Alertas de precio", "value": "avisar si un plato muy vendido cruza umbral de food cost por subida de proveedor."},
    ]
