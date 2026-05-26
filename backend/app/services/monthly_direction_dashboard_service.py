"""Dashboard mensual de dirección para inventario/conciliación.

Lee datos existentes sin modificar stock. Agrupa desviaciones de inventario cerrado
por proveedor, rubro y local para detectar pérdida económica operativa.
"""
from __future__ import annotations

from datetime import datetime, date
from typing import Any

from app.core import db, ensure_columns, _unit_factor, normalize_stock_area


def _rowdict(row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()} if row is not None and hasattr(row, "keys") else dict(row or {})


def _month_bounds(year: int | None = None, month: int | None = None) -> tuple[str, str, str]:
    today = date.today()
    y = int(year or today.year)
    m = int(month or today.month)
    if m < 1 or m > 12:
        y, m = today.year, today.month
    start = date(y, m, 1)
    if m == 12:
        end = date(y + 1, 1, 1)
    else:
        end = date(y, m + 1, 1)
    return start.isoformat(), end.isoformat(), f"{y:04d}-{m:02d}"


def _supplier_for_item(cur, item_id: int, center_id: int) -> dict[str, Any]:
    """Devuelve proveedor preferente/habitual si existe. No inventa proveedor."""
    try:
        row = cur.execute(
            """
            SELECT s.id supplier_id, s.name supplier_name
              FROM supplier_item_prices sp
              JOIN suppliers s ON s.id=sp.supplier_id
             WHERE sp.item_id=? AND (sp.center_id=? OR sp.center_id IS NULL OR sp.center_id=0)
             ORDER BY COALESCE(sp.is_preferred,0) DESC,
                      CASE WHEN sp.center_id=? THEN 0 ELSE 1 END,
                      datetime(COALESCE(sp.updated_at,'1970-01-01')) DESC,
                      sp.id DESC
             LIMIT 1
            """,
            (int(item_id or 0), int(center_id or 0), int(center_id or 0)),
        ).fetchone()
        if row:
            return {"supplier_id": int(row["supplier_id"] or 0), "supplier_name": row["supplier_name"] or ""}
    except Exception:
        pass
    return {"supplier_id": 0, "supplier_name": "Sin proveedor habitual"}


def _rubro_label(stock_area: str, family_key: str, source_type: str) -> str:
    area = normalize_stock_area(stock_area or "")
    fam = (family_key or "").strip().lower()
    stype = (source_type or "").strip().lower()
    if area == "FRESCOS":
        return "Frescos"
    if area == "SECOS":
        return "Secos"
    if area == "CONGELADOS":
        return "Congelados"
    if area == "LIMPIEZA":
        return "Limpieza"
    if area == "PREPARACIONES" or stype == "production" or "produccion" in fam or "producciones" in fam:
        return "Producciones"
    if area == "SIN_CLASIFICACION":
        return "Sin clasificación"
    if "limpieza" in fam:
        return "Limpieza"
    if "congel" in fam:
        return "Congelados"
    if "secos" in fam:
        return "Secos"
    if any(x in fam for x in ["verduras", "carnes", "pescados", "lacteos", "huevos"]):
        return "Frescos"
    return "Otros"


def _severity(diff_qty: float, theoretical_qty: float, value_abs: float) -> str:
    pct = 0.0
    if abs(theoretical_qty) > 0.000001:
        pct = abs(diff_qty) / abs(theoretical_qty) * 100.0
    if value_abs >= 100 or pct >= 20:
        return "CRITICA"
    if value_abs >= 40 or pct >= 10:
        return "ALTA"
    if value_abs >= 10 or pct >= 3:
        return "MEDIA"
    return "BAJA"


def _new_group(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "lines": 0,
        "loss_value": 0.0,
        "surplus_value": 0.0,
        "net_value": 0.0,
        "critical_lines": 0,
        "medium_or_more_lines": 0,
        "top_items": [],
    }


def _add_to_group(group: dict[str, Any], item_payload: dict[str, Any]) -> None:
    group["lines"] += 1
    diff_value = float(item_payload.get("diff_value") or 0.0)
    if diff_value < 0:
        group["loss_value"] += abs(diff_value)
    else:
        group["surplus_value"] += diff_value
    group["net_value"] += diff_value
    sev = str(item_payload.get("severity") or "")
    if sev == "CRITICA":
        group["critical_lines"] += 1
    if sev in {"MEDIA", "ALTA", "CRITICA"}:
        group["medium_or_more_lines"] += 1
    if abs(diff_value) > 0.000001:
        group["top_items"].append(item_payload)
        group["top_items"] = sorted(group["top_items"], key=lambda x: abs(float(x.get("diff_value") or 0.0)), reverse=True)[:5]


def _safe_date(value: str | None) -> date | None:
    try:
        if not value:
            return None
        return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def build_monthly_direction_dashboard(center_id: int | None = None, year: int | None = None, month: int | None = None, day: int | None = None, start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    """Construye un resumen de dirección sin efectos secundarios.

    Usa inventarios cerrados del periodo/rango y calcula la diferencia entre teórico y físico.
    Si no hay inventarios cerrados, devuelve estructura vacía y mensaje claro.
    """
    start, end, period = _month_bounds(year, month)
    import datetime as _dt
    visible_start = start
    try:
        visible_end = (_safe_date(end) - _dt.timedelta(days=1)).isoformat()
    except Exception:
        visible_end = start
    mode = "month"
    day_value = None
    range_start = _safe_date(start_date)
    range_end = _safe_date(end_date)
    if range_start or range_end:
        if not range_start:
            range_start = range_end
        if not range_end:
            range_end = range_start
        if range_start and range_end and range_end < range_start:
            range_start, range_end = range_end, range_start
        start = range_start.isoformat()
        # consulta SQL usa límite superior exclusivo: sumamos un día al hasta visible
        end_exclusive = range_end + _dt.timedelta(days=1)
        end = end_exclusive.isoformat()
        visible_start = range_start.isoformat()
        visible_end = range_end.isoformat()
        period = f"{range_start.isoformat()} a {range_end.isoformat()}"
        mode = "range"
    elif day is not None:
        try:
            import datetime as _dt
            y = int(year or period[:4])
            m = int(month or period[5:7])
            d = int(day)
            selected_day = _dt.date(y, m, d)
            start = selected_day.isoformat()
            end = (selected_day + _dt.timedelta(days=1)).isoformat()
            visible_start = selected_day.isoformat()
            visible_end = selected_day.isoformat()
            period = selected_day.isoformat()
            mode = "day"
            day_value = d
        except Exception:
            mode = "month"
            day_value = None
    conn = db(); cur = conn.cursor(); ensure_columns(cur)
    params: list[Any] = [start, end]
    center_clause = ""
    if center_id:
        center_clause = " AND s.center_id=?"
        params.append(int(center_id))
    try:
        rows = cur.execute(
            f"""
            SELECT s.id session_id, s.center_id, c.name center_name, s.warehouse_id session_warehouse_id,
                   s.status, s.created_at session_created_at, COALESCE(s.responsible_name,'') responsible_name,
                   ic.id count_id, ic.source_type, ic.item_id, COALESCE(ic.item_name, i.name, '') item_name,
                   COALESCE(ic.family_key,'') family_key, ic.warehouse_id, COALESCE(w.name,'') warehouse_name,
                   COALESCE(ic.theoretical_qty,0) theoretical_qty, COALESCE(ic.physical_qty,0) physical_qty,
                   COALESCE(ic.count_unit, i.unit, 'ud') count_unit,
                   COALESCE(ic.unit_cost_snapshot, i.current_price, 0) unit_cost,
                   COALESCE(i.unit, ic.count_unit, 'ud') base_unit,
                   COALESCE(i.stock_area,'') stock_area,
                   COALESCE(ic.note,'') note
              FROM inventory_sessions s
              JOIN inventory_counts ic ON ic.session_id=s.id
              LEFT JOIN centers c ON c.id=s.center_id
              LEFT JOIN warehouses w ON w.id=ic.warehouse_id
              LEFT JOIN items i ON i.id=ic.item_id
             WHERE UPPER(COALESCE(s.status,''))='CLOSED'
               AND date(COALESCE(s.created_at,'')) >= date(?)
               AND date(COALESCE(s.created_at,'')) < date(?)
               AND COALESCE(ic.is_checked,0)=1
               {center_clause}
             ORDER BY c.name COLLATE NOCASE, ic.item_name COLLATE NOCASE
            """,
            tuple(params),
        ).fetchall()
    except Exception:
        rows = []

    suppliers: dict[str, dict[str, Any]] = {}
    rubros: dict[str, dict[str, Any]] = {}
    centers: dict[str, dict[str, Any]] = {}
    lines: list[dict[str, Any]] = []
    missing_supplier = 0
    missing_rubro = 0

    for raw in rows:
        r = _rowdict(raw)
        item_id = int(r.get("item_id") or 0)
        center = str(r.get("center_name") or f"Local {int(r.get('center_id') or 0)}")
        base_unit = str(r.get("base_unit") or r.get("count_unit") or "ud").strip() or "ud"
        count_unit = str(r.get("count_unit") or base_unit).strip() or base_unit
        try:
            factor = float(_unit_factor(count_unit, base_unit) or 1.0)
        except Exception:
            factor = 1.0
        theoretical_qty = float(r.get("theoretical_qty") or 0.0)
        physical_base = float(r.get("physical_qty") or 0.0) * factor
        diff_qty = physical_base - theoretical_qty
        unit_cost = float(r.get("unit_cost") or 0.0)
        diff_value = diff_qty * unit_cost
        if abs(diff_qty) <= 0.000001 and abs(diff_value) <= 0.000001:
            continue
        supplier = _supplier_for_item(cur, item_id, int(r.get("center_id") or 0)) if item_id else {"supplier_id": 0, "supplier_name": "Sin proveedor habitual"}
        supplier_name = (supplier.get("supplier_name") or "Sin proveedor habitual").strip() or "Sin proveedor habitual"
        rubro = _rubro_label(str(r.get("stock_area") or ""), str(r.get("family_key") or ""), str(r.get("source_type") or ""))
        if supplier_name == "Sin proveedor habitual":
            missing_supplier += 1
        if rubro in {"Otros", "Sin clasificación"}:
            missing_rubro += 1
        severity = _severity(diff_qty, theoretical_qty, abs(diff_value))
        payload = {
            "session_id": int(r.get("session_id") or 0),
            "center_name": center,
            "warehouse_name": r.get("warehouse_name") or "",
            "supplier_name": supplier_name,
            "rubro": rubro,
            "item_id": item_id,
            "item_name": r.get("item_name") or "",
            "base_unit": base_unit,
            "theoretical_qty": theoretical_qty,
            "physical_qty_base": physical_base,
            "diff_qty": diff_qty,
            "unit_cost": unit_cost,
            "diff_value": diff_value,
            "severity": severity,
            "responsible_name": r.get("responsible_name") or "",
            "note": r.get("note") or "",
        }
        lines.append(payload)
        suppliers.setdefault(supplier_name, _new_group(supplier_name))
        rubros.setdefault(rubro, _new_group(rubro))
        centers.setdefault(center, _new_group(center))
        _add_to_group(suppliers[supplier_name], payload)
        _add_to_group(rubros[rubro], payload)
        _add_to_group(centers[center], payload)

    conn.close()

    def _sorted_groups(groups: dict[str, dict[str, Any]], alphabetical: bool = False) -> list[dict[str, Any]]:
        vals = list(groups.values())
        if alphabetical:
            return sorted(vals, key=lambda x: str(x.get("name") or "").lower())
        return sorted(vals, key=lambda x: (float(x.get("loss_value") or 0.0), abs(float(x.get("net_value") or 0.0))), reverse=True)

    total_loss = sum(abs(float(x.get("diff_value") or 0.0)) for x in lines if float(x.get("diff_value") or 0.0) < 0)
    total_surplus = sum(float(x.get("diff_value") or 0.0) for x in lines if float(x.get("diff_value") or 0.0) > 0)
    total_net = total_surplus - total_loss
    critical = [x for x in lines if x.get("severity") in {"ALTA", "CRITICA"}]
    top_losses = sorted([x for x in lines if float(x.get("diff_value") or 0.0) < 0], key=lambda x: float(x.get("diff_value") or 0.0))[:10]
    top_surpluses = sorted([x for x in lines if float(x.get("diff_value") or 0.0) > 0], key=lambda x: float(x.get("diff_value") or 0.0), reverse=True)[:10]

    recommendations = []
    if total_loss > 0:
        recommendations.append("Revisar primero los grupos con pérdida neta: son salida económica no explicada o consumo no registrado.")
    if missing_supplier:
        recommendations.append("Completar proveedor habitual en artículos sin proveedor para poder atribuir desviaciones.")
    if missing_rubro:
        recommendations.append("Clasificar artículos sin rubro para que el informe no oculte pérdidas en 'Otros'.")
    if critical:
        recommendations.append("Exigir causa operativa en diferencias ALTA/CRÍTICA antes de aceptar el cierre como válido.")
    if not recommendations:
        recommendations.append("Sin desviaciones relevantes en inventarios cerrados del periodo.")

    return {
        "period": period,
        "mode": mode,
        "day": day_value,
        "start_date": visible_start,
        "end_date": end,
        "range_start": visible_start,
        "range_end": visible_end,
        "has_data": bool(lines),
        "total_lines": len(lines),
        "total_loss": total_loss,
        "total_surplus": total_surplus,
        "total_net": total_net,
        "critical_count": len(critical),
        "missing_supplier_count": missing_supplier,
        "missing_rubro_count": missing_rubro,
        "by_supplier_alpha": _sorted_groups(suppliers, alphabetical=True),
        "by_supplier_risk": _sorted_groups(suppliers, alphabetical=False)[:8],
        "by_rubro_alpha": _sorted_groups(rubros, alphabetical=True),
        "by_rubro_risk": _sorted_groups(rubros, alphabetical=False)[:8],
        "by_center_risk": _sorted_groups(centers, alphabetical=False)[:8],
        "top_losses": top_losses,
        "top_surpluses": top_surpluses,
        "critical_lines": sorted(critical, key=lambda x: abs(float(x.get("diff_value") or 0.0)), reverse=True)[:10],
        "recommendations": recommendations,
    }
