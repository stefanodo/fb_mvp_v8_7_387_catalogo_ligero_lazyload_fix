"""Dashboard mensual de dirección · proveedores, precios y recetas afectadas.

Lectura pura. No modifica stock, recetas, pedidos ni albaranes.
Objetivo: detectar qué proveedor subió más, qué artículo causó impacto y qué recetas quedan afectadas.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.core import db, ensure_columns, recipe_with_calc, db_coalesce_text


def _rowdict(row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()} if row is not None and hasattr(row, "keys") else dict(row or {})


def _month_bounds(year: int | None = None, month: int | None = None) -> tuple[str, str, str]:
    today = date.today()
    y = int(year or today.year)
    m = int(month or today.month)
    if m < 1 or m > 12:
        y, m = today.year, today.month
    start = date(y, m, 1)
    end = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return start.isoformat(), end.isoformat(), f"{y:04d}-{m:02d}"



def _parse_delivery_days(raw: Any) -> set[int]:
    """Devuelve días de reparto 0=lunes...6=domingo. Vacío = sin restricción configurada."""
    if raw is None:
        return set()
    s = str(raw).strip().lower()
    if not s:
        return set()
    aliases = {
        "lunes": 0, "lun": 0, "l": 0,
        "martes": 1, "mar": 1, "ma": 1,
        "miercoles": 2, "miércoles": 2, "mie": 2, "mié": 2, "mi": 2, "x": 2,
        "jueves": 3, "jue": 3, "j": 3,
        "viernes": 4, "vie": 4, "v": 4,
        "sabado": 5, "sábado": 5, "sab": 5, "sáb": 5, "s": 5,
        "domingo": 6, "dom": 6, "d": 6,
    }
    if "lunes-sábado" in s or "lunes-sabado" in s or "lun-sab" in s or "l-s" in s:
        return {0, 1, 2, 3, 4, 5}
    if "lunes-domingo" in s or "lunes-dom" in s or "todos" in s:
        return {0, 1, 2, 3, 4, 5, 6}
    out: set[int] = set()
    for token in s.replace(";", ",").replace("/", ",").replace("|", ",").split(","):
        t = token.strip()
        if not t:
            continue
        if t.isdigit():
            n = int(t)
            if 0 <= n <= 6:
                out.add(n)
            continue
        if "-" in t:
            a, b = [x.strip() for x in t.split("-", 1)]
            if a in aliases and b in aliases:
                start, end = aliases[a], aliases[b]
                if start <= end:
                    out.update(range(start, end + 1))
                else:
                    out.update(list(range(start, 7)) + list(range(0, end + 1)))
                continue
        if t in aliases:
            out.add(aliases[t])
    return out


def _delivery_label(days: set[int]) -> str:
    names = ["L", "M", "X", "J", "V", "S", "D"]
    return "/".join(names[d] for d in sorted(days)) if days else "sin regla"


def _next_delivery_day(days: set[int], lead_time_days: int = 0, from_day: date | None = None) -> str:
    base = (from_day or date.today()) + timedelta(days=max(0, int(lead_time_days or 0)))
    if not days:
        return base.isoformat()
    for offset in range(0, 15):
        candidate = base + timedelta(days=offset)
        if candidate.weekday() in days:
            return candidate.isoformat()
    return ""


def _supplier_delivery_review(raw_supplier: dict[str, Any], estimated_alt_order_value: float) -> dict[str, Any]:
    days = _parse_delivery_days(raw_supplier.get("delivery_days"))
    min_amount = _safe_price(raw_supplier.get("delivery_min_order_amount"))
    lead = int(_safe_price(raw_supplier.get("delivery_lead_time_days")) or 0)
    next_date = _next_delivery_day(days, lead)
    below_min = bool(min_amount > 0 and float(estimated_alt_order_value or 0.0) < min_amount)
    warnings: list[str] = []
    if below_min:
        warnings.append(f"bajo mínimo proveedor: {estimated_alt_order_value:.2f}/{min_amount:.2f} €")
    if days and not next_date:
        warnings.append("sin próximo reparto claro")
    if lead > 0:
        warnings.append(f"plazo {lead} día(s)")
    status = "OK"
    if below_min:
        status = "BAJO_MINIMO"
    if warnings and status == "OK":
        status = "REVISAR"
    return {
        "delivery_days": sorted(days),
        "delivery_days_label": _delivery_label(days),
        "next_delivery_date": next_date,
        "delivery_min_order_amount": min_amount,
        "delivery_min_tax_mode": raw_supplier.get("delivery_min_tax_mode") or "ex_vat",
        "delivery_lead_time_days": lead,
        "delivery_notes": raw_supplier.get("delivery_notes") or "",
        "estimated_alt_order_value": float(estimated_alt_order_value or 0.0),
        "below_minimum": below_min,
        "status": status,
        "warnings": warnings,
    }

def _new_supplier_group(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "events": 0,
        "increases": 0,
        "decreases": 0,
        "max_increase_pct": 0.0,
        "total_estimated_month_impact": 0.0,
        "top_items": [],
        "affected_recipes": [],
    }


def _safe_price(v: Any) -> float:
    try:
        return float(v or 0.0)
    except Exception:
        return 0.0


def _recipes_using_item(cur, item_id: int, limit: int = 8) -> list[dict[str, Any]]:
    try:
        rows = cur.execute(
            """
            SELECT DISTINCT r.id, r.name, COALESCE(r.manual_price,0) manual_price,
                   COALESCE(r.suggested_price,0) suggested_price
              FROM recipe_ingredients ri
              JOIN recipes r ON r.id=ri.recipe_id
             WHERE ri.item_id=?
             ORDER BY LOWER(COALESCE(r.name,''))
             LIMIT ?
            """,
            (int(item_id or 0), int(limit)),
        ).fetchall()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        r = _rowdict(row)
        margin_state = "SIN_PRECIO_VENTA"
        food_cost_pct = 0.0
        try:
            calc = recipe_with_calc(cur, int(r.get("id") or 0)) or {}
            c = calc.get("calc", {}) or {}
            food_cost_pct = float(c.get("food_cost_pct") or 0.0)
            if food_cost_pct >= 45:
                margin_state = "PELIGRO"
            elif food_cost_pct >= 35:
                margin_state = "VIGILAR"
            elif food_cost_pct > 0:
                margin_state = "OK"
        except Exception:
            pass
        out.append({
            "id": int(r.get("id") or 0),
            "name": r.get("name") or "",
            "food_cost_pct": food_cost_pct,
            "margin_state": margin_state,
        })
    return out


def _month_qty_for_item_supplier(cur, item_id: int, supplier_id: int, start: str, end: str, center_id: int | None = None) -> float:
    params: list[Any] = [int(item_id or 0), int(supplier_id or 0), start, end]
    center_clause = ""
    if center_id:
        center_clause = " AND r.center_id=?"
        params.append(int(center_id))
    try:
        row = cur.execute(
            f"""
            SELECT COALESCE(SUM(COALESCE(rl.qty_base,0)),0) qty
              FROM receipt_lines rl
              JOIN receipts r ON r.id=rl.receipt_id
             WHERE rl.item_id=? AND r.supplier_id=?
               AND date(COALESCE({db_coalesce_text('r.doc_date','r.validated_at','r.created_at', cur_or_conn=cur)},'')) >= date(?)
               AND date(COALESCE({db_coalesce_text('r.doc_date','r.validated_at','r.created_at', cur_or_conn=cur)},'')) < date(?)
               {center_clause}
            """,
            tuple(params),
        ).fetchone()
        return float(row["qty"] or 0.0) if row else 0.0
    except Exception:
        return 0.0


def _cheapest_supplier_alternative(cur, item_id: int, current_supplier_id: int, current_unit_price: float, center_id: int | None = None, month_qty: float = 0.0) -> dict[str, Any] | None:
    """Busca proveedor alternativo más barato para el mismo artículo.

    Comparación prudente: usa supplier_item_prices normalizado a precio/base.
    No cambia proveedor ni modifica pedidos; solo devuelve recomendación revisable.
    """
    if not item_id or current_unit_price <= 0:
        return None
    params: list[Any] = [int(item_id)]
    center_clause = ""
    if center_id:
        center_clause = " AND (sp.center_id IS NULL OR sp.center_id=?)"
        params.append(int(center_id))
    try:
        rows = cur.execute(
            f"""
            SELECT sp.supplier_id, COALESCE(s.name,'') supplier_name,
                   COALESCE(sp.price_per_purchase,0) price_per_purchase,
                   COALESCE(sp.purchase_unit,'') purchase_unit,
                   COALESCE(sp.purchase_to_base_factor,1) purchase_to_base_factor,
                   COALESCE(sp.is_preferred,0) is_preferred,
                   COALESCE(sp.updated_at,'') updated_at, sp.center_id,
                   COALESCE(s.delivery_days,'') delivery_days,
                   COALESCE(s.delivery_min_order_amount,0) delivery_min_order_amount,
                   COALESCE(s.delivery_min_tax_mode,'ex_vat') delivery_min_tax_mode,
                   COALESCE(s.delivery_lead_time_days,0) delivery_lead_time_days,
                   COALESCE(s.delivery_notes,'') delivery_notes
              FROM supplier_item_prices sp
              JOIN suppliers s ON s.id=sp.supplier_id
             WHERE sp.item_id=? AND COALESCE(s.is_active,1)=1 AND COALESCE(sp.price_per_purchase,0)>0
               {center_clause}
             ORDER BY CASE WHEN sp.center_id IS NOT NULL THEN 0 ELSE 1 END, sp.updated_at DESC
            """,
            tuple(params),
        ).fetchall()
    except Exception:
        rows = []
    best_by_supplier: dict[int, dict[str, Any]] = {}
    for row in rows:
        r = _rowdict(row)
        sid = int(r.get("supplier_id") or 0)
        if not sid or sid == int(current_supplier_id or 0):
            continue
        factor = _safe_price(r.get("purchase_to_base_factor")) or 1.0
        if factor <= 0:
            factor = 1.0
        normalized_price = _safe_price(r.get("price_per_purchase")) / factor
        if normalized_price <= 0:
            continue
        estimated_alt_value = normalized_price * max(0.0, float(month_qty or 0.0))
        delivery_review = _supplier_delivery_review(r, estimated_alt_value)
        candidate = {
            "supplier_id": sid,
            "supplier_name": r.get("supplier_name") or "Proveedor alternativo",
            "price_per_purchase": _safe_price(r.get("price_per_purchase")),
            "purchase_unit": r.get("purchase_unit") or "",
            "purchase_to_base_factor": factor,
            "normalized_price": normalized_price,
            "is_preferred": int(r.get("is_preferred") or 0),
            "updated_at": r.get("updated_at") or "",
            "delivery_review": delivery_review,
            "delivery_status": delivery_review.get("status"),
            "delivery_warnings": delivery_review.get("warnings") or [],
            "delivery_days_label": delivery_review.get("delivery_days_label"),
            "next_delivery_date": delivery_review.get("next_delivery_date"),
            "delivery_min_order_amount": delivery_review.get("delivery_min_order_amount"),
            "estimated_alt_order_value": delivery_review.get("estimated_alt_order_value"),
        }
        prev = best_by_supplier.get(sid)
        if prev is None or normalized_price < float(prev.get("normalized_price") or 0):
            best_by_supplier[sid] = candidate
    # Priorización: no basta con ser barato; se ordena primero por viabilidad operativa
    # (mínimo de pedido/días/plazo), luego por precio.
    def _rank_candidate(x: dict[str, Any]) -> tuple[int, float, str]:
        status = str(x.get("delivery_status") or "OK")
        penalty = 0 if status == "OK" else (1 if status == "REVISAR" else 2)
        return (penalty, float(x.get("normalized_price") or 0), str(x.get("supplier_name") or "").lower())
    candidates = sorted(best_by_supplier.values(), key=_rank_candidate)
    if not candidates:
        return None
    best = candidates[0]
    best_price = float(best.get("normalized_price") or 0.0)
    saving_per_unit = float(current_unit_price or 0.0) - best_price
    if saving_per_unit <= 0:
        return None
    saving_pct = (saving_per_unit / float(current_unit_price or 1.0)) * 100.0
    best.update({
        "saving_per_unit": saving_per_unit,
        "saving_pct": saving_pct,
        "estimated_month_saving": saving_per_unit * max(0.0, float(month_qty or 0.0)),
        "current_unit_price": float(current_unit_price or 0.0),
        "review_required": True,
        "operationally_preferred": str(best.get("delivery_status") or "OK") == "OK",
    })
    return best


def build_monthly_supplier_dashboard(center_id: int | None = None, year: int | None = None, month: int | None = None) -> dict[str, Any]:
    """Construye lectura mensual de precios/proveedores y recetas afectadas.

    Usa albaranes/receipt_lines validados o con fecha de documento. Si falta histórico previo,
    no inventa subida: marca el artículo como sin comparativa suficiente.
    """
    start, end, period = _month_bounds(year, month)
    conn = db(); cur = conn.cursor(); ensure_columns(cur)

    center_clause = ""
    params: list[Any] = [start, end]
    if center_id:
        center_clause = " AND r.center_id=?"
        params.append(int(center_id))

    try:
        rows = cur.execute(
            f"""
            SELECT rl.item_id, COALESCE(i.name,'') item_name, COALESCE(i.unit, rl.input_unit, 'ud') base_unit,
                   r.supplier_id, COALESCE(s.name,'Sin proveedor') supplier_name,
                   r.center_id, COALESCE(c.name,'') center_name,
                   COALESCE(rl.price_unit,0) price_unit,
                   COALESCE(rl.qty_base,0) qty_base,
                   COALESCE(rl.line_total,0) line_total,
                   COALESCE({db_coalesce_text('r.doc_date','r.validated_at','r.created_at', cur_or_conn=cur)},'') event_date,
                   r.doc_number, r.id receipt_id
              FROM receipt_lines rl
              JOIN receipts r ON r.id=rl.receipt_id
              LEFT JOIN items i ON i.id=rl.item_id
              LEFT JOIN suppliers s ON s.id=r.supplier_id
              LEFT JOIN centers c ON c.id=r.center_id
                         WHERE date(COALESCE({db_coalesce_text('r.doc_date','r.validated_at','r.created_at', cur_or_conn=cur)},'')) >= date(?)
                             AND date(COALESCE({db_coalesce_text('r.doc_date','r.validated_at','r.created_at', cur_or_conn=cur)},'')) < date(?)
               AND COALESCE(rl.price_unit,0) > 0
               {center_clause}
             ORDER BY LOWER(COALESCE(supplier_name,'')), LOWER(COALESCE(item_name,'')), event_date
            """,
            tuple(params),
        ).fetchall()
    except Exception:
        rows = []

    events: list[dict[str, Any]] = []
    missing_comparison: list[dict[str, Any]] = []
    supplier_groups: dict[str, dict[str, Any]] = {}
    recipes_map: dict[int, list[dict[str, Any]]] = {}

    for raw in rows:
        r = _rowdict(raw)
        item_id = int(r.get("item_id") or 0)
        supplier_id = int(r.get("supplier_id") or 0)
        current_price = _safe_price(r.get("price_unit"))
        if current_price <= 0 or not item_id or not supplier_id:
            continue
        prev_params: list[Any] = [item_id, supplier_id, start]
        prev_center_clause = ""
        if center_id:
            prev_center_clause = " AND pr.center_id=?"
            prev_params.append(int(center_id))
        try:
            prev = cur.execute(
                f"""
                SELECT COALESCE(pl.price_unit,0) price_unit,
                       COALESCE({db_coalesce_text('pr.doc_date','pr.validated_at','pr.created_at', cur_or_conn=cur)},'') event_date,
                       pr.id receipt_id, pr.doc_number
                  FROM receipt_lines pl
                  JOIN receipts pr ON pr.id=pl.receipt_id
                 WHERE pl.item_id=? AND pr.supplier_id=?
                   AND COALESCE(pl.price_unit,0) > 0
                   AND date(COALESCE({db_coalesce_text('pr.doc_date','pr.validated_at','pr.created_at', cur_or_conn=cur)},'')) < date(?)
                   {prev_center_clause}
                 ORDER BY date(COALESCE({db_coalesce_text('pr.doc_date','pr.validated_at','pr.created_at', cur_or_conn=cur)},'')) DESC, pr.id DESC
                 LIMIT 1
                """,
                tuple(prev_params),
            ).fetchone()
        except Exception:
            prev = None
        if not prev:
            missing_comparison.append({
                "item_id": item_id,
                "item_name": r.get("item_name") or "",
                "supplier_name": r.get("supplier_name") or "Sin proveedor",
                "current_price": current_price,
                "event_date": r.get("event_date") or "",
            })
            continue
        old_price = _safe_price(prev["price_unit"])
        if old_price <= 0:
            continue
        delta = current_price - old_price
        pct = (delta / old_price * 100.0) if old_price else 0.0
        month_qty = _month_qty_for_item_supplier(cur, item_id, supplier_id, start, end, center_id=center_id)
        estimated_impact = delta * month_qty
        recipes = recipes_map.get(item_id)
        if recipes is None:
            recipes = _recipes_using_item(cur, item_id)
            recipes_map[item_id] = recipes
        cheapest_alt = _cheapest_supplier_alternative(
            cur, item_id=item_id, current_supplier_id=supplier_id,
            current_unit_price=current_price, center_id=center_id, month_qty=month_qty,
        )
        payload = {
            "item_id": item_id,
            "item_name": r.get("item_name") or "",
            "base_unit": r.get("base_unit") or "",
            "supplier_id": supplier_id,
            "supplier_name": r.get("supplier_name") or "Sin proveedor",
            "center_name": r.get("center_name") or "",
            "old_price": old_price,
            "new_price": current_price,
            "delta_price": delta,
            "delta_pct": pct,
            "month_qty": month_qty,
            "estimated_month_impact": estimated_impact,
            "event_date": r.get("event_date") or "",
            "prev_date": prev["event_date"] if prev else "",
            "receipt_id": int(r.get("receipt_id") or 0),
            "doc_number": r.get("doc_number") or "",
            "affected_recipes": recipes,
            "cheapest_alternative": cheapest_alt,
            "severity": "SUBIDA" if delta > 0 else ("BAJADA" if delta < 0 else "IGUAL"),
        }
        events.append(payload)
        g = supplier_groups.setdefault(payload["supplier_name"], _new_supplier_group(payload["supplier_name"]))
        g["events"] += 1
        if delta > 0:
            g["increases"] += 1
            g["max_increase_pct"] = max(float(g["max_increase_pct"] or 0.0), pct)
            g["total_estimated_month_impact"] += max(0.0, estimated_impact)
        elif delta < 0:
            g["decreases"] += 1
        if abs(delta) > 0.000001:
            g["top_items"].append(payload)
            g["top_items"] = sorted(g["top_items"], key=lambda x: (float(x.get("delta_pct") or 0.0), float(x.get("estimated_month_impact") or 0.0)), reverse=True)[:6]
        for rec in recipes[:4]:
            key = (rec.get("id"), rec.get("name"))
            if not any((x.get("id"), x.get("name")) == key for x in g["affected_recipes"]):
                g["affected_recipes"].append(rec)
                g["affected_recipes"] = g["affected_recipes"][:8]

    conn.close()

    price_increases = [x for x in events if float(x.get("delta_price") or 0.0) > 0]
    price_decreases = [x for x in events if float(x.get("delta_price") or 0.0) < 0]
    top_increases = sorted(price_increases, key=lambda x: (float(x.get("delta_pct") or 0.0), float(x.get("estimated_month_impact") or 0.0)), reverse=True)[:10]
    top_impact = sorted(price_increases, key=lambda x: float(x.get("estimated_month_impact") or 0.0), reverse=True)[:10]
    top_expensive_items = sorted(events, key=lambda x: float(x.get("new_price") or 0.0), reverse=True)[:10]
    supplier_alternatives = sorted(
        [x for x in events if x.get("cheapest_alternative")],
        key=lambda x: (float((x.get("cheapest_alternative") or {}).get("estimated_month_saving") or 0.0), float((x.get("cheapest_alternative") or {}).get("saving_pct") or 0.0)),
        reverse=True,
    )[:12]
    suppliers_by_risk = sorted(supplier_groups.values(), key=lambda x: (float(x.get("total_estimated_month_impact") or 0.0), float(x.get("max_increase_pct") or 0.0)), reverse=True)
    suppliers_alpha = sorted(supplier_groups.values(), key=lambda x: str(x.get("name") or "").lower())
    affected_recipes: list[dict[str, Any]] = []
    seen_recipe_ids: set[int] = set()
    for ev in top_impact + top_increases:
        for rec in ev.get("affected_recipes") or []:
            rid = int(rec.get("id") or 0)
            if rid and rid not in seen_recipe_ids:
                rec2 = dict(rec)
                rec2["cause_item"] = ev.get("item_name")
                rec2["cause_supplier"] = ev.get("supplier_name")
                rec2["delta_pct"] = ev.get("delta_pct")
                rec2["estimated_month_impact"] = ev.get("estimated_month_impact")
                affected_recipes.append(rec2)
                seen_recipe_ids.add(rid)
    affected_recipes = affected_recipes[:12]

    recommendations = []
    if top_increases:
        recommendations.append("Revisar primero proveedores con mayor impacto mensual estimado, no solo mayor % de subida.")
    if missing_comparison:
        recommendations.append("Hay artículos sin histórico previo: no se puede confirmar subida hasta tener una compra anterior comparable.")
    if affected_recipes:
        recommendations.append("Priorizar recetas afectadas con food cost alto o precio de venta manual no actualizado.")
    if supplier_alternatives:
        recommendations.append("Revisar proveedor alternativo más barato solo si también cumple mínimos, días de reparto y plazo; no cambiar automáticamente sin validar calidad y formato.")
    if not recommendations:
        recommendations.append("Sin subidas comparables de proveedor en el periodo seleccionado.")

    return {
        "period": period,
        "start_date": start,
        "end_date": end,
        "has_data": bool(events or missing_comparison),
        "events_count": len(events),
        "increase_count": len(price_increases),
        "decrease_count": len(price_decreases),
        "missing_comparison_count": len(missing_comparison),
        "total_estimated_impact": sum(max(0.0, float(x.get("estimated_month_impact") or 0.0)) for x in price_increases),
        "suppliers_alpha": suppliers_alpha,
        "suppliers_by_risk": suppliers_by_risk[:10],
        "top_increases": top_increases,
        "top_impact": top_impact,
        "top_expensive_items": top_expensive_items,
        "supplier_alternatives": supplier_alternatives,
        "affected_recipes": affected_recipes,
        "missing_comparison": missing_comparison[:12],
        "recommendations": recommendations,
    }
