"""System MAC · Núcleo OÍDO ALFI / IA Orquestadora.

Capa central para que la IA conviva con los módulos sin romper la lógica estable.
Reglas:
- Consulta y lectura: permitido.
- Crear borradores/propuestas: permitido.
- Confirmar stock, pedidos, producciones, albaranes o recetas maestras: requiere humano.
- Nunca inventar datos: si no hay confianza, queda en revisión.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import unicodedata
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import UploadFile

from app.core import db, UPLOADS_DIR
from app.services.oido_alfi_service import answer_oido_alfi
from app.services.operational_quick_service import add_operational_command, interpret_operational_command, get_ai_status, normalize_operational_text, force_spanish_operational_text, transcribe_audio_bytes


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _norm(value: Any) -> str:
    txt = normalize_operational_text(str(value or ""))
    txt = txt.strip().lower()
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    txt = re.sub(r"[^a-z0-9,\.\s]", " ", txt)
    txt = re.sub(r"\s+", " ", txt)
    return txt.strip()


INTENT_ENUM = {"PRODUCCIÓN", "MERMA", "PEDIDO", "CONSULTA_STOCK", "CONSULTA_PROVEEDOR", "RECETA_IA", "ALBARÁN_IA", "NO_ENTENDIDO"}


def _safe_public_intent(value: str) -> str:
    v = str(value or "").strip().upper()
    return v if v in INTENT_ENUM else "NO_ENTENDIDO"


def _ensure_col(cur: sqlite3.Cursor, table: str, col: str, ddl: str) -> None:
    try:
        cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
        if col not in cols:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
    except Exception:
        pass


def ensure_ai_orchestrator_schema(cur: sqlite3.Cursor) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_action_audit(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            center_id INTEGER NOT NULL DEFAULT 0,
            source TEXT DEFAULT 'oido_alfi',
            user_text TEXT DEFAULT '',
            intent TEXT DEFAULT '',
            action_type TEXT DEFAULT '',
            module TEXT DEFAULT '',
            permission_level TEXT DEFAULT 'READ',
            status TEXT DEFAULT 'PROPOSED',
            confidence REAL DEFAULT 0,
            result_message TEXT DEFAULT '',
            payload_json TEXT DEFAULT '',
            created_at TEXT DEFAULT ''
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_document_reviews(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            center_id INTEGER NOT NULL DEFAULT 0,
            doc_type TEXT DEFAULT 'unknown',
            source_type TEXT DEFAULT 'upload',
            original_filename TEXT DEFAULT '',
            stored_path TEXT DEFAULT '',
            file_sha256 TEXT DEFAULT '',
            status TEXT DEFAULT 'PENDIENTE_REVISION',
            confidence REAL DEFAULT 0,
            extracted_json TEXT DEFAULT '',
            warnings_json TEXT DEFAULT '[]',
            created_at TEXT DEFAULT '',
            review_at TEXT DEFAULT ''
        )
        """
    )
    for col, ddl in {
        "module": "TEXT DEFAULT ''",
        "permission_level": "TEXT DEFAULT 'READ'",
        "payload_json": "TEXT DEFAULT ''",
    }.items():
        _ensure_col(cur, "ai_action_audit", col, ddl)
    for col, ddl in {
        "review_at": "TEXT DEFAULT ''",
        "warnings_json": "TEXT DEFAULT '[]'",
    }.items():
        _ensure_col(cur, "ai_document_reviews", col, ddl)


POLICIES: list[dict[str, Any]] = [
    {"level": "READ", "allowed": True, "human_required": False, "description": "Consultar stock, proveedores, recetas, alertas y datos ya cargados."},
    {"level": "DRAFT", "allowed": True, "human_required": False, "description": "Crear borradores o propuestas pendientes de pedido, merma, producción, receta o documento."},
    {"level": "REVIEW", "allowed": True, "human_required": True, "description": "Validar lectura dudosa, ingrediente nuevo, artículo sin precio, albarán/factura o modificador TPV."},
    {"level": "COMMIT", "allowed": False, "human_required": True, "description": "Confirmar stock, cerrar pedido, validar albarán, confirmar producción, confirmar merma o modificar receta maestra."},
]

MODULES: dict[str, dict[str, Any]] = {
    "stock": {"page": "stock", "read": True, "draft": False, "commit": False},
    "proveedores": {"page": "admin", "tab": "proveedores", "read": True, "draft": False, "commit": False},
    "recetas": {"page": "recetas", "read": True, "draft": True, "commit": False},
    "recetas_ia": {"url": "/recipe-ai/ui", "read": True, "draft": True, "commit": False},
    "albaranes": {"page": "albaranes", "read": True, "draft": True, "commit": False},
    "facturas": {"page": "albaranes", "read": True, "draft": True, "commit": False},
    "pedidos": {"page": "pedidos", "read": True, "draft": True, "commit": False},
    "producciones": {"page": "producciones", "read": True, "draft": True, "commit": False},
    "mermas": {"page": "mermas", "read": True, "draft": True, "commit": False},
    "inventario": {"page": "inventario", "read": True, "draft": False, "commit": False},
    "tpv": {"page": "admin", "tab": "tpv", "read": True, "draft": True, "commit": False},
    "control": {"page": "inicio", "read": True, "draft": False, "commit": False},
}


def capabilities() -> dict[str, Any]:
    status = get_ai_status()
    return {
        "ok": True,
        "name": "OÍDO ALFI / IA System MAC",
        "ai_status": status,
        "policies": POLICIES,
        "modules": MODULES,
        "rules": [
            "No modifica recetas maestras sin validación humana.",
            "No valida albaranes/facturas ni mueve stock desde OCR sin revisión.",
            "Puede crear borradores/propuestas pendientes para pedidos, mermas, producciones y recetas IA.",
            "Si un dato no se puede confirmar, lo marca como PENDIENTE_REVISION.",
            "Los ingredientes nuevos permanecen dentro del borrador como PENDIENTE_ALTA y el coste queda incompleto.",
        ],
    }


def _audit(center_id: int, user_text: str, result: dict[str, Any]) -> None:
    try:
        conn = db(); cur = conn.cursor(); ensure_ai_orchestrator_schema(cur)
        cur.execute(
            """INSERT INTO ai_action_audit(center_id,source,user_text,intent,action_type,module,permission_level,status,confidence,result_message,payload_json,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                int(center_id or 0),
                "oido_alfi",
                user_text or "",
                result.get("intent") or result.get("type") or "",
                result.get("action_type") or "",
                result.get("module") or "",
                result.get("permission_level") or "READ",
                result.get("status") or "ANSWERED",
                float(result.get("confidence") or 0),
                result.get("message") or "",
                json.dumps(result, ensure_ascii=False)[:8000],
                _now(),
            ),
        )
        conn.commit(); conn.close()
    except Exception:
        pass


def _page_url(page: str, center_id: int = 0, **extra) -> str:
    qs = {"page": page, "center_id": str(int(center_id or 0))}
    qs.update({k: str(v) for k, v in extra.items() if v is not None and str(v) != ""})
    return "/?" + "&".join(f"{k}={urllib.request.quote(str(v))}" for k, v in qs.items())


def _open_page_response(module: str, message: str, center_id: int = 0, **extra) -> dict[str, Any]:
    cfg = MODULES.get(module, {})
    url = cfg.get("url") or _page_url(cfg.get("page", "inicio"), center_id, **extra)
    return {
        "ok": True,
        "handled": True,
        "intent": "open_module",
        "action_type": "OPEN_PAGE",
        "permission_level": "READ",
        "module": module,
        "message": message,
        "redirect_url": url,
        "open_page": cfg.get("page"),
        "tab": cfg.get("tab"),
        "confidence": 0.9,
        "status": "ANSWERED",
    }


def _suggestions_for_intent(public_intent: str, parsed: Optional[dict[str, Any]] = None, center_id: int = 0) -> list[dict[str, str]]:
    """Sugerencias operativas seguras: nunca confirman acciones críticas."""
    parsed = parsed or {}
    items = parsed.get("items") or []
    name = ""
    qty = 0.0
    unit = ""
    if items:
        first = items[0] or {}
        name = str(first.get("name") or first.get("raw_name") or "").strip().upper()
        try:
            qty = float(first.get("qty") or 0)
        except Exception:
            qty = 0.0
        unit = str(first.get("unit") or "").strip()
    if public_intent == "PRODUCCIÓN":
        return [
            {"label": "Abrir Producciones", "url": _page_url("producciones", center_id)},
            {"label": "Completar cantidad" if qty <= 0 else "Revisar borrador", "url": _page_url("operativa", center_id, op_type="PRODUCTION")},
            {"label": "Ver receta/subreceta" if name else "Buscar receta", "url": _page_url("recetas", center_id)},
        ]
    if public_intent == "MERMA":
        return [
            {"label": "Abrir Mermas", "url": _page_url("mermas", center_id)},
            {"label": "Añadir cantidad/motivo" if qty <= 0 else "Revisar merma pendiente", "url": _page_url("operativa", center_id, op_type="WASTE")},
            {"label": "Consultar stock del producto", "url": _page_url("stock", center_id)},
        ]
    if public_intent == "PEDIDO":
        return [
            {"label": "Abrir Pedidos", "url": _page_url("pedidos", center_id)},
            {"label": "Revisar línea pendiente", "url": _page_url("operativa", center_id, op_type="ORDER")},
            {"label": "Ver proveedor/precio", "url": _page_url("admin", center_id, tab="proveedores")},
        ]
    if public_intent == "CONSULTA_STOCK":
        return [{"label": "Abrir Stock", "url": _page_url("stock", center_id)}, {"label": "Abrir Inventario", "url": _page_url("inventario", center_id)}]
    if public_intent == "CONSULTA_PROVEEDOR":
        return [{"label": "Abrir Proveedores", "url": _page_url("admin", center_id, tab="proveedores")}, {"label": "Abrir Pedidos", "url": _page_url("pedidos", center_id)}]
    if public_intent == "RECETA_IA":
        return [{"label": "Abrir IA Recetas", "url": "/recipe-ai/ui"}, {"label": "Abrir Recetas", "url": _page_url("recetas", center_id)}]
    if public_intent == "ALBARÁN_IA":
        return [{"label": "Abrir Albaranes", "url": _page_url("albaranes", center_id)}, {"label": "Ver pendientes OCR", "url": _page_url("albaranes", center_id, status="pending_ocr")} ]
    return [{"label": "Abrir OÍDO ALFI", "url": _page_url("operativa", center_id)}, {"label": "Inicio", "url": _page_url("inicio", center_id)}]



def _spanishize_visible_text(value: str) -> str:
    """Último filtro anti-inglés para textos visibles de OÍDO ALFI."""
    t = str(value or "")
    swaps = {
        r"\bproduction\b": "producción",
        r"\bwaste\b": "merma",
        r"\border\b": "pedido",
        r"\bsupplier\b": "proveedor",
        r"\btomatoes\b": "tomates",
        r"\btomato\b": "tomate",
        r"\bmake\b": "hacer",
        r"\bprepare\b": "preparar",
        r"\bstock\b": "stock",
        r"\bdraft\b": "borrador",
        r"\breview\b": "revisión",
    }
    for pat, repl in swaps.items():
        t = re.sub(pat, repl, t, flags=re.I)
    return t


def _expert_review_flags(public_intent: str, parsed: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Resumen experto para que la UI pueda explicar qué falta sin ejecutar de más."""
    parsed = parsed or {}
    items = parsed.get("items") or []
    missing: list[str] = []
    warnings: list[str] = []
    main_item = ""
    qty = 0.0
    unit = ""
    if items:
        first = items[0] or {}
        main_item = str(first.get("name") or first.get("raw_name") or "").strip().upper()
        try:
            qty = float(first.get("qty") or 0)
        except Exception:
            qty = 0.0
        unit = str(first.get("unit") or "").strip()
        if first.get("ambiguous_match"):
            warnings.append("coincidencia_ambigua")
        if first.get("matched_kind") == "none":
            warnings.append("sin_vinculo_catalogo")
    if public_intent in {"PRODUCCIÓN", "MERMA", "PEDIDO"} and not main_item:
        missing.append("producto/receta/artículo")
    if public_intent in {"MERMA", "PEDIDO"} and qty <= 0:
        missing.append("cantidad")
    if public_intent == "PRODUCCIÓN" and qty <= 0:
        missing.append("cantidad o lote/raciones")
    if public_intent == "MERMA" and not parsed.get("reason"):
        warnings.append("motivo_no_detectado")
    conf = float(parsed.get("confidence") or 0)
    risk = "BAJO"
    if warnings or missing or conf < 0.70:
        risk = "REVISIÓN"
    elif conf < 0.85:
        risk = "MEDIO"
    return {
        "main_item": main_item,
        "qty": qty,
        "unit": unit,
        "missing_fields": list(dict.fromkeys(missing)),
        "warnings": list(dict.fromkeys(warnings)),
        "risk_level": risk,
        "confidence": round(conf, 2),
    }

def _decorate_response(result: dict[str, Any], public_intent: str = "", parsed: Optional[dict[str, Any]] = None, center_id: int = 0, normalized_text: str = "") -> dict[str, Any]:
    pi = _safe_public_intent(public_intent or result.get("intent") or "NO_ENTENDIDO")
    result["intent"] = pi
    if normalized_text:
        result["normalized_text"] = normalized_text
    if result.get("message"):
        result["message"] = _spanishize_visible_text(str(result.get("message") or ""))
    flags = _expert_review_flags(pi, parsed)
    result.setdefault("expert_review", flags)
    result.setdefault("suggestions", _suggestions_for_intent(pi, parsed, center_id))
    result.setdefault("requires_human_confirmation", result.get("permission_level") in {"REVIEW", "COMMIT"} or result.get("action_type") in {"CREATE_DRAFT"})
    result.setdefault("execution_policy", "Solo crea borradores/propuestas pendientes. Confirmar stock, pedidos, producciones, albaranes o recetas maestras requiere revisión humana.")
    if flags.get("missing_fields") and pi in {"PRODUCCIÓN", "MERMA", "PEDIDO"}:
        result.setdefault("next_required_action", "Completar: " + ", ".join(flags.get("missing_fields") or []))
    elif pi in {"PRODUCCIÓN", "MERMA", "PEDIDO"}:
        result.setdefault("next_required_action", "Revisar y confirmar manualmente en el módulo correspondiente.")
    return result


def explain_command(text: str, center_id: int = 0) -> dict[str, Any]:
    """Prelectura sin ejecutar: útil para sugerencias en UI antes de pulsar Ejecutar."""
    raw = force_spanish_operational_text((text or "").strip())
    nq = _norm(raw)
    task_mode = _task_mode_for(nq)
    public_intent = _safe_public_intent(_public_intent(task_mode, nq))
    parsed = {}
    if task_mode in {"ORDER", "PRODUCTION", "WASTE"}:
        try:
            parsed = interpret_operational_command(raw, task_mode)
        except Exception:
            parsed = {}
    return _decorate_response({
        "ok": bool(raw),
        "handled": bool(raw),
        "action_type": "PREVIEW",
        "permission_level": "READ",
        "module": _route_module(nq) or "oido_alfi",
        "status": "PREVIEW" if raw else "EMPTY",
        "confidence": float(parsed.get("confidence") or (0.5 if raw else 0)),
        "parsed": parsed,
        "message": "Prelectura de OÍDO ALFI. Ejecutar creará solo propuestas pendientes cuando proceda.",
    }, public_intent, parsed, center_id, nq)


def _is_query(nq: str) -> bool:
    return any(x in nq for x in [
        "hay ", "stock", "cuanto", "cuánto", "proveedor", "telefono", "teléfono", "email", "correo", "minimo", "mínimo", "reparto", "quien vende", "quién vende", "de que", "de qué",
    ])


def _route_module(nq: str) -> Optional[str]:
    if any(x in nq for x in ["albaran", "albarán", "albaranes", "ocr"]): return "albaranes"
    if any(x in nq for x in ["factura", "facturas"]): return "facturas"
    if any(x in nq for x in ["receta por foto", "receta por voz", "importar receta", "ia receta", "ia recetas", "borrador ia"]): return "recetas_ia"
    if "receta" in nq or "escandallo" in nq: return "recetas"
    if "pedido" in nq or "pedir" in nq or "comprar" in nq: return "pedidos"
    if "produccion" in nq or "producción" in nq or "producir" in nq or "raciones" in nq: return "producciones"
    if "merma" in nq or "perdida" in nq or "pérdida" in nq or "desperdicio" in nq: return "mermas"
    if "inventario" in nq or "conteo" in nq or "conciliar" in nq: return "inventario"
    if "stock" in nq or "insumo" in nq or "articulo" in nq or "artículo" in nq: return "stock"
    if "tpv" in nq or "modificador" in nq: return "tpv"
    if "dashboard" in nq or "margen" in nq or "ventas" in nq or "control" in nq: return "control"
    if "proveedor" in nq or "proveedores" in nq: return "proveedores"
    return None


def _task_mode_for(nq: str) -> str:
    if any(x in nq for x in ["merma", "mima", "merna", "perdida", "pérdida", "desperdicio", "tirar", "tira", "desechar", "roto", "rota", "podrido", "caduc", "quemado", "mal estado"]): return "WASTE"
    if any(x in nq for x in ["produccion", "producción", "producir", "preparar", "prepárame", "preparame", "elaborar", "hacer produccion", "hacer producción", "mise", "raciones", "lote", "pico de gallo", "pico gallo"]): return "PRODUCTION"
    if any(x in nq for x in ["pedido", "pedir", "pide", "comprar", "compra", "encargar", "encarga", "solicitar", "solicita", "necesito", "falta", "faltan", "agrega", "añade", "anade", "apunta compra", "anota compra"]): return "ORDER"
    return "AUTO"


def _public_intent(task_mode: str, nq: str) -> str:
    if task_mode == "PRODUCTION": return "PRODUCCIÓN"
    if task_mode == "WASTE": return "MERMA"
    if task_mode == "ORDER": return "PEDIDO"
    if any(x in nq for x in ["receta por foto", "receta por voz", "receta ia", "borrador ia", "importar receta"]): return "RECETA_IA"
    if any(x in nq for x in ["albaran", "albarán", "factura", "ocr", "leer albaran", "leer factura"]): return "ALBARÁN_IA"
    if any(x in nq for x in ["proveedor", "telefono", "teléfono", "email", "correo", "reparto", "quien vende", "quién vende"]): return "CONSULTA_PROVEEDOR"
    if any(x in nq for x in ["stock", "hay ", "cuanto", "cuánto", "quedan", "existencias"]): return "CONSULTA_STOCK"
    return "NO_ENTENDIDO"



def _draft_message(task_mode: str, parsed: dict[str, Any], module: str, res: dict[str, Any]) -> str:
    items = parsed.get("items") or []
    main = items[0] if items else {}
    name = str(main.get("name") or main.get("raw_name") or "").strip().upper() or "SIN IDENTIFICAR"
    qty = float(main.get("qty") or 0) if str(main.get("qty") or "").strip() not in {""} else 0.0
    unit = str(main.get("unit") or "").strip()
    if task_mode == "PRODUCTION":
        if qty <= 0:
            return f"He entendido PRODUCCIÓN de {name}. Falta cantidad. La dejo como borrador pendiente; completa kg/raciones/lote antes de confirmar. No he movido stock."
        return f"He creado borrador pendiente de PRODUCCIÓN: {name} · {qty:g} {unit}. Revísalo en Operativa/Producciones; no he movido stock."
    if task_mode == "WASTE":
        if qty <= 0:
            return f"He entendido MERMA de {name}. Falta cantidad. La dejo como merma pendiente; no he descontado stock."
        return f"He creado merma pendiente: {name} · {qty:g} {unit}. Requiere confirmación humana; no he descontado stock."
    if task_mode == "ORDER":
        return f"He creado línea pendiente de PEDIDO: {name} · {qty:g} {unit}. No se ha enviado ni cerrado ningún pedido."
    return f"He creado una propuesta pendiente de {module}. Revísala antes de confirmar."

def handle_assistant_command(text: str, center_id: int = 0, requested_by: str = "") -> dict[str, Any]:
    """Orquesta una orden de OÍDO ALFI con límites de seguridad.

    Puede responder, abrir módulo o crear una propuesta pendiente. No confirma acciones críticas.
    """
    raw = force_spanish_operational_text((text or "").strip())
    nq = _norm(raw)
    if not nq:
        result = _decorate_response({"ok": False, "handled": False, "intent": "NO_ENTENDIDO", "message": "Escribe o dicta una orden para OÍDO ALFI.", "status": "EMPTY"}, "NO_ENTENDIDO", None, center_id, nq)
        _audit(center_id, raw, result); return result

    task_mode = _task_mode_for(nq)
    public_intent = _safe_public_intent(_public_intent(task_mode, nq))

    # Consultas de datos reales: usa servicio existente y trazable.
    # Si hay intención operativa clara (merma/producción/pedido), no la degrada a consulta por palabras como "hay".
    if _is_query(nq) and task_mode == "AUTO":
        info = answer_oido_alfi(raw, center_id)
        info.update({"handled": bool(info.get("type") != "fallback"), "action_type": "READ", "permission_level": "READ", "module": info.get("open_page") or "consulta", "intent": public_intent})
        info = _decorate_response(info, public_intent, None, center_id, nq)
        _audit(center_id, raw, info); return info

    # Lectura de documentos: abrir módulo correcto, no inventar lectura si no se ha subido archivo.
    if any(x in nq for x in ["leer albaran", "leer albarán", "procesar albaran", "procesar albarán", "leer factura", "leer receta", "foto receta", "receta por foto"]):
        if "receta" in nq:
            result = _open_page_response("recetas_ia", "Abro IA Recetas. La lectura crea borrador revisable, no receta maestra.", center_id)
        elif "factura" in nq:
            result = _open_page_response("facturas", "Abro Albaranes/Facturas. La IA podrá preparar lectura pendiente de revisión.", center_id)
        else:
            result = _open_page_response("albaranes", "Abro Albaranes. La IA podrá leer y preparar propuesta; validar stock requiere revisión humana.", center_id)
        result = _decorate_response(result, public_intent, None, center_id, nq)
        _audit(center_id, raw, result); return result

    # Operativa de bajo riesgo: si detecta intención operativa, crea propuesta pendiente.
    # No se limita a abrir el módulo: OÍDO ALFI debe dejar una acción real revisable.
    if task_mode in {"ORDER", "PRODUCTION", "WASTE"}:
        try:
            parsed = interpret_operational_command(raw, task_mode)
            if parsed.get("items"):
                items_preview = parsed.get("items") or []
                bad_name = all((str((it or {}).get("name") or "").strip().upper() in {"", "SIN IDENTIFICAR", "NONE"}) for it in items_preview)
                low_conf = float(parsed.get("confidence") or 0) < 0.50
                ambiguous = any(bool((it or {}).get("ambiguous_match")) for it in items_preview)
                if bad_name or low_conf:
                    guess = str((items_preview[0] or {}).get("name") or (items_preview[0] or {}).get("raw_name") or "").strip().upper() if items_preview else ""
                    result = {
                        "ok": False, "handled": True, "intent": public_intent, "internal_intent": "confirm_operational_draft",
                        "action_type": "ASK_CONFIRMATION", "permission_level": "REVIEW", "module": {"ORDER":"pedidos","PRODUCTION":"producciones","WASTE":"mermas"}.get(task_mode,"operativa"),
                        "status": "NEEDS_CONFIRMATION", "confidence": float(parsed.get("confidence") or 0), "parsed": parsed,
                        "message": (f"Creo que quieres hacer {public_intent}" + (f" de {guess}" if guess and guess != "SIN IDENTIFICAR" else "") + ". Confírmalo o escribe el producto/cantidad con más detalle. No he creado borrador todavía."),
                        "redirect_url": _page_url("operativa", center_id, op_type=task_mode),
                    }
                    result = _decorate_response(result, public_intent, parsed, center_id, nq)
                    _audit(center_id, raw, result); return result
                actor = requested_by or parsed.get("responsible") or "OÍDO ALFI"
                res = add_operational_command(center_id=center_id, voice_text=raw, requested_by=actor, source="oido_alfi", forced_task_type=task_mode)
                module = {"ORDER": "pedidos", "PRODUCTION": "producciones", "WASTE": "mermas"}.get(task_mode, "operativa")
                if not res.get("ok"):
                    result = {
                        "ok": False, "handled": True, "intent": public_intent, "internal_intent": "create_operational_draft",
                        "action_type": "CREATE_DRAFT", "permission_level": "DRAFT", "module": module, "status": "NEEDS_CLARIFICATION",
                        "confidence": float(parsed.get("confidence") or 0.5), "parsed": parsed,
                        "message": res.get("error") or "Faltan datos para crear la propuesta pendiente.",
                        "error_code": res.get("error_code") or "NEEDS_CLARIFICATION",
                        "redirect_url": _page_url("operativa", center_id, op_type=task_mode),
                    }
                    result = _decorate_response(result, public_intent, parsed, center_id, nq)
                    _audit(center_id, raw, result); return result
                result = {
                    "ok": True,
                    "handled": True,
                    "intent": public_intent,
                    "internal_intent": "create_operational_draft",
                    "action_type": "CREATE_DRAFT",
                    "permission_level": "DRAFT",
                    "module": module,
                    "status": "PENDING_REVIEW",
                    "confidence": float(parsed.get("confidence") or 0.6),
                    "line_id": res.get("line_id"),
                    "task_type": task_mode,
                    "parsed": parsed,
                    "message": _draft_message(task_mode, parsed, module, res),
                    "redirect_url": _page_url("operativa", center_id, op_line=res.get("line_id") or 0, op_type=task_mode),
                    "module_url": _page_url(module, center_id) if module in {"pedidos", "producciones", "mermas"} else _page_url("operativa", center_id),
                }
                result = _decorate_response(result, public_intent, parsed, center_id, nq)
                _audit(center_id, raw, result); return result
        except Exception as exc:
            result = {"ok": False, "handled": True, "intent": "create_operational_draft", "action_type": "CREATE_DRAFT", "permission_level": "DRAFT", "status": "ERROR", "message": f"No pude crear la propuesta: {exc}", "module": "operativa"}
            result = _decorate_response(result, public_intent, None, center_id, nq)
            _audit(center_id, raw, result); return result

    module = _route_module(nq)
    if module:
        result = _open_page_response(module, f"Abro {module}. No ejecuto cambios críticos sin validación humana.", center_id)
        result = _decorate_response(result, public_intent, None, center_id, nq)
        _audit(center_id, raw, result); return result

    result = {
        "ok": False,
        "handled": False,
        "intent": "NO_ENTENDIDO",
        "internal_intent": "fallback",
        "action_type": "FALLBACK",
        "permission_level": "READ",
        "module": "oido_alfi",
        "status": "NEEDS_CLARIFICATION",
        "message": "No puedo confirmar esa orden. Puedo consultar datos, abrir módulos o crear propuestas pendientes para revisar.",
        "ideas": ["leer albarán", "importar receta por foto", "apunta merma de 2 kg", "¿hay puerro en stock?", "¿de qué proveedor es bacalao?"],
    }
    result = _decorate_response(result, "NO_ENTENDIDO", None, center_id, nq)
    _audit(center_id, raw, result); return result


def _openai_vision_extract(doc_type: str, image_bytes: bytes, mime: str = "image/jpeg") -> dict[str, Any]:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        return {"ok": False, "configured": False, "message": "OpenAI no está activa. Documento guardado para revisión manual."}
    model = os.environ.get("OIDO_ALFI_VISION_MODEL", os.environ.get("OPERATIVA_AI_MODEL", "gpt-4o-mini"))
    b64 = base64.b64encode(image_bytes).decode("ascii")
    if doc_type == "recipe":
        task = "Extrae una receta de cocina en JSON: recipe_name, ingredients[{name, qty, unit, notes}], elaboration_steps[], warnings[]. No inventes ingredientes no visibles."
    elif doc_type in {"receipt", "albaran", "albarán"}:
        task = "Extrae un albarán en JSON: supplier, date, document_number, lines[{name, qty, unit, unit_price, amount, vat}], totals, warnings[]. No inventes; marca dudas."
    else:
        task = "Extrae una factura/albarán en JSON estructurado con cabecera, líneas, impuestos, totales y warnings. No inventes."
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Eres IA documental de System MAC. Devuelve solo JSON válido. Si no puedes leer algo, usa null y warnings. Nunca confirmes stock ni receta maestra."},
            {"role": "user", "content": [
                {"type": "text", "text": task},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ]},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    try:
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=float(os.environ.get("OIDO_ALFI_DOC_TIMEOUT", "45"))) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        extracted = json.loads(content)
        return {"ok": True, "configured": True, "model": model, "extracted": extracted, "usage": data.get("usage") or {}}
    except Exception as exc:
        return {"ok": False, "configured": True, "message": f"OpenAI no pudo leer el documento: {exc}"}


def _audio_suffix(filename: str, content_type: str = "") -> str:
    ext = Path(filename or "").suffix.lower()
    if ext in {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm", ".ogg"}:
        return ext
    ct = (content_type or "").lower()
    if "webm" in ct:
        return ".webm"
    if "ogg" in ct:
        return ".ogg"
    if "wav" in ct:
        return ".wav"
    if "mp4" in ct:
        return ".m4a"
    return ".webm"


async def transcribe_oido_alfi_audio(upload: UploadFile, center_id: int = 0) -> dict[str, Any]:
    """Transcribe audio for OÍDO ALFI using a server-side STT layer.

    No depends on browser SpeechRecognition or the OpenAI Python SDK. It uses
    OpenAI audio transcription via HTTPS multipart when OPENAI_API_KEY and
    OPERATIVA_STT_MODE=openai are configured. If not, it returns a clear fallback
    for iPhone/Android keyboard dictation.
    """
    raw = await upload.read()
    max_mb = float(os.environ.get("OIDO_ALFI_AUDIO_MAX_MB", "25"))
    if not raw:
        return {"ok": False, "configured": bool(os.environ.get("OPENAI_API_KEY", "").strip()), "text": "", "message": "El audio está vacío.", "status": "EMPTY_AUDIO"}
    if len(raw) > max_mb * 1024 * 1024:
        return {"ok": False, "configured": True, "text": "", "message": f"Audio demasiado grande. Máximo {max_mb:g} MB.", "status": "AUDIO_TOO_LARGE"}

    # Selector de STT: Deepgram si está configurado; OpenAI queda como fallback.
    # No fuerza OpenAI cuando exista Deepgram para evitar volver al motor que falló en pruebas reales.
    if os.environ.get("DEEPGRAM_API_KEY", "").strip():
        os.environ.setdefault("STT_PROVIDER", "deepgram")
        os.environ.setdefault("OPERATIVA_STT_MODE", "deepgram")
    elif os.environ.get("OPENAI_API_KEY", "").strip():
        os.environ.setdefault("STT_PROVIDER", "openai")
        os.environ.setdefault("OPERATIVA_STT_MODE", "openai")
    filename = upload.filename or "oido_alfi.webm"
    content_type = upload.content_type or "audio/webm"
    res = transcribe_audio_bytes(raw, filename=filename, content_type=content_type)
    if not res.get("ok"):
        msg = res.get("error") or res.get("message") or "No pude transcribir el audio. Usa el micrófono del teclado en el campo de texto."
        return {
            "ok": False,
            "configured": bool(res.get("configured")),
            "text": "",
            "message": msg,
            "status": "TRANSCRIPTION_UNAVAILABLE" if not res.get("configured") else "TRANSCRIPTION_ERROR",
            "source": res.get("source") or "server_stt",
        }
    text = _norm(force_spanish_operational_text(str(res.get("text") or "").strip()))
    if not text:
        return {"ok": False, "configured": True, "text": "", "message": "No pude obtener texto útil del audio.", "status": "NO_TRANSCRIPT"}
    return {
        "ok": True,
        "configured": True,
        "text": text,
        "model": res.get("model") or os.environ.get("OPERATIVA_STT_MODEL", os.environ.get("OIDO_ALFI_STT_MODEL", "gpt-4o-mini-transcribe")),
        "raw_text": res.get("raw_text") or text,
        "message": f"He transcrito en español: {text}",
        "status": "TRANSCRIBED",
        "source": res.get("source") or "server_stt",
        "language": res.get("language") or os.environ.get("STT_LANGUAGE", "es"),
        "warning": res.get("warning") or "",
    }

async def receive_document_for_review(upload: UploadFile, doc_type: str = "unknown", center_id: int = 0) -> dict[str, Any]:
    raw = await upload.read()
    now = _now()
    safe_doc = _norm(doc_type).replace(" ", "_") or "unknown"
    fname = upload.filename or f"documento_{safe_doc}.bin"
    ext = Path(fname).suffix.lower()[:12] or ".bin"
    digest = hashlib.sha256(raw).hexdigest()
    folder = UPLOADS_DIR / "ai_document_reviews"
    folder.mkdir(parents=True, exist_ok=True)
    stored = folder / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{digest[:10]}{ext}"
    stored.write_bytes(raw)

    warnings: list[str] = []
    extracted: dict[str, Any] = {}
    confidence = 0.0
    status = "PENDIENTE_REVISION"
    mime = upload.content_type or "application/octet-stream"
    if mime.startswith("image/") or ext in {".jpg", ".jpeg", ".png", ".webp"}:
        ai_res = _openai_vision_extract(safe_doc, raw, mime if mime.startswith("image/") else "image/jpeg")
        if ai_res.get("ok"):
            extracted = ai_res.get("extracted") or {}
            confidence = 0.72
            status = "LECTURA_IA_PENDIENTE_REVISION"
            warnings = extracted.get("warnings") if isinstance(extracted.get("warnings"), list) else []
        else:
            warnings.append(ai_res.get("message") or "Lectura IA no disponible; revisión manual.")
    else:
        warnings.append("Formato guardado para revisión. La lectura automática de PDF/factura se integrará por OCR/IA documental supervisada.")

    conn = db(); cur = conn.cursor(); ensure_ai_orchestrator_schema(cur)
    cur.execute(
        """INSERT INTO ai_document_reviews(center_id,doc_type,source_type,original_filename,stored_path,file_sha256,status,confidence,extracted_json,warnings_json,created_at,review_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (int(center_id or 0), safe_doc, "upload", fname, str(stored), digest, status, confidence, json.dumps(extracted, ensure_ascii=False), json.dumps(warnings, ensure_ascii=False), now, now),
    )
    review_id = cur.lastrowid
    conn.commit(); conn.close()
    return {
        "ok": True,
        "review_id": review_id,
        "doc_type": safe_doc,
        "status": status,
        "confidence": confidence,
        "created_at": now,
        "review_at": now,
        "warnings": warnings,
        "extracted": extracted,
        "message": "Documento guardado en revisión IA. No se ha validado stock, factura ni receta maestra.",
    }
