from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from app.core import db, recipe_with_calc, get_table_columns_from_cursor, table_exists, db_coalesce_text


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default


def _has_table(cur, name: str) -> bool:
    try:
        return table_exists(cur, name)
    except Exception:
        return False


def _cols(cur, table: str) -> set[str]:
    if not _has_table(cur, table):
        return set()
    return get_table_columns_from_cursor(cur, table)


def _today_str() -> str:
    return date.today().isoformat()


def _norm_date(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value[:10]).date().isoformat()
    except Exception:
        return None


def _period(start_date: str | None, end_date: str | None) -> tuple[str, str, str]:
    start = _norm_date(start_date)
    end = _norm_date(end_date)
    if not start and not end:
        start = end = _today_str()
    elif start and not end:
        end = start
    elif end and not start:
        start = end
    if start and end and start > end:
        start, end = end, start
    label = start if start == end else f"{start} → {end}"
    return start or _today_str(), end or _today_str(), label


def _area_from_business_type(value: str | None) -> str:
    s = (value or "").strip().lower()
    if s in {"bar", "barra", "cocktail", "cocteleria", "bebidas"}:
        return "barra"
    return "cocina"


def _empty_area(name: str) -> dict[str, Any]:
    return {
        "key": name.lower(),
        "name": name,
        "sales": 0.0,
        "theoretical_cost": 0.0,
        "purchases": 0.0,
        "waste": 0.0,
        "gross_margin": 0.0,
        "gross_margin_pct": 0.0,
        "food_cost_pct": 0.0,
        "tickets": 0,
        "has_data": False,
    }


def _finish_area(area: dict[str, Any]) -> None:
    area["gross_margin"] = area["sales"] - area["theoretical_cost"]
    area["gross_margin_pct"] = (area["gross_margin"] / area["sales"] * 100.0) if area["sales"] > 0 else 0.0
    area["food_cost_pct"] = (area["theoretical_cost"] / area["sales"] * 100.0) if area["sales"] > 0 else 0.0
    area["has_data"] = any(abs(area[k]) > 0 for k in ("sales", "theoretical_cost", "purchases", "waste")) or area.get("tickets", 0) > 0


def _recipe_cost_per_portion(cur, recipe_id: int) -> float:
    if not recipe_id:
        return 0.0
    try:
        payload = recipe_with_calc(cur, int(recipe_id)) or {}
        return _f((payload.get("calc") or {}).get("cost_per_portion"), 0.0)
    except Exception:
        return 0.0


def _cocktail_cost_by_name(cur, name: str) -> float:
    if not name or not _has_table(cur, "cocktail_recipes"):
        return 0.0
    row = cur.execute(
        "SELECT cost_2026_gross_with_waste, cost_2026_net FROM cocktail_recipes WHERE lower(name)=lower(?) LIMIT 1",
        (name.strip(),),
    ).fetchone()
    if not row:
        return 0.0
    return _f(row["cost_2026_gross_with_waste"], 0.0) or _f(row["cost_2026_net"], 0.0)


def build_daily_business_dashboard(center_id: int | None = None, start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    """Executive daily dashboard for Inicio.

    Conservative by design:
    - It reads normalized POS/import tables when present.
    - It separates theoretical food cost from purchases of the day.
    - It returns empty/ready states instead of inventing sales or costs.
    """
    start, end, label = _period(start_date, end_date)
    conn = db()
    try:
        cur = conn.cursor()
        areas = {
            "cocina": _empty_area("Cocina"),
            "barra": _empty_area("Barra"),
        }
        notes: list[str] = []
        warnings: list[str] = []

        # Sales from aggregated normalized POS table.
        if _has_table(cur, "pos_sales_daily"):
            where = ["sale_date BETWEEN ? AND ?"]
            params: list[Any] = [start, end]
            if center_id:
                where.append("center_id=?")
                params.append(int(center_id))
            rows = cur.execute(
                f"""SELECT business_type, SUM(net_sales) sales, SUM(tickets) tickets
                    FROM pos_sales_daily WHERE {' AND '.join(where)} GROUP BY business_type""",
                params,
            ).fetchall()
            for r in rows:
                key = _area_from_business_type(r["business_type"])
                areas[key]["sales"] += _f(r["sales"])
                areas[key]["tickets"] += int(_f(r["tickets"], 0.0))

        # Fallback/direct LAB POS tables.
        if _has_table(cur, "tpv_sales"):
            cols = _cols(cur, "tpv_sales")
            date_col = "business_date" if "business_date" in cols else "sale_datetime"
            where = [f"substr({date_col},1,10) BETWEEN ? AND ?"]
            params = [start, end]
            if center_id and "restaurant_id" in cols:
                where.append("COALESCE(restaurant_id,0) IN (0, ?)")
                params.append(int(center_id))
            rows = cur.execute(
                f"""SELECT COUNT(*) tickets, SUM(total_amount) sales
                    FROM tpv_sales WHERE {' AND '.join(where)}""",
                params,
            ).fetchone()
            # In this beta table, most sales are kitchen unless matched later as bar/cocktail.
            areas["cocina"]["sales"] += _f(rows["sales"] if rows else 0.0)
            areas["cocina"]["tickets"] += int(_f(rows["tickets"] if rows else 0.0))

        # Theoretical cost from normalized item daily table.
        if _has_table(cur, "pos_sales_item_daily"):
            where = ["sale_date BETWEEN ? AND ?"]
            params = [start, end]
            if center_id:
                where.append("center_id=?")
                params.append(int(center_id))
            rows = cur.execute(
                f"""SELECT recipe_id, recipe_name, business_type, SUM(qty_sold) qty
                    FROM pos_sales_item_daily WHERE {' AND '.join(where)} GROUP BY recipe_id, recipe_name, business_type""",
                params,
            ).fetchall()
            for r in rows:
                key = _area_from_business_type(r["business_type"])
                cost = _recipe_cost_per_portion(cur, int(r["recipe_id"] or 0))
                if cost <= 0 and key == "barra":
                    cost = _cocktail_cost_by_name(cur, r["recipe_name"] or "")
                areas[key]["theoretical_cost"] += _f(r["qty"]) * cost

        # Fallback/direct LAB POS line cost.
        if _has_table(cur, "tpv_sale_lines") and _has_table(cur, "tpv_sales"):
            where = [f"substr({db_coalesce_text('s.business_date','s.sale_datetime', cur_or_conn=cur)},1,10) BETWEEN ? AND ?"]
            params = [start, end]
            if center_id:
                where.append("COALESCE(s.restaurant_id,0) IN (0, ?)")
                params.append(int(center_id))
            rows = cur.execute(
                f"""SELECT l.matched_recipe_id, l.product_name_raw, SUM(COALESCE(l.quantity,0)) qty
                    FROM tpv_sale_lines l JOIN tpv_sales s ON s.id=l.tpv_sale_id
                    WHERE {' AND '.join(where)} GROUP BY l.matched_recipe_id, l.product_name_raw""",
                params,
            ).fetchall()
            for r in rows:
                recipe_id = int(r["matched_recipe_id"] or 0)
                qty = _f(r["qty"])
                cocktail_cost = _cocktail_cost_by_name(cur, r["product_name_raw"] or "")
                if cocktail_cost > 0:
                    areas["barra"]["theoretical_cost"] += qty * cocktail_cost
                elif recipe_id:
                    areas["cocina"]["theoretical_cost"] += qty * _recipe_cost_per_portion(cur, recipe_id)
                else:
                    warnings.append(f"Venta sin coste teórico mapeado: {r['product_name_raw'] or 'sin nombre'}")

        # Purchases/validated receipts for kitchen.
        if _has_table(cur, "receipts") and _has_table(cur, "receipt_lines"):
            where = [f"substr({db_coalesce_text('r.doc_date','r.validated_at','r.created_at', cur_or_conn=cur)},1,10) BETWEEN ? AND ?"]
            params = [start, end]
            if center_id:
                where.append("r.center_id=?")
                params.append(int(center_id))
            row = cur.execute(
                f"""SELECT SUM(COALESCE(rl.line_total, COALESCE(rl.qty_input,0)*COALESCE(rl.price_unit,0))) total
                    FROM receipt_lines rl JOIN receipts r ON r.id=rl.receipt_id
                    WHERE {' AND '.join(where)}""",
                params,
            ).fetchone()
            areas["cocina"]["purchases"] += _f(row["total"] if row else 0.0)
        # Purchases/entries for bar demo/stock. Uses movement value estimated from item unit cost.
        if _has_table(cur, "bar_stock_movements") and _has_table(cur, "bar_items"):
            row = cur.execute(
                f"""SELECT SUM(m.qty * COALESCE(i.cost_per_base_unit_2026,0)) total
                     FROM bar_stock_movements m JOIN bar_items i ON i.id=m.bar_item_id
                     WHERE lower(COALESCE(m.movement_type,'')) IN ('entrada','in')
                         AND substr({db_coalesce_text('m.movement_datetime','m.created_at', cur_or_conn=cur)},1,10) BETWEEN ? AND ?""",
                (start, end),
            ).fetchone()
            areas["barra"]["purchases"] += _f(row["total"] if row else 0.0)

        # Waste.
        if _has_table(cur, "waste_records"):
            where = [f"substr({db_coalesce_text('confirmed_at','created_at', cur_or_conn=cur)},1,10) BETWEEN ? AND ?"]
            params = [start, end]
            if center_id:
                where.append("center_id=?")
                params.append(int(center_id))
            row = cur.execute(
                f"SELECT SUM(total_cost_snapshot) total FROM waste_records WHERE status IN ('CONFIRMED','CONFIRMADA','confirmada') AND {' AND '.join(where)}",
                params,
            ).fetchone()
            areas["cocina"]["waste"] += _f(row["total"] if row else 0.0)

        # Expiry / rotation suggestions. Conservative: only known shelf-life and demo bar open stock/preps.
        suggestions: list[dict[str, Any]] = []
        if _has_table(cur, "bar_productions"):
            for r in cur.execute(
                """SELECT name, stock_actual, yield_unit, shelf_life_days, storage_location
                   FROM bar_productions
                   WHERE COALESCE(stock_actual,0)>0 AND COALESCE(shelf_life_days,0) BETWEEN 1 AND 3
                   ORDER BY shelf_life_days ASC, stock_actual DESC LIMIT 6"""
            ).fetchall():
                suggestions.append({
                    "area": "Barra",
                    "item": r["name"],
                    "risk": f"Caducidad corta: {int(r['shelf_life_days'] or 0)} día(s)",
                    "detail": f"Stock aprox. {r['stock_actual']:.0f} {r['yield_unit'] or ''} · {r['storage_location'] or 'sin ubicación'}",
                    "action": "Sugerir cócteles o servicios que usen este preparado antes de descartarlo.",
                })
        if _has_table(cur, "items"):
            for r in cur.execute(
                """SELECT name, stock_area, current_price, max_qty, min_qty
                   FROM items
                   WHERE COALESCE(max_qty,0)>0 AND COALESCE(current_price,0)>0
                   ORDER BY current_price DESC LIMIT 4"""
            ).fetchall():
                suggestions.append({
                    "area": "Cocina",
                    "item": r["name"],
                    "risk": "Vigilar rotación / coste alto",
                    "detail": f"Rubro {r['stock_area'] or '-'} · precio {r['current_price']:.2f} €/{'ud'}",
                    "action": "Revisar stock real, ventas asociadas y posible prioridad de salida si hay riesgo de merma.",
                })

        total = _empty_area("Total")
        for key in ("sales", "theoretical_cost", "purchases", "waste"):
            total[key] = areas["cocina"][key] + areas["barra"][key]
        total["tickets"] = areas["cocina"]["tickets"] + areas["barra"]["tickets"]
        for a in areas.values():
            _finish_area(a)
        _finish_area(total)

        if not total["sales"]:
            notes.append("Sin ventas normalizadas en el periodo. El dashboard no inventa ventas: mostrará datos cuando entre TPV/importación.")
        if total["purchases"] and not total["sales"]:
            notes.append("Hay compras/entradas, pero sin ventas asociadas en el periodo.")
        if total["sales"] and not total["theoretical_cost"]:
            notes.append("Hay ventas, pero falta mapeo coste/receta para calcular food cost teórico completo.")
        notes.append("Food cost teórico por ventas y compras del día se muestran separados para evitar lecturas engañosas.")

        return {
            "period": label,
            "start_date": start,
            "end_date": end,
            "has_data": total["has_data"] or bool(suggestions),
            "areas": [areas["cocina"], areas["barra"], total],
            "cocina": areas["cocina"],
            "barra": areas["barra"],
            "total": total,
            "suggestions": suggestions[:8],
            "alerts": warnings[:6],
            "notes": notes[:6],
        }
    finally:
        conn.close()
