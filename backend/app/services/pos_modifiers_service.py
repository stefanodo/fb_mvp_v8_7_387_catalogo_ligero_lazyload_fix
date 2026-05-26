"""TPV · modificadores de receta para consumo realista.

Capa preparada, sin acoplar ningún TPV concreto y sin modificar recetas maestras.
La receta base sigue siendo el estándar; los modificadores son deltas de consumo
por venta: SIN, EXTRA, SUSTITUIR, GUARNICIÓN o NO_STOCK.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any

from app.core import db, ensure_columns, _convert_qty


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


def normalize_modifier_name(value: str) -> str:
    """Normaliza nombres que pueden venir distintos según el TPV."""
    text = (value or "").strip().upper()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^A-Z0-9]+", "_", text).strip("_")
    return text or "SIN_MODIFICADOR"


def ensure_pos_modifier_tables(cur) -> None:
    """Migración aditiva; se puede llamar varias veces."""
    cur.execute("""
    CREATE TABLE IF NOT EXISTS recipe_modifiers(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      recipe_id INTEGER NOT NULL DEFAULT 0,
      code TEXT NOT NULL DEFAULT '',
      name TEXT NOT NULL DEFAULT '',
      modifier_type TEXT NOT NULL DEFAULT 'REVIEW',
      action TEXT NOT NULL DEFAULT 'REVIEW',
      item_id INTEGER NOT NULL DEFAULT 0,
      subrecipe_id INTEGER NOT NULL DEFAULT 0,
      qty_delta_base REAL NOT NULL DEFAULT 0,
      unit_base TEXT NOT NULL DEFAULT 'g',
      price_extra REAL NOT NULL DEFAULT 0,
      affects_stock INTEGER NOT NULL DEFAULT 1,
      confidence TEXT NOT NULL DEFAULT 'MANUAL',
      notes TEXT NOT NULL DEFAULT '',
      is_active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS pos_modifier_map(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      provider_name TEXT NOT NULL DEFAULT '',
      business_type TEXT NOT NULL DEFAULT '',
      pos_modifier_name TEXT NOT NULL DEFAULT '',
      normalized_code TEXT NOT NULL DEFAULT '',
      recipe_id INTEGER NOT NULL DEFAULT 0,
      modifier_id INTEGER NOT NULL DEFAULT 0,
      action_status TEXT NOT NULL DEFAULT 'ACTIVE',
      notes TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS pos_sales_modifier_daily(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      center_id INTEGER NOT NULL DEFAULT 0,
      sale_date TEXT NOT NULL,
      recipe_id INTEGER NOT NULL DEFAULT 0,
      recipe_name TEXT NOT NULL DEFAULT '',
      pos_item_code TEXT NOT NULL DEFAULT '',
      pos_item_name TEXT NOT NULL DEFAULT '',
      pos_modifier_name TEXT NOT NULL DEFAULT '',
      normalized_modifier_code TEXT NOT NULL DEFAULT '',
      modifier_id INTEGER NOT NULL DEFAULT 0,
      qty_sold REAL NOT NULL DEFAULT 0,
      channel TEXT NOT NULL DEFAULT '',
      business_type TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'REQUIERE_MAPEO',
      confidence TEXT NOT NULL DEFAULT 'LOW',
      source TEXT NOT NULL DEFAULT 'manual',
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS pos_modifier_consumption_audit(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      center_id INTEGER NOT NULL DEFAULT 0,
      sale_date TEXT NOT NULL,
      recipe_id INTEGER NOT NULL DEFAULT 0,
      modifier_id INTEGER NOT NULL DEFAULT 0,
      item_id INTEGER NOT NULL DEFAULT 0,
      subrecipe_id INTEGER NOT NULL DEFAULT 0,
      qty_delta_base REAL NOT NULL DEFAULT 0,
      unit_base TEXT NOT NULL DEFAULT 'g',
      status TEXT NOT NULL DEFAULT 'PREVIEW',
      reason TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS pos_modifier_review_queue(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      center_id INTEGER NOT NULL DEFAULT 0,
      sale_date TEXT NOT NULL DEFAULT (date('now')),
      recipe_id INTEGER NOT NULL DEFAULT 0,
      recipe_name TEXT NOT NULL DEFAULT '',
      pos_item_name TEXT NOT NULL DEFAULT '',
      raw_customer_note TEXT NOT NULL DEFAULT '',
      normalized_note TEXT NOT NULL DEFAULT '',
      suggested_status TEXT NOT NULL DEFAULT 'REQUIERE_MAPEO',
      suggested_action TEXT NOT NULL DEFAULT '',
      suggested_delta_json TEXT NOT NULL DEFAULT '',
      confidence_score REAL NOT NULL DEFAULT 0,
      review_status TEXT NOT NULL DEFAULT 'PENDIENTE',
      learned_modifier_id INTEGER NOT NULL DEFAULT 0,
      notes TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT (datetime('now')),
      updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)
    # Índices ligeros para dashboard/mes sin bloquear versiones antiguas.
    for sql in [
        "CREATE INDEX IF NOT EXISTS idx_recipe_modifiers_recipe ON recipe_modifiers(recipe_id,is_active)",
        "CREATE INDEX IF NOT EXISTS idx_pos_modifier_map_norm ON pos_modifier_map(normalized_code,recipe_id,action_status)",
        "CREATE INDEX IF NOT EXISTS idx_pos_sales_modifier_period ON pos_sales_modifier_daily(sale_date,center_id,recipe_id)",
        "CREATE INDEX IF NOT EXISTS idx_pos_modifier_review_status ON pos_modifier_review_queue(review_status,recipe_id,created_at)",
    ]:
        try:
            cur.execute(sql)
        except Exception:
            pass


def _month_bounds(year: int | None = None, month: int | None = None) -> tuple[str, str, str]:
    today = date.today()
    y = int(year or today.year)
    m = int(month or today.month)
    if m < 1 or m > 12:
        y, m = today.year, today.month
    start = date(y, m, 1)
    end = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return start.isoformat(), end.isoformat(), f"{y:04d}-{m:02d}"


def resolve_modifier(cur, recipe_id: int, pos_modifier_name: str, provider_name: str = "") -> dict[str, Any]:
    """Devuelve el modificador interno si hay mapeo. Nunca inventa consumo."""
    ensure_pos_modifier_tables(cur)
    norm = normalize_modifier_name(pos_modifier_name)
    row = cur.execute(
        """
        SELECT m.modifier_id, rm.*
          FROM pos_modifier_map m
          JOIN recipe_modifiers rm ON rm.id=m.modifier_id
         WHERE m.normalized_code=?
           AND (m.recipe_id=? OR m.recipe_id=0)
           AND m.action_status='ACTIVE'
           AND rm.is_active=1
         ORDER BY CASE WHEN m.recipe_id=? THEN 0 ELSE 1 END, m.id DESC
         LIMIT 1
        """,
        (norm, int(recipe_id or 0), int(recipe_id or 0)),
    ).fetchone()
    if row:
        d = _rowdict(row)
        d["status"] = "CONSUMO_EXACTO" if _safe_int(d.get("affects_stock")) else "IGNORADO_NO_STOCK"
        d["normalized_code"] = norm
        return d
    return {
        "id": 0,
        "recipe_id": int(recipe_id or 0),
        "code": norm,
        "name": pos_modifier_name,
        "modifier_type": "REVIEW",
        "action": "REQUIERE_MAPEO",
        "item_id": 0,
        "subrecipe_id": 0,
        "qty_delta_base": 0.0,
        "unit_base": "g",
        "affects_stock": 0,
        "status": "REQUIERE_MAPEO",
        "confidence": "LOW",
        "normalized_code": norm,
    }


def build_modifier_delta(cur, recipe_id: int, pos_modifier_name: str, qty_sold: float = 1.0) -> dict[str, Any]:
    """Calcula delta de consumo para una venta. Lectura pura; no mueve stock."""
    mod = resolve_modifier(cur, recipe_id, pos_modifier_name)
    qty = _safe_float(qty_sold) or 1.0
    delta = _safe_float(mod.get("qty_delta_base")) * qty
    return {
        "recipe_id": int(recipe_id or 0),
        "modifier_id": _safe_int(mod.get("id")),
        "modifier_name": mod.get("name") or pos_modifier_name,
        "normalized_code": mod.get("normalized_code") or normalize_modifier_name(pos_modifier_name),
        "status": mod.get("status") or "REQUIERE_MAPEO",
        "action": mod.get("action") or "REQUIERE_MAPEO",
        "item_id": _safe_int(mod.get("item_id")),
        "subrecipe_id": _safe_int(mod.get("subrecipe_id")),
        "qty_delta_base": delta,
        "unit_base": mod.get("unit_base") or "g",
        "confidence": mod.get("confidence") or "LOW",
        "affects_stock": bool(_safe_int(mod.get("affects_stock"))),
    }



# ==============================================================================
# TPV libre · interpretación automática prudente + aprendizaje supervisado
# ==============================================================================

def _plain_norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", (value or "").lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def split_customer_modifier_note(note: str) -> list[str]:
    """Parte una nota libre del camarero en fragmentos interpretables.

    No intenta adivinar contexto complejo. Divide por coma, punto y conectores
    frecuentes, manteniendo expresiones como "en vez de".
    """
    raw = (note or "").strip()
    if not raw:
        return []
    # Separar primero por signos fuertes; luego por conectores habituales de comanda.
    raw = re.sub(r"[;\n]+", ",", raw)
    parts: list[str] = []
    for chunk in re.split(r",|\s+\+\s+", raw):
        chunk = chunk.strip()
        if not chunk:
            continue
        # Dividir frases con " y " solo cuando parecen dos modificadores claros.
        sub = re.split(r"\s+y\s+(?=(sin|con|extra|mas|más|solo|cambio|cambiar|guarnicion|guarnición)\b)", chunk, flags=re.I)
        if len(sub) > 1:
            buf = []
            i = 0
            while i < len(sub):
                if sub[i].lower() in {"sin","con","extra","mas","más","solo","cambio","cambiar","guarnicion","guarnición"} and i+1 < len(sub):
                    buf.append((sub[i] + " " + sub[i+1]).strip())
                    i += 2
                else:
                    if sub[i].strip():
                        buf.append(sub[i].strip())
                    i += 1
            parts.extend([x for x in buf if x])
        else:
            parts.append(chunk)
    return parts[:12]


def _recipe_item_candidates(cur, recipe_id: int, term: str, limit: int = 5) -> list[dict[str, Any]]:
    """Busca ingrediente primero dentro de la receta; si no, en catálogo.

    Devuelve candidatos; no selecciona automáticamente si hay demasiada duda.
    """
    ensure_pos_modifier_tables(cur)
    tnorm = _plain_norm(term)
    if not tnorm:
        return []
    candidates: list[dict[str, Any]] = []
    try:
        rows = cur.execute(
            """
            SELECT COALESCE(ri.item_id,0) item_id,
                   COALESCE(ri.item_name, i.name, '') item_name,
                   COALESCE(ri.qty_net, ri.qty_gross, 0) qty_ref,
                   COALESCE(ri.unit, i.unit, 'g') unit_ref,
                   1 as in_recipe
              FROM recipe_ingredients ri
              LEFT JOIN items i ON i.id=ri.item_id
             WHERE ri.recipe_id=?
             ORDER BY ri.id
            """,
            (int(recipe_id or 0),),
        ).fetchall()
        for r in rows:
            name = r["item_name"] or ""
            n = _plain_norm(name)
            if tnorm in n or any(tok and tok in n for tok in tnorm.split() if len(tok) >= 4):
                d = _rowdict(r); d["score"] = 0.96 if tnorm in n else 0.78
                candidates.append(d)
    except Exception:
        pass
    if not candidates:
        try:
            rows = cur.execute("SELECT id item_id, name item_name, 0 qty_ref, COALESCE(unit,'g') unit_ref, 0 in_recipe FROM items ORDER BY name LIMIT 2000").fetchall()
            for r in rows:
                name = r["item_name"] or ""
                n = _plain_norm(name)
                if tnorm in n or any(tok and tok in n for tok in tnorm.split() if len(tok) >= 4):
                    d = _rowdict(r); d["score"] = 0.70 if tnorm in n else 0.52
                    candidates.append(d)
                    if len(candidates) >= limit:
                        break
        except Exception:
            pass
    return candidates[:limit]


def _candidate_delta(cands: list[dict[str, Any]], sign: float, fallback_qty: float = 0.0, fallback_unit: str = "g") -> tuple[int, float, str, str, float]:
    if not cands:
        return 0, 0.0, fallback_unit, "", 0.0
    c = cands[0]
    item_id = _safe_int(c.get("item_id"))
    qty = abs(_safe_float(c.get("qty_ref"))) or abs(_safe_float(fallback_qty))
    unit = (c.get("unit_ref") or fallback_unit or "g")
    try:
        q_base, u_base = _convert_qty(sign * qty, unit)
    except Exception:
        q_base, u_base = sign * qty, unit
    return item_id, _safe_float(q_base), u_base, c.get("item_name") or "", _safe_float(c.get("score"))


def interpret_free_pos_modifier_note(cur, recipe_id: int, note: str, qty_sold: float = 1.0, center_id: int = 0) -> dict[str, Any]:
    """Interpreta notas libres del TPV de forma prudente.

    Se usa cuando el camarero puede escribir cualquier petición del cliente. La función:
    - aplica mapeos ya aprendidos;
    - resuelve patrones obvios (sin X, extra X, solo aceite, guarnición A en vez de B);
    - deja REQUIERE_MAPEO si no hay confianza suficiente;
    - no modifica receta maestra ni mueve stock.
    """
    ensure_pos_modifier_tables(cur)
    fragments = split_customer_modifier_note(note)
    qty_factor = _safe_float(qty_sold) or 1.0
    results: list[dict[str, Any]] = []
    exact = estimated = review = no_stock = 0
    for frag in fragments:
        norm = _plain_norm(frag)
        mapped = resolve_modifier(cur, recipe_id, frag)
        if mapped.get("id"):
            delta = build_modifier_delta(cur, recipe_id, frag, qty_factor)
            status = delta.get("status") or "CONSUMO_EXACTO"
            results.append({"raw": frag, "normalized": normalize_modifier_name(frag), "status": status, "confidence": 0.95, "source": "MAPEADO", "delta": delta, "message": "Regla ya aprendida/mapeada."})
            if status == "IGNORADO_NO_STOCK": no_stock += 1
            else: exact += 1
            continue
        # No stock: punto/corte/cubiertos/observación operativa.
        if re.search(r"\b(poco hecho|muy hecho|al punto|cortar|partir|sin cubiertos|con cubiertos|para llevar|mesa|cumpleanos|cumpleaños)\b", norm):
            results.append({"raw": frag, "normalized": normalize_modifier_name(frag), "status": "IGNORADO_NO_STOCK", "confidence": 0.88, "source": "REGLA_LOCAL", "delta": {}, "message": "Parece observación de servicio; no ajusta stock."})
            no_stock += 1
            continue
        # Sustitución guarnición: ensalada en vez de patatas / cambiar patatas por ensalada.
        m = re.search(r"(.+?)\s+(?:en vez de|por|x)\s+(.+)", norm)
        if m:
            add_term = m.group(1).replace("con ", "").replace("guarnicion", "").strip()
            sub_term = m.group(2).replace("sin ", "").replace("guarnicion", "").strip()
            add_c = _recipe_item_candidates(cur, recipe_id, add_term)
            sub_c = _recipe_item_candidates(cur, recipe_id, sub_term)
            add_id, add_q, add_u, add_name, add_score = _candidate_delta(add_c, +1)
            sub_id, sub_q, sub_u, sub_name, sub_score = _candidate_delta(sub_c, -1)
            conf = min(add_score or 0, sub_score or 0)
            status = "CONSUMO_ESTIMADO_CON_ALERTA" if conf >= 0.65 and (add_id or sub_id) else "REQUIERE_MAPEO"
            results.append({"raw": frag, "normalized": normalize_modifier_name(frag), "status": status, "confidence": round(conf, 2), "source": "SUSTITUCION_AUTO", "delta": {"add_item_id": add_id, "add_item": add_name, "add_qty": add_q * qty_factor, "add_unit": add_u, "subtract_item_id": sub_id, "subtract_item": sub_name, "subtract_qty": sub_q * qty_factor, "subtract_unit": sub_u}, "message": "Sustitución detectada; revisar si la equivalencia es correcta."})
            estimated += 1 if status != "REQUIERE_MAPEO" else 0
            review += 1 if status == "REQUIERE_MAPEO" else 0
            continue
        # SIN X / quitar X.
        m = re.search(r"\b(?:sin|quitar|quita|no poner|no lleva)\s+(.+)$", norm)
        if m:
            term = m.group(1).strip()
            cands = _recipe_item_candidates(cur, recipe_id, term)
            item_id, q, u, name, score = _candidate_delta(cands, -1)
            status = "CONSUMO_EXACTO" if score >= 0.90 else ("CONSUMO_ESTIMADO_CON_ALERTA" if score >= 0.60 else "REQUIERE_MAPEO")
            results.append({"raw": frag, "normalized": normalize_modifier_name(frag), "status": status, "confidence": round(score, 2), "source": "SIN_AUTO", "delta": {"item_id": item_id, "item": name, "qty_delta_base": q * qty_factor, "unit_base": u}, "message": "Patrón SIN detectado; no cambia receta maestra."})
            if status == "CONSUMO_EXACTO": exact += 1
            elif status == "CONSUMO_ESTIMADO_CON_ALERTA": estimated += 1
            else: review += 1
            continue
        # EXTRA/MÁS/CON X / solo aceite.
        m = re.search(r"\b(?:extra|mas|más|con|solo|añadir|agregar)\s+(.+)$", norm)
        if m:
            term = m.group(1).strip()
            cands = _recipe_item_candidates(cur, recipe_id, term)
            item_id, q, u, name, score = _candidate_delta(cands, +1)
            # Para extras el gramaje puede no existir en receta: debe ser revisión salvo regla aprendida.
            status = "CONSUMO_ESTIMADO_CON_ALERTA" if score >= 0.65 and item_id else "REQUIERE_MAPEO"
            results.append({"raw": frag, "normalized": normalize_modifier_name(frag), "status": status, "confidence": round(score, 2), "source": "EXTRA_AUTO", "delta": {"item_id": item_id, "item": name, "qty_delta_base": q * qty_factor, "unit_base": u}, "message": "Extra detectado; conviene aprender gramaje exacto si se repite."})
            estimated += 1 if status != "REQUIERE_MAPEO" else 0
            review += 1 if status == "REQUIERE_MAPEO" else 0
            continue
        # Ambiguo.
        results.append({"raw": frag, "normalized": normalize_modifier_name(frag), "status": "REQUIERE_MAPEO", "confidence": 0.0, "source": "LIBRE_AMBIGUO", "delta": {}, "message": "Nota libre no interpretable con seguridad; descontar base y revisar."})
        review += 1
    if not fragments:
        return {"ok": True, "status": "SIN_MODIFICADORES", "policy": "base_only", "fragments": [], "summary": "Sin nota/modificador TPV."}
    if review:
        status = "CONSUMO_ESTIMADO_CON_ALERTA" if (exact or estimated or no_stock) else "REQUIERE_MAPEO"
    elif estimated:
        status = "CONSUMO_ESTIMADO_CON_ALERTA"
    else:
        status = "CONSUMO_EXACTO" if exact else "IGNORADO_NO_STOCK"
    return {
        "ok": True,
        "status": status,
        "policy": "descontar_base_y_aplicar_deltas_claros" if status != "REQUIERE_MAPEO" else "descontar_base_y_revisar_modificador",
        "recipe_id": int(recipe_id or 0),
        "qty_sold": qty_factor,
        "raw_note": note or "",
        "fragments": results,
        "counts": {"exact": exact, "estimated": estimated, "review": review, "no_stock": no_stock},
        "summary": "La venta puede consumir receta base; solo se aplican deltas claros y lo ambiguo queda en revisión.",
    }


def register_modifier_review_from_note(cur, recipe_id: int, note: str, center_id: int = 0, pos_item_name: str = "", recipe_name: str = "") -> int:
    """Guarda una nota libre para aprendizaje supervisado si requiere revisión."""
    ensure_pos_modifier_tables(cur)
    interp = interpret_free_pos_modifier_note(cur, recipe_id, note, center_id=center_id)
    import json
    cur.execute(
        """
        INSERT INTO pos_modifier_review_queue(
            center_id, recipe_id, recipe_name, pos_item_name, raw_customer_note, normalized_note,
            suggested_status, suggested_action, suggested_delta_json, confidence_score, review_status, notes
        ) VALUES(?,?,?,?,?,?,?,?,?,?, 'PENDIENTE', ?)
        """,
        (
            int(center_id or 0), int(recipe_id or 0), (recipe_name or "")[:160], (pos_item_name or "")[:160],
            (note or "")[:500], normalize_modifier_name(note or ""), interp.get("status") or "REQUIERE_MAPEO",
            interp.get("policy") or "", json.dumps(interp.get("fragments") or [], ensure_ascii=False)[:4000],
            max([_safe_float(x.get("confidence")) for x in interp.get("fragments") or []] or [0.0]),
            "Creado desde nota libre TPV para aprendizaje supervisado.",
        ),
    )
    return int(cur.lastrowid)

def build_monthly_modifier_dashboard(center_id: int | None = None, year: int | None = None, month: int | None = None) -> dict[str, Any]:
    """Resumen mensual de modificadores TPV y riesgo de stock realista."""
    start, end, period = _month_bounds(year, month)
    conn = db(); cur = conn.cursor(); ensure_columns(cur); ensure_pos_modifier_tables(cur)
    params: list[Any] = [start, end]
    center_clause = ""
    if center_id:
        center_clause = " AND pm.center_id=?"
        params.append(int(center_id))
    try:
        rows = cur.execute(
            f"""
            SELECT COALESCE(pm.recipe_id,0) recipe_id,
                   COALESCE(pm.recipe_name, r.name, 'Venta sin receta vinculada') recipe_name,
                   COALESCE(pm.pos_modifier_name,'') pos_modifier_name,
                   COALESCE(pm.normalized_modifier_code,'') normalized_modifier_code,
                   COALESCE(pm.modifier_id,0) modifier_id,
                   COALESCE(rm.action,'') action,
                   COALESCE(rm.modifier_type,'') modifier_type,
                   COALESCE(rm.item_id,0) item_id,
                   COALESCE(i.name,'') item_name,
                   COALESCE(rm.subrecipe_id,0) subrecipe_id,
                   COALESCE(sr.name,'') subrecipe_name,
                   COALESCE(rm.qty_delta_base,0) qty_delta_base,
                   COALESCE(rm.unit_base,'g') unit_base,
                   COALESCE(pm.status,'REQUIERE_MAPEO') status,
                   COALESCE(pm.confidence,'LOW') confidence,
                   COALESCE(pm.channel,'') channel,
                   COALESCE(pm.business_type,'') business_type,
                   SUM(COALESCE(pm.qty_sold,0)) qty_sold,
                   COUNT(*) rows_count
              FROM pos_sales_modifier_daily pm
              LEFT JOIN recipe_modifiers rm ON rm.id=pm.modifier_id
              LEFT JOIN recipes r ON r.id=pm.recipe_id
              LEFT JOIN recipes sr ON sr.id=rm.subrecipe_id
              LEFT JOIN items i ON i.id=rm.item_id
             WHERE date(COALESCE(pm.sale_date,'')) >= date(?)
               AND date(COALESCE(pm.sale_date,'')) < date(?)
               {center_clause}
             GROUP BY COALESCE(pm.recipe_id,0), COALESCE(pm.normalized_modifier_code,''), COALESCE(pm.modifier_id,0),
                      COALESCE(pm.channel,''), COALESCE(pm.business_type,'')
             ORDER BY qty_sold DESC, rows_count DESC
            """,
            tuple(params),
        ).fetchall()
    except Exception:
        rows = []

    modifiers: list[dict[str, Any]] = []
    consumption: list[dict[str, Any]] = []
    unmapped: list[dict[str, Any]] = []
    no_stock: list[dict[str, Any]] = []
    for raw in rows:
        r = _rowdict(raw)
        qty = _safe_float(r.get("qty_sold"))
        status = r.get("status") or "REQUIERE_MAPEO"
        delta = _safe_float(r.get("qty_delta_base")) * qty if _safe_int(r.get("modifier_id")) else 0.0
        item_label = r.get("item_name") or r.get("subrecipe_name") or "sin artículo/subreceta"
        row = {
            "recipe_id": _safe_int(r.get("recipe_id")),
            "recipe_name": r.get("recipe_name") or "Venta sin receta vinculada",
            "modifier_name": r.get("pos_modifier_name") or r.get("normalized_modifier_code") or "Modificador",
            "normalized_code": r.get("normalized_modifier_code") or normalize_modifier_name(r.get("pos_modifier_name") or ""),
            "modifier_id": _safe_int(r.get("modifier_id")),
            "action": r.get("action") or "REQUIERE_MAPEO",
            "modifier_type": r.get("modifier_type") or "REVIEW",
            "qty_sold": qty,
            "status": status,
            "confidence": r.get("confidence") or "LOW",
            "channel": r.get("channel") or "sin canal",
            "business_type": r.get("business_type") or "sin tipo",
            "item_label": item_label,
            "qty_delta_base": delta,
            "unit_base": r.get("unit_base") or "g",
        }
        modifiers.append(row)
        if status == "REQUIERE_MAPEO" or not row["modifier_id"]:
            unmapped.append(row)
        elif status == "IGNORADO_NO_STOCK" or row["action"] == "NO_STOCK":
            no_stock.append(row)
        else:
            consumption.append(row)

    recommendations: list[str] = []
    if not modifiers:
        recommendations.append("Capa de modificadores preparada; aún no hay modificadores TPV normalizados para el periodo.")
    if unmapped:
        recommendations.append("Hay modificadores TPV sin mapear: no deben descontar stock hasta asignar regla interna.")
    if consumption:
        recommendations.append("Los modificadores mapeados ajustan consumo como delta sobre la receta base; la receta maestra no se modifica.")
    if no_stock:
        recommendations.append("Algunos modificadores se registran como observación sin impacto de stock, por ejemplo punto de cocción o cortar en dos.")

    conn.close()
    return {
        "period": period,
        "has_data": bool(modifiers),
        "total_modifier_qty": sum(_safe_float(x.get("qty_sold")) for x in modifiers),
        "mapped_count": len(consumption),
        "unmapped_count": len(unmapped),
        "no_stock_count": len(no_stock),
        "top_modifiers": modifiers[:15],
        "consumption_deltas": sorted(consumption, key=lambda x: abs(_safe_float(x.get("qty_delta_base"))), reverse=True)[:15],
        "unmapped_modifiers": unmapped[:15],
        "no_stock_modifiers": no_stock[:15],
        "recommendations": recommendations,
    }


# ==============================================================================
# Administración de modificadores TPV ↔ consumo real
# ==============================================================================

def list_recipe_modifiers_admin(cur, recipe_id: int | None = None, limit: int = 400) -> dict[str, Any]:
    """Contexto para Admin → Modificadores TPV. Lectura pura.

    Objetivo: configurar cómo los cambios del TPV ajustan stock sin tocar recetas maestras.
    """
    ensure_pos_modifier_tables(cur)
    where = "WHERE rm.is_active=1"
    params: list[Any] = []
    if recipe_id:
        where += " AND rm.recipe_id=?"
        params.append(int(recipe_id))
    rows = cur.execute(
        f"""
        SELECT rm.*,
               COALESCE(r.name,'Todas / genérico') recipe_name,
               COALESCE(i.name,'') item_name,
               COALESCE(sr.name,'') subrecipe_name
          FROM recipe_modifiers rm
          LEFT JOIN recipes r ON r.id=rm.recipe_id
          LEFT JOIN items i ON i.id=rm.item_id
          LEFT JOIN recipes sr ON sr.id=rm.subrecipe_id
          {where}
         ORDER BY COALESCE(r.name,''), rm.name
         LIMIT ?
        """,
        tuple(params + [int(limit or 400)]),
    ).fetchall()
    maps = cur.execute(
        """
        SELECT m.*, COALESCE(r.name,'Todas / genérico') recipe_name, COALESCE(rm.name,'') modifier_name
          FROM pos_modifier_map m
          LEFT JOIN recipes r ON r.id=m.recipe_id
          LEFT JOIN recipe_modifiers rm ON rm.id=m.modifier_id
         ORDER BY m.created_at DESC, m.id DESC
         LIMIT 500
        """
    ).fetchall()
    recipes = cur.execute("SELECT id,name FROM recipes ORDER BY name LIMIT 600").fetchall()
    items = cur.execute("SELECT id,name,unit FROM items ORDER BY name LIMIT 1200").fetchall()
    try:
        queue = cur.execute("""
            SELECT q.*, COALESCE(r.name, q.recipe_name, '') recipe_label
              FROM pos_modifier_review_queue q
              LEFT JOIN recipes r ON r.id=q.recipe_id
             WHERE COALESCE(q.review_status,'PENDIENTE')='PENDIENTE'
             ORDER BY q.created_at DESC, q.id DESC
             LIMIT 80
        """).fetchall()
    except Exception:
        queue = []
    return {
        "modifiers": [_rowdict(x) for x in rows],
        "maps": [_rowdict(x) for x in maps],
        "review_queue": [_rowdict(x) for x in queue],
        "recipes": [_rowdict(x) for x in recipes],
        "items": [_rowdict(x) for x in items],
        "actions": ["ADD_ITEM", "SUBTRACT_ITEM", "REPLACE", "ADD_SUBRECIPE", "SUBTRACT_SUBRECIPE", "NO_STOCK", "REVIEW"],
        "types": ["SIN", "EXTRA", "SUSTITUIR", "GUARNICION", "SALSA", "PUNTO_COCCION", "OBSERVACION_NO_STOCK", "REVIEW"],
    }


def create_recipe_modifier(
    cur,
    recipe_id: int = 0,
    name: str = "",
    modifier_type: str = "REVIEW",
    action: str = "REVIEW",
    item_id: int = 0,
    subrecipe_id: int = 0,
    qty_delta: float = 0.0,
    unit: str = "g",
    affects_stock: int = 1,
    price_extra: float = 0.0,
    notes: str = "",
) -> int:
    """Crea un modificador interno seguro.

    qty_delta se guarda como cantidad base normalizada. Para acciones de resta puede ser
    negativa; si el usuario la carga positiva y la acción es SUBTRACT, se invierte.
    """
    ensure_pos_modifier_tables(cur)
    safe_name = (name or "").strip()[:160]
    if not safe_name:
        raise ValueError("Nombre de modificador requerido")
    safe_type = (modifier_type or "REVIEW").strip().upper()[:40]
    safe_action = (action or "REVIEW").strip().upper()[:40]
    q = _safe_float(qty_delta)
    u = (unit or "g").strip().lower()[:20] or "g"
    if safe_action.startswith("SUBTRACT") and q > 0:
        q = -q
    if safe_action in {"NO_STOCK", "REVIEW"}:
        affects_stock = 0 if safe_action == "NO_STOCK" else int(affects_stock or 0)
    try:
        q_base, unit_base = _convert_qty(q, u)
    except Exception:
        q_base, unit_base = q, u
    code = normalize_modifier_name(safe_name)
    cur.execute(
        """
        INSERT INTO recipe_modifiers(
            recipe_id, code, name, modifier_type, action, item_id, subrecipe_id,
            qty_delta_base, unit_base, price_extra, affects_stock, confidence, notes, is_active
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1)
        """,
        (
            int(recipe_id or 0), code, safe_name, safe_type, safe_action,
            int(item_id or 0), int(subrecipe_id or 0), float(q_base or 0), unit_base,
            _safe_float(price_extra), 1 if int(affects_stock or 0) else 0, "MANUAL",
            (notes or "").strip()[:500],
        ),
    )
    return int(cur.lastrowid)


def create_pos_modifier_map(
    cur,
    pos_modifier_name: str,
    modifier_id: int,
    recipe_id: int = 0,
    provider_name: str = "",
    business_type: str = "",
    notes: str = "",
) -> int:
    ensure_pos_modifier_tables(cur)
    safe_pos = (pos_modifier_name or "").strip()[:160]
    if not safe_pos:
        raise ValueError("Nombre TPV requerido")
    mid = int(modifier_id or 0)
    mod = cur.execute("SELECT id,recipe_id FROM recipe_modifiers WHERE id=? AND is_active=1", (mid,)).fetchone()
    if not mod:
        raise ValueError("Modificador interno no encontrado")
    norm = normalize_modifier_name(safe_pos)
    cur.execute(
        """
        INSERT INTO pos_modifier_map(
            provider_name,business_type,pos_modifier_name,normalized_code,recipe_id,modifier_id,action_status,notes
        ) VALUES(?,?,?,?,?,?, 'ACTIVE', ?)
        """,
        (
            (provider_name or "").strip()[:80],
            (business_type or "").strip()[:80],
            safe_pos, norm, int(recipe_id or mod["recipe_id"] or 0), mid, (notes or "").strip()[:500],
        ),
    )
    return int(cur.lastrowid)


def deactivate_recipe_modifier(cur, modifier_id: int) -> None:
    ensure_pos_modifier_tables(cur)
    cur.execute("UPDATE recipe_modifiers SET is_active=0 WHERE id=?", (int(modifier_id or 0),))
    cur.execute("UPDATE pos_modifier_map SET action_status='INACTIVE' WHERE modifier_id=?", (int(modifier_id or 0),))


def deactivate_pos_modifier_map(cur, map_id: int) -> None:
    ensure_pos_modifier_tables(cur)
    cur.execute("UPDATE pos_modifier_map SET action_status='INACTIVE' WHERE id=?", (int(map_id or 0),))
