"""OÍDO ALFI · consultas operativas seguras.

Lectura pura para el asistente movible. No confirma pedidos, stock, recetas,
producciones ni mermas. Devuelve respuestas cortas y trazables para UI/voz.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta
from typing import Any

from app.core import db

_DAY_NAMES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _norm(value: Any) -> str:
    txt = str(value or "").strip().lower()
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    txt = re.sub(r"\s+", " ", txt)
    return txt


def _fmt_money(value: Any) -> str:
    try:
        v = float(value or 0)
    except Exception:
        v = 0.0
    return f"{v:.2f} €"


def _fmt_price(value: Any, unit: str = "") -> str:
    try:
        v = float(value or 0)
    except Exception:
        v = 0.0
    suffix = f"/{unit}" if unit else ""
    return f"{v:.3f} €{suffix}" if v and v < 1 else f"{v:.2f} €{suffix}"


def _rowdict(row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()} if row is not None and hasattr(row, "keys") else dict(row or {})


def _parse_delivery_days(raw: Any) -> set[int]:
    if raw is None:
        return set()
    s = _norm(raw)
    if not s:
        return set()
    aliases = {
        "lunes": 0, "lun": 0, "l": 0,
        "martes": 1, "mar": 1, "ma": 1,
        "miercoles": 2, "mie": 2, "mi": 2, "x": 2,
        "jueves": 3, "jue": 3, "j": 3,
        "viernes": 4, "vie": 4, "v": 4,
        "sabado": 5, "sab": 5, "s": 5,
        "domingo": 6, "dom": 6, "d": 6,
    }
    if "lunes-sabado" in s or "lun-sab" in s or "l-s" in s:
        return {0, 1, 2, 3, 4, 5}
    if "lunes-domingo" in s or "lunes-dom" in s or "todos" in s:
        return {0, 1, 2, 3, 4, 5, 6}
    out: set[int] = set()
    for token in re.split(r"[,;/|]+", s):
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


def _delivery_label(raw: Any) -> str:
    days = _parse_delivery_days(raw)
    return ", ".join(_DAY_NAMES[d] for d in sorted(days)) if days else "sin días de reparto configurados"


def _next_delivery(raw_days: Any, lead_time_days: Any = 0) -> str:
    days = _parse_delivery_days(raw_days)
    try:
        lead = max(0, int(float(lead_time_days or 0)))
    except Exception:
        lead = 0
    base = date.today() + timedelta(days=lead)
    if not days:
        return base.isoformat()
    for offset in range(0, 21):
        candidate = base + timedelta(days=offset)
        if candidate.weekday() in days:
            return candidate.isoformat()
    return ""


def _find_supplier(cur, name: str):
    key = _norm(name)
    if not key:
        return None
    rows = cur.execute(
        """SELECT id,name,phone,email,COALESCE(delivery_days,'') delivery_days,
                  COALESCE(delivery_min_order_amount,0) delivery_min_order_amount,
                  COALESCE(delivery_min_tax_mode,'ex_vat') delivery_min_tax_mode,
                  COALESCE(delivery_lead_time_days,0) delivery_lead_time_days,
                  COALESCE(delivery_notes,'') delivery_notes,
                  COALESCE(is_active,1) is_active
             FROM suppliers
            WHERE COALESCE(is_active,1)=1
            ORDER BY name"""
    ).fetchall()
    exact = [r for r in rows if _norm(r["name"]) == key]
    if exact:
        return exact[0]
    contains = [r for r in rows if key in _norm(r["name"]) or _norm(r["name"]) in key]
    if contains:
        return sorted(contains, key=lambda r: len(str(r["name"] or "")))[0]
    return None


def _find_item(cur, name: str):
    key = _norm(name)
    if not key:
        return None
    rows = cur.execute(
        """SELECT id,name,unit,min_qty,max_qty,current_price,stock_area,order_category,item_type
             FROM items ORDER BY name"""
    ).fetchall()
    exact = [r for r in rows if _norm(r["name"]) == key]
    if exact:
        return exact[0]
    contains = [r for r in rows if key in _norm(r["name"]) or _norm(r["name"]) in key]
    if contains:
        return sorted(contains, key=lambda r: len(str(r["name"] or "")))[0]
    # búsqueda por últimas palabras útiles: "de qué proveedor es el salmón" -> salmón
    tokens = [t for t in re.split(r"\W+", key) if len(t) >= 3]
    if tokens:
        scored = []
        for r in rows:
            n = _norm(r["name"])
            score = sum(1 for t in tokens if t in n)
            if score:
                scored.append((score, len(n), r))
        if scored:
            scored.sort(key=lambda x: (-x[0], x[1]))
            return scored[0][2]
    return None


def _extract_after_patterns(q: str, patterns: list[str]) -> str:
    nq = _norm(q)
    for p in patterns:
        m = re.search(p, nq)
        if m:
            val = (m.group(1) or "").strip(" .,:;¿?¡!")
            val = re.sub(r"^(el|la|los|las|un|una|de|del)\s+", "", val).strip()
            if val:
                return val
    # fallback: quita palabras de intención y conserva posible entidad
    stop = r"\b(oido|alfi|telefono|teléfono|mail|email|correo|proveedor|proveedores|insumo|insumos|articulo|artículo|producto|productos|reparto|dias|dias|mínimo|minimo|pedido|vende|venden|stock|hay|cuanto|cuánto|queda|quedan|tengo|tenemos|existencias|es|de|del|la|el|los|las|que|cual|cuál|quien|quién|dime|datos|contacto|tiene|cuales|cuáles)\b"
    val = re.sub(stop, " ", nq)
    val = re.sub(r"\s+", " ", val).strip()
    return val



def _extract_stock_item(q: str) -> str:
    nq = _norm(q)
    patterns = [
        r"(?:cuanto|cuánto)\s+(.+?)\s+(?:hay|queda|quedan|tengo|tenemos)(?:\s+en\s+stock)?",
        r"(?:hay|tenemos|tengo)\s+(.+?)\s+(?:en\s+stock|disponible|disponibles|queda|quedan)",
        r"(?:stock\s+de|cuanto queda de|cuánto queda de|existencias de)\s+(.+)$",
        r"(?:hay)\s+(.+)$",
    ]
    for pat in patterns:
        m = re.search(pat, nq)
        if m:
            val = (m.group(1) or "").strip(" .,:;¿?¡!")
            val = re.sub(r"\b(en|el|la|los|las|un|una|de|del|stock|cámara|camara|almacen|almacén|cocina|economato)\b", " ", val)
            val = re.sub(r"\s+", " ", val).strip()
            if val:
                return val
    return _extract_after_patterns(q, [r"(?:hay|stock de|cuanto queda de|cuánto queda de|tengo)\s+(.+)$"])

def _supplier_payload(row) -> dict[str, Any]:
    if not row:
        return {}
    d = _rowdict(row)
    days_label = _delivery_label(d.get("delivery_days"))
    next_delivery = _next_delivery(d.get("delivery_days"), d.get("delivery_lead_time_days"))
    return {
        "id": d.get("id"),
        "name": d.get("name") or "",
        "phone": d.get("phone") or "sin teléfono",
        "email": d.get("email") or "sin email",
        "delivery_days": d.get("delivery_days") or "",
        "delivery_days_label": days_label,
        "delivery_min_order_amount": float(d.get("delivery_min_order_amount") or 0),
        "delivery_min_tax_mode": d.get("delivery_min_tax_mode") or "ex_vat",
        "delivery_lead_time_days": int(float(d.get("delivery_lead_time_days") or 0)),
        "delivery_notes": d.get("delivery_notes") or "",
        "next_delivery_date": next_delivery,
    }


def _answer_supplier_info(cur, q: str) -> dict[str, Any]:
    name = _extract_after_patterns(q, [
        r"(?:telefono|teléfono|mail|email|correo|contacto|datos|reparto|dias de reparto|días de reparto|minimo|mínimo|condiciones|notas)\s+(?:de|del proveedor|proveedor)?\s+(.+)$",
        r"(?:proveedor)\s+(.+)$",
    ])
    sup = _find_supplier(cur, name)
    if not sup:
        return {"ok": False, "type": "supplier_info", "message": "No encuentro ese proveedor. Abro Catálogo para revisarlo.", "open_page": "admin", "tab": "proveedores"}
    s = _supplier_payload(sup)
    parts = [f"Proveedor {s['name']}."]
    if any(x in _norm(q) for x in ["telefono", "teléfono", "contacto", "datos"]):
        parts.append(f"Teléfono: {s['phone']}.")
    if any(x in _norm(q) for x in ["mail", "email", "correo", "contacto", "datos"]):
        parts.append(f"Email: {s['email']}.")
    if any(x in _norm(q) for x in ["reparto", "entrega", "dias", "días", "datos", "condiciones"]):
        parts.append(f"Reparte: {s['delivery_days_label']}.")
        if s["next_delivery_date"]:
            parts.append(f"Próximo reparto operativo: {s['next_delivery_date']}.")
    if any(x in _norm(q) for x in ["minimo", "mínimo", "datos", "condiciones"]):
        mode = "sin IVA" if s["delivery_min_tax_mode"] == "ex_vat" else "con IVA"
        min_txt = _fmt_money(s["delivery_min_order_amount"]) if s["delivery_min_order_amount"] else "sin mínimo configurado"
        parts.append(f"Mínimo: {min_txt} {mode if s['delivery_min_order_amount'] else ''}.")
    if s["delivery_lead_time_days"]:
        parts.append(f"Plazo: {s['delivery_lead_time_days']} día(s).")
    if s["delivery_notes"]:
        parts.append(f"Notas: {s['delivery_notes']}.")
    if len(parts) == 1:
        parts.extend([f"Teléfono: {s['phone']}.", f"Email: {s['email']}.", f"Reparte: {s['delivery_days_label']}."])
    return {"ok": True, "type": "supplier_info", "message": " ".join(parts), "supplier": s, "open_page": "admin", "tab": "proveedores"}


def _item_suppliers(cur, item_id: int, center_id: int = 0) -> list[dict[str, Any]]:
    rows = cur.execute(
        """SELECT sp.supplier_id, s.name supplier_name, s.phone, s.email,
                  COALESCE(s.delivery_days,'') delivery_days,
                  COALESCE(s.delivery_min_order_amount,0) delivery_min_order_amount,
                  COALESCE(s.delivery_min_tax_mode,'ex_vat') delivery_min_tax_mode,
                  COALESCE(s.delivery_lead_time_days,0) delivery_lead_time_days,
                  COALESCE(s.delivery_notes,'') delivery_notes,
                  sp.price_per_purchase, sp.purchase_unit, sp.purchase_to_base_factor,
                  COALESCE(sp.is_preferred,0) is_preferred, COALESCE(sp.updated_at,'') updated_at
             FROM supplier_item_prices sp
             JOIN suppliers s ON s.id=sp.supplier_id
            WHERE sp.item_id=? AND COALESCE(s.is_active,1)=1 AND (sp.center_id=? OR sp.center_id IS NULL OR ?=0)
            ORDER BY COALESCE(sp.is_preferred,0) DESC, sp.updated_at DESC, sp.price_per_purchase ASC""",
        (int(item_id), int(center_id or 0), int(center_id or 0)),
    ).fetchall()
    return [_rowdict(r) for r in rows]


def _answer_item_supplier(cur, q: str, center_id: int) -> dict[str, Any]:
    item_name = _extract_after_patterns(q, [
        r"(?:de que proveedor es|de qué proveedor es|que proveedor tiene|qué proveedor tiene|quien vende|quién vende|proveedor de|proveedor del|vende)\s+(.+)$",
        r"(?:insumo|articulo|artículo|producto)\s+(.+)$",
    ])
    item = _find_item(cur, item_name)
    if not item:
        return {"ok": False, "type": "item_supplier", "message": "No encuentro ese insumo en Catálogo. Abro Catálogo para revisarlo.", "open_page": "admin", "tab": "articulos"}
    prices = _item_suppliers(cur, int(item["id"]), center_id)
    item_d = _rowdict(item)
    if not prices:
        msg = f"{item_d['name']} no tiene proveedor vinculado en precios por proveedor. Precio actual de catálogo: {_fmt_money(item_d.get('current_price'))}. Conviene completar proveedor habitual."
        return {"ok": False, "type": "item_supplier", "message": msg, "item": item_d, "suppliers": [], "open_page": "admin", "tab": "precios"}
    preferred = prices[0]
    # Alternativa más barata comparable por precio/factor si existe
    def norm_base(p: dict[str, Any]) -> float:
        try:
            factor = float(p.get("purchase_to_base_factor") or 1)
            price = float(p.get("price_per_purchase") or 0)
            return price / factor if factor else price
        except Exception:
            return 0.0
    cheapest = sorted([p for p in prices if norm_base(p) > 0], key=norm_base)[0] if any(norm_base(p) > 0 for p in prices) else preferred
    parts = [f"{item_d['name']} está vinculado a {preferred.get('supplier_name')}."]
    if preferred.get("is_preferred"):
        parts.append("Figura como proveedor preferente.")
    parts.append(f"Último precio: {_fmt_price(preferred.get('price_per_purchase'), preferred.get('purchase_unit') or item_d.get('unit') or '')}.")
    parts.append(f"Reparto: {_delivery_label(preferred.get('delivery_days'))}.")
    min_amount = float(preferred.get("delivery_min_order_amount") or 0)
    if min_amount:
        mode = "sin IVA" if (preferred.get("delivery_min_tax_mode") or "ex_vat") == "ex_vat" else "con IVA"
        parts.append(f"Mínimo proveedor: {_fmt_money(min_amount)} {mode}.")
    if cheapest and int(cheapest.get("supplier_id") or 0) != int(preferred.get("supplier_id") or 0):
        parts.append(f"Proveedor alternativo más barato detectado: {cheapest.get('supplier_name')} ({_fmt_price(cheapest.get('price_per_purchase'), cheapest.get('purchase_unit') or item_d.get('unit') or '')}). Revisar calidad, mínimo y reparto antes de cambiar.")
    return {
        "ok": True,
        "type": "item_supplier",
        "message": " ".join(parts),
        "item": item_d,
        "supplier": preferred,
        "cheapest_supplier": cheapest,
        "suppliers": prices[:5],
        "open_page": "admin",
        "tab": "precios",
    }


def _answer_stock(cur, q: str, center_id: int) -> dict[str, Any]:
    item_name = _extract_stock_item(q)
    item = _find_item(cur, item_name)
    if not item:
        return {"ok": False, "type": "stock", "message": "No encuentro ese insumo. Abro Stock para buscarlo.", "open_page": "stock"}
    rows = cur.execute(
        """SELECT COALESCE(SUM(qty),0) qty
             FROM movements
            WHERE item_id=? AND (?=0 OR center_id=?)""",
        (int(item["id"]), int(center_id or 0), int(center_id or 0)),
    ).fetchone()
    qty = float(rows["qty"] or 0) if rows else 0.0
    unit = item["unit"] or ""
    msg = f"{item['name']}: stock teórico {qty:.2f} {unit}. Mínimo {float(item['min_qty'] or 0):.2f} {unit}; máximo {float(item['max_qty'] or 0):.2f} {unit}."
    if float(item["min_qty"] or 0) and qty < float(item["min_qty"] or 0):
        msg += " Está bajo mínimo; conviene revisar pedido sugerido."
    return {"ok": True, "type": "stock", "message": msg, "item": _rowdict(item), "stock_qty": qty, "open_page": "stock"}


def answer_oido_alfi(query: str, center_id: int = 0) -> dict[str, Any]:
    """Responde una consulta de OÍDO ALFI. Lectura pura."""
    q = query or ""
    nq = _norm(q)
    if not nq:
        return {"ok": False, "type": "empty", "message": "Escribe o dicta una consulta para OÍDO ALFI."}
    with db() as conn:
        cur = conn.cursor()
        # Intenciones de proveedor/insumo primero para no abrir Pedidos por la palabra proveedor.
        if any(x in nq for x in ["de que proveedor", "de qué proveedor", "proveedor de", "proveedor del", "quien vende", "quién vende", "que proveedor tiene", "qué proveedor tiene", "vende "]):
            return _answer_item_supplier(cur, q, int(center_id or 0))
        if any(x in nq for x in ["telefono", "teléfono", "mail", "email", "correo", "contacto", "dias de reparto", "días de reparto", "reparto", "minimo", "mínimo", "condiciones", "notas proveedor", "datos proveedor"]):
            return _answer_supplier_info(cur, q)
        if any(x in nq for x in ["hay ", "stock", "cuanto queda", "cuánto queda", "tengo "]):
            return _answer_stock(cur, q, int(center_id or 0))
    return {
        "ok": False,
        "type": "fallback",
        "message": "Puedo consultar proveedores, insumos, stock, mínimos y reparto; o abrir pedidos, mermas, producciones, recetas e inventario. No ejecuto cambios críticos sin revisión.",
        "ideas": [
            "¿de qué proveedor es salmón?",
            "teléfono de Negrini",
            "mínimo de La Huerta",
            "días de reparto de Pescadería Palacio",
            "¿hay aguacate en stock?",
        ],
    }
