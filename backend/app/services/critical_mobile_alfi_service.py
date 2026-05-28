"""Capa LAB segura para flujos críticos móviles y OÍDO ALFI.

No mueve stock productivo ni confirma operaciones críticas. Crea propuestas/borradores
con prelectura, impacto y confirmación registrada para futura conexión productiva.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from typing import Any

from app.core import db, ensure_columns, safe_insert_returning


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def _norm(txt: str) -> str:
    import unicodedata
    s = (txt or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip()


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(str(value).replace(",", ".").strip())
    except Exception:
        return default


def ensure_critical_flow_schema(cur: sqlite3.Cursor) -> None:
    # Schema for critical mobile ALFI flows is managed by backend/migrate.py.
    # Avoid runtime DDL in the service module; run migrations as an administrative step.
    return


def _insert_draft(cur, flow_type: str, title: str, payload: dict, impact: dict, source_channel: str = "mobile", actor: str = "Sistema Demo") -> int:
    sqlite_sql = """INSERT INTO critical_flow_drafts(flow_type,source_channel,status,title,payload_json,impact_json,created_by,created_at)
           VALUES(?,?,?,?,?,?,?,?)"""
    pg_sql = sqlite_sql.replace('?', '%s')
    draft_id = safe_insert_returning(
        cur,
        sqlite_sql,
        (flow_type, source_channel, "draft_preview", title, json.dumps(payload, ensure_ascii=False), json.dumps(impact, ensure_ascii=False), actor, _now()),
        pg_sql=pg_sql,
    ) or 0
    cur.execute(
        """INSERT INTO critical_flow_audit(draft_id,flow_type,action,actor,note,before_json,after_json,created_at)
           VALUES(?,?,?,?,?,?,?,?)""",
        (draft_id, flow_type, "create_preview", actor, "Propuesta creada sin tocar stock productivo", "{}", json.dumps({"payload": payload, "impact": impact}, ensure_ascii=False), _now()),
    )
    return draft_id


def simulate_validation_correction(cur, actor: str = "Sistema Demo", source_channel: str = "mobile") -> dict[str, Any]:
    payload = {
        "module": "producciones",
        "record_label": "Producción Pico de gallo · ayer",
        "reason": "cantidad_incorrecta",
        "before": {"Tomate": {"qty": 5, "unit": "kg"}},
        "after": {"Tomate": {"qty": 3, "unit": "kg"}},
    }
    impact = {
        "stock_preview": [{"item": "Tomate", "movement": "+2 kg devueltos a Stock Cocina"}],
        "cost_preview": "se recalcularía el coste real de la producción corregida",
        "requires_human_confirmation": True,
        "productive_commit": False,
    }
    did = _insert_draft(cur, "validation_correction", "Corregir producción validada", payload, impact, source_channel, actor)
    return {"ok": True, "draft_id": did, "flow_type": "validation_correction", "title": "Corregir producción validada", "payload": payload, "impact": impact, "message": "Corrección simulada. No se ha movido stock productivo."}


def simulate_order_suggestions(cur, actor: str = "Sistema Demo", source_channel: str = "mobile") -> dict[str, Any]:
    sqlite_sql = "INSERT INTO order_suggestion_review_runs(title,status,source_channel,created_by,created_at) VALUES(?,?,?,?,?)"
    pg_sql = sqlite_sql.replace('?', '%s')
    run_id = safe_insert_returning(
        cur,
        sqlite_sql,
        ("Revisión pedido sugerido editable LAB", "draft_preview", source_channel, actor, _now()),
        pg_sql=pg_sql,
    ) or 0
    lines = [
        {"item_name": "Tomate", "area": "cocina", "supplier_name": "Proveedor Demo", "suggested_qty": 16, "final_qty": 20, "unit": "kg", "priority": "alta", "note": "fin de semana fuerte", "was_modified": 1, "modification_reason": "Ajuste por previsión de ventas"},
        {"item_name": "Lima", "area": "barra", "supplier_name": "Proveedor Demo", "suggested_qty": 4.2, "final_qty": 4.2, "unit": "kg", "priority": "normal", "note": "pedido consolidable", "was_modified": 0, "modification_reason": ""},
        {"item_name": "Perejil", "area": "cocina", "supplier_name": "Proveedor Demo", "suggested_qty": 1, "final_qty": 0, "unit": "manojo", "priority": "baja", "note": "quitado por stock suficiente", "accepted": 0, "was_modified": 1, "modification_reason": "Línea retirada"},
    ]
    for l in lines:
        cur.execute(
            """INSERT INTO order_suggestion_review_lines(run_id,item_name,area,supplier_name,suggested_qty,final_qty,unit,priority,note,accepted,was_modified,modification_reason)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (run_id, l["item_name"], l["area"], l["supplier_name"], l["suggested_qty"], l["final_qty"], l["unit"], l["priority"], l["note"], int(l.get("accepted", 1)), int(l.get("was_modified", 0)), l.get("modification_reason", "")),
        )
    payload = {"run_id": run_id, "lines": lines}
    impact = {"order_preview": "se generaría pedido revisado con desglose original/final", "requires_human_confirmation": True, "productive_commit": False}
    did = _insert_draft(cur, "editable_order_suggestions", "Pedido sugerido editable", payload, impact, source_channel, actor)
    return {"ok": True, "draft_id": did, "run_id": run_id, "flow_type": "editable_order_suggestions", "title": "Pedido sugerido editable", "payload": payload, "impact": impact, "message": "Pedido sugerido simulado con líneas editables. No se ha generado pedido real."}


def simulate_portioning(cur, actor: str = "Sistema Demo", source_channel: str = "mobile") -> dict[str, Any]:
    gross = 10.0
    waste = 1.2
    net = gross - waste
    total_cost = 180.0
    cost_per_kg = total_cost / net if net else 0
    lot = "ATUN-LAB-" + datetime.utcnow().strftime("%Y%m%d%H%M%S")
    sqlite_sql = """INSERT INTO portioning_batches(origin_item_name,gross_qty,unit,waste_qty,net_qty,total_cost,cost_per_net_unit,lot_code,responsible,status,source_channel,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)"""
    pg_sql = sqlite_sql.replace('?', '%s')
    batch_id = safe_insert_returning(
        cur,
        sqlite_sql,
        ("Atún pieza", gross, "kg", waste, net, total_cost, cost_per_kg, lot, actor, "draft_preview", source_channel, _now()),
        pg_sql=pg_sql,
    ) or 0
    outputs = [
        {"destination_name": "Tataki", "qty": 4.0, "linked_recipe_name": "Tataki de atún"},
        {"destination_name": "Tartar", "qty": 3.0, "linked_recipe_name": "Tartar de atún"},
        {"destination_name": "Especiales", "qty": 1.8, "linked_recipe_name": "Fuera de carta"},
    ]
    for o in outputs:
        cost = _f(o["qty"]) * cost_per_kg
        o["cost_assigned"] = round(cost, 2)
        cur.execute(
            """INSERT INTO portioning_outputs(batch_id,destination_name,destination_type,qty,unit,cost_assigned,linked_recipe_name)
               VALUES(?,?,?,?,?,?,?)""",
            (batch_id, o["destination_name"], "preparacion", o["qty"], "kg", o["cost_assigned"], o["linked_recipe_name"]),
        )
    payload = {"batch_id": batch_id, "origin_item_name": "Atún pieza", "gross_qty": gross, "unit": "kg", "waste_qty": waste, "net_qty": net, "total_cost": total_cost, "cost_per_net_unit": round(cost_per_kg, 4), "lot_code": lot, "outputs": outputs}
    impact = {"stock_preview": ["Stock Atún pieza -10 kg", "Merma/descarte +1,2 kg", "Stock interno porciones +8,8 kg"], "cost_preview": f"coste útil {cost_per_kg:.2f} €/kg", "requires_human_confirmation": True, "productive_commit": False}
    did = _insert_draft(cur, "portioning", "Racionado de pieza de atún", payload, impact, source_channel, actor)
    return {"ok": True, "draft_id": did, "batch_id": batch_id, "flow_type": "portioning", "title": "Racionado de pieza de atún", "payload": payload, "impact": impact, "message": "Racionado simulado. No se ha movido stock productivo."}


def simulate_all_critical_flows() -> dict[str, Any]:
    conn = db(); cur = conn.cursor(); ensure_critical_flow_schema(cur)
    try:
        correction = simulate_validation_correction(cur)
        orders = simulate_order_suggestions(cur)
        portioning = simulate_portioning(cur)
        conn.commit()
        return {
            "ok": True,
            "message": "Simulacro completo creado en modo LAB seguro.",
            "conclusions": [
                "Hay datos suficientes para implementar la capa de prelectura móvil y ALFI sin tocar stock productivo.",
                "Correcciones, pedidos editables y racionado deben entrar primero como borradores con impacto visible.",
                "La confirmación productiva real debe conectarse módulo por módulo después de validar reversos y permisos.",
            ],
            "results": [correction, orders, portioning],
        }
    except Exception as exc:
        conn.rollback()
        return {"ok": False, "message": str(exc)}
    finally:
        conn.close()


def list_critical_flow_summary() -> dict[str, Any]:
    conn = db(); cur = conn.cursor(); ensure_critical_flow_schema(cur)
    try:
        counts = {}
        for flow in ["validation_correction", "editable_order_suggestions", "portioning", "alfi_preview"]:
            row = cur.execute("SELECT COUNT(*) c FROM critical_flow_drafts WHERE flow_type=?", (flow,)).fetchone()
            counts[flow] = int(row["c"] if row else 0)
        drafts = [dict(r) for r in cur.execute(
            """SELECT id,flow_type,source_channel,status,title,created_by,created_at,requires_confirmation,confirmed_by,confirmed_at
                 FROM critical_flow_drafts ORDER BY id DESC LIMIT 10"""
        ).fetchall()]
        for d in drafts:
            row = cur.execute("SELECT payload_json,impact_json FROM critical_flow_drafts WHERE id=?", (d["id"],)).fetchone()
            try: d["payload"] = json.loads(row["payload_json"] or "{}") if row else {}
            except Exception: d["payload"] = {}
            try: d["impact"] = json.loads(row["impact_json"] or "{}") if row else {}
            except Exception: d["impact"] = {}
        return {"ok": True, "counts": counts, "drafts": drafts, "rules": ["Móvil y ALFI crean la misma propuesta", "Nada crítico se ejecuta sin prelectura y confirmación", "Todo queda auditado con usuario/hora/motivo"]}
    finally:
        conn.close()


def confirm_critical_draft(draft_id: int, actor: str = "Sistema Demo", note: str = "Confirmación LAB") -> dict[str, Any]:
    conn = db(); cur = conn.cursor(); ensure_critical_flow_schema(cur)
    try:
        row = cur.execute("SELECT * FROM critical_flow_drafts WHERE id=?", (int(draft_id),)).fetchone()
        if not row:
            return {"ok": False, "message": "No existe ese borrador."}
        cur.execute("UPDATE critical_flow_drafts SET status=?, confirmed_by=?, confirmed_at=?, confirmation_note=? WHERE id=?", ("confirmed_preview", actor, _now(), note, int(draft_id)))
        cur.execute(
            "INSERT INTO critical_flow_audit(draft_id,flow_type,action,actor,note,before_json,after_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (int(draft_id), row["flow_type"], "confirm_preview", actor, note, "{}", json.dumps({"status": "confirmed_preview", "productive_commit": False}, ensure_ascii=False), _now()),
        )
        conn.commit()
        return {"ok": True, "message": "Confirmación LAB registrada. No se ha movido stock productivo.", "draft_id": int(draft_id)}
    except Exception as exc:
        conn.rollback()
        return {"ok": False, "message": str(exc)}
    finally:
        conn.close()


def alfi_critical_preview(text: str, actor: str = "ALFI LAB") -> dict[str, Any]:
    """Interpreta texto/voz y crea una propuesta segura."""
    q = _norm(text)
    conn = db(); cur = conn.cursor(); ensure_critical_flow_schema(cur)
    try:
        if any(x in q for x in ["racion", "porcion", "despiece", "atun", "pieza"]):
            res = simulate_portioning(cur, actor=actor, source_channel="alfi")
        elif any(x in q for x in ["pedido", "sugerido", "cambia", "quita"]):
            res = simulate_order_suggestions(cur, actor=actor, source_channel="alfi")
        elif any(x in q for x in ["corrige", "corregir", "anula", "validacion", "validado", "produccion"]):
            res = simulate_validation_correction(cur, actor=actor, source_channel="alfi")
        else:
            payload = {"raw_text": text, "missing_fields": ["tipo de acción", "artículo/registro", "cantidad"]}
            impact = {"requires_clarification": True, "productive_commit": False}
            did = _insert_draft(cur, "alfi_preview", "ALFI necesita aclaración", payload, impact, "alfi", actor)
            res = {"ok": True, "draft_id": did, "flow_type": "alfi_preview", "title": "ALFI necesita aclaración", "payload": payload, "impact": impact, "message": "No ejecuto nada. Necesito más datos para preparar una propuesta."}
        conn.commit()
        res["alfi_rule"] = "ALFI solo crea prelectura; no ejecuta cambios críticos sin confirmación humana."
        return res
    except Exception as exc:
        conn.rollback()
        return {"ok": False, "message": str(exc)}
    finally:
        conn.close()
