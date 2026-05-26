# ==============================================================================
# BLOQUE ADMIN · Centros, configuración general
# ==============================================================================
from fastapi import APIRouter, Form
from fastapi.responses import RedirectResponse, JSONResponse
import os
from pathlib import Path

from app.core import db, ensure_columns, ROOT_DIR
from app.services.admin_service import normalize_center_name, redirect_admin
from app.services.operational_quick_service import get_ai_status, test_openai_connection, test_deepgram_connection
from app.services.pos_modifiers_service import (
    ensure_pos_modifier_tables, create_recipe_modifier, create_pos_modifier_map,
    deactivate_recipe_modifier, deactivate_pos_modifier_map, register_modifier_review_from_note,
)

router = APIRouter()


@router.post("/center/{center_id}/update_name_form")
def update_center_name_form(center_id: int, name: str = Form(...)):
    conn = db(); cur = conn.cursor()
    cur.execute("UPDATE centers SET name=? WHERE id=?", (normalize_center_name(name), center_id))
    conn.commit(); conn.close()
    return redirect_admin(center_id=0, ok=1)


@router.get("/health")
def health():
    return {"ok": True}


@router.get("/api/admin/ia_status")
def admin_ia_status():
    return JSONResponse(get_ai_status())


@router.post("/api/admin/probar_ia")
def admin_probar_ia():
    return JSONResponse(test_openai_connection())

@router.post("/api/admin/probar_openai")
def admin_probar_openai():
    return JSONResponse(test_openai_connection())

@router.post("/api/admin/probar_deepgram")
def admin_probar_deepgram():
    return JSONResponse(test_deepgram_connection())




# ==============================================================================
# ADMIN · Configuración IA/OpenAI desde la interfaz
# ==============================================================================

SENSITIVE_ENV_KEYS = {
    "OPENAI_API_KEY",
    "DEEPGRAM_API_KEY",
    "STT_PROVIDER",
    "STT_LANGUAGE",
    "DEEPGRAM_MODEL",
    "OPERATIVA_AI_MODE",
    "OPERATIVA_STT_MODE",
    "OPERATIVA_AI_MODEL",
    "OPERATIVA_STT_MODEL",
    "OPENAI_STT_MODEL",
    "OPERATIVA_AI_TIMEOUT",
    "OPERATIVA_STT_TIMEOUT",
    "RECIPE_AI_PROVIDER",
}


def _project_env_paths() -> list[Path]:
    """Devuelve .env de raíz del paquete y backend/.env.

    No guarda la clave en base de datos. Se escribe en ficheros locales con permisos 600.
    """
    backend_dir = Path(ROOT_DIR).resolve()
    package_root = backend_dir.parent
    return [package_root / ".env", backend_dir / ".env"]


def _read_env_values() -> dict[str, str]:
    vals: dict[str, str] = {}
    for path in _project_env_paths():
        try:
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip().strip('"').strip("'")
        except Exception:
            pass
    return vals


def _write_env_values(values: dict[str, str]) -> None:
    keep_order = [
        "OPERATIVA_AI_MODE", "OPERATIVA_STT_MODE", "STT_PROVIDER", "STT_LANGUAGE",
        "OPENAI_API_KEY", "DEEPGRAM_API_KEY",
        "OPERATIVA_AI_MODEL", "OPENAI_STT_MODEL", "OPERATIVA_STT_MODEL", "DEEPGRAM_MODEL",
        "OPERATIVA_LANGUAGE", "OIDO_ALFI_LANGUAGE", "RECIPE_VOICE_LANGUAGE",
        "OPERATIVA_AI_TIMEOUT", "OPERATIVA_STT_TIMEOUT", "RECIPE_AI_PROVIDER",
    ]
    lines = ["# System MAC · IA / Voz", "# Archivo generado desde Admin → IA.", "# No compartas este archivo."]
    for k in keep_order:
        if values.get(k, "") != "":
            lines.append(f"{k}={values[k]}")
    lines.append("")
    content = "\n".join(lines)
    for path in _project_env_paths():
        try:
            path.write_text(content, encoding="utf-8")
            try:
                path.chmod(0o600)
            except Exception:
                pass
        except Exception as exc:
            raise RuntimeError(f"No se pudo escribir {path}: {exc}") from exc
    for k, v in values.items():
        if v != "":
            os.environ[k] = v


def _write_ai_env(openai_key: str) -> None:
    openai_key = (openai_key or "").strip()
    if not openai_key:
        raise ValueError("Clave vacía")
    if not openai_key.startswith("sk-"):
        raise ValueError("La clave no parece una OPENAI_API_KEY válida")
    values = _read_env_values()
    values.update({
        "OPERATIVA_AI_MODE": "openai",
        "OPENAI_API_KEY": openai_key,
        "OPERATIVA_AI_MODEL": values.get("OPERATIVA_AI_MODEL") or "gpt-4o-mini",
        "OPENAI_STT_MODEL": values.get("OPENAI_STT_MODEL") or "gpt-4o-mini-transcribe",
        "OPERATIVA_LANGUAGE": values.get("OPERATIVA_LANGUAGE") or "es",
        "OIDO_ALFI_LANGUAGE": values.get("OIDO_ALFI_LANGUAGE") or "es",
        "RECIPE_VOICE_LANGUAGE": values.get("RECIPE_VOICE_LANGUAGE") or "es",
        "OPERATIVA_AI_TIMEOUT": values.get("OPERATIVA_AI_TIMEOUT") or "12",
        "OPERATIVA_STT_TIMEOUT": values.get("OPERATIVA_STT_TIMEOUT") or "25",
        "RECIPE_AI_PROVIDER": values.get("RECIPE_AI_PROVIDER") or "auto",
    })
    if values.get("DEEPGRAM_API_KEY"):
        values["STT_PROVIDER"] = "deepgram"
        values["OPERATIVA_STT_MODE"] = "deepgram"
        values["DEEPGRAM_MODEL"] = values.get("DEEPGRAM_MODEL") or "nova-3"
    else:
        values["STT_PROVIDER"] = values.get("STT_PROVIDER") or "openai"
        values["OPERATIVA_STT_MODE"] = values.get("OPERATIVA_STT_MODE") or "openai"
    values["STT_LANGUAGE"] = values.get("STT_LANGUAGE") or "es"
    _write_env_values(values)


def _write_deepgram_env(deepgram_key: str, stt_language: str = "es") -> None:
    deepgram_key = (deepgram_key or "").strip()
    if not deepgram_key:
        raise ValueError("Clave vacía")
    values = _read_env_values()
    values.update({
        "DEEPGRAM_API_KEY": deepgram_key,
        "STT_PROVIDER": "deepgram",
        "OPERATIVA_STT_MODE": "deepgram",
        "STT_LANGUAGE": (stt_language or "es").strip() or "es",
        "DEEPGRAM_MODEL": values.get("DEEPGRAM_MODEL") or "nova-3",
        "OPERATIVA_AI_MODE": values.get("OPERATIVA_AI_MODE") or ("openai" if values.get("OPENAI_API_KEY") else "local"),
        "OPERATIVA_AI_MODEL": values.get("OPERATIVA_AI_MODEL") or "gpt-4o-mini",
        "OPENAI_STT_MODEL": values.get("OPENAI_STT_MODEL") or "gpt-4o-mini-transcribe",
        "OPERATIVA_LANGUAGE": values.get("OPERATIVA_LANGUAGE") or "es",
        "OIDO_ALFI_LANGUAGE": values.get("OIDO_ALFI_LANGUAGE") or "es",
        "RECIPE_VOICE_LANGUAGE": values.get("RECIPE_VOICE_LANGUAGE") or "es",
        "OPERATIVA_AI_TIMEOUT": values.get("OPERATIVA_AI_TIMEOUT") or "12",
        "OPERATIVA_STT_TIMEOUT": values.get("OPERATIVA_STT_TIMEOUT") or "25",
        "RECIPE_AI_PROVIDER": values.get("RECIPE_AI_PROVIDER") or "auto",
    })
    _write_env_values(values)


@router.post("/api/admin/openai_key/save")
def admin_save_openai_key(openai_api_key: str = Form(...)):
    try:
        _write_ai_env(openai_api_key)
        return RedirectResponse("/?page=admin&center_id=0#tab-ia&ok=openai_saved", status_code=303)
    except Exception as exc:
        return RedirectResponse(f"/?page=admin&center_id=0#tab-ia&err=openai_config_failed", status_code=303)


@router.post("/api/admin/deepgram_key/save")
def admin_save_deepgram_key(deepgram_api_key: str = Form(...), stt_language: str = Form("es")):
    try:
        _write_deepgram_env(deepgram_api_key, stt_language)
        return RedirectResponse("/?page=admin&center_id=0#tab-ia&ok=deepgram_saved", status_code=303)
    except Exception:
        return RedirectResponse("/?page=admin&center_id=0#tab-ia&err=deepgram_config_failed", status_code=303)


@router.post("/api/admin/openai_key/delete")
def admin_delete_openai_key():
    for key in SENSITIVE_ENV_KEYS:
        try:
            os.environ.pop(key, None)
        except Exception:
            pass
    for path in _project_env_paths():
        try:
            if path.exists():
                path.unlink()
        except Exception:
            pass
    return RedirectResponse("/?page=admin&center_id=0#tab-ia&ok=openai_deleted", status_code=303)


@router.post("/user/create_form")
def create_user_form(name: str = Form(...), role: str = Form('OPERATIVO'), center_id: int = Form(0), is_active: int = Form(1)):
    conn = db(); cur = conn.cursor()
    safe_name = (name or '').strip().upper()[:120]
    safe_role = (role or 'OPERATIVO').strip().upper()[:40]
    if safe_name:
        cur.execute("INSERT INTO users(name,role,center_id,is_active) VALUES(?,?,?,?)", (safe_name, safe_role, int(center_id or 0), 1 if int(is_active or 0) else 0))
        conn.commit()
    conn.close()
    return redirect_admin(center_id=0, ok=1)


@router.post("/user/{user_id}/update_form")
def update_user_form(user_id: int, name: str = Form(...), role: str = Form('OPERATIVO'), center_id: int = Form(0), is_active: int = Form(0)):
    conn = db(); cur = conn.cursor()
    safe_name = (name or '').strip().upper()[:120]
    safe_role = (role or 'OPERATIVO').strip().upper()[:40]
    cur.execute("UPDATE users SET name=?, role=?, center_id=?, is_active=? WHERE id=?", (safe_name, safe_role, int(center_id or 0), 1 if int(is_active or 0) else 0, int(user_id)))
    conn.commit(); conn.close()
    return redirect_admin(center_id=0, ok=1)


@router.post("/user/{user_id}/delete_form")
def delete_user_form(user_id: int):
    conn = db(); cur = conn.cursor()
    linked = 0
    try:
        linked = cur.execute("SELECT COUNT(*) FROM inventory_sessions WHERE responsible_user_id=?", (int(user_id),)).fetchone()[0]
    except Exception:
        linked = 0
    if linked:
        cur.execute("UPDATE users SET is_active=0 WHERE id=?", (int(user_id),))
    else:
        cur.execute("DELETE FROM users WHERE id=?", (int(user_id),))
    conn.commit(); conn.close()
    return redirect_admin(center_id=0, ok=1)


# ==============================================================================
# ADMIN · Modificadores TPV → consumo realista
# ==============================================================================

@router.post("/recipe_modifier/create_form")
def recipe_modifier_create_form(
    recipe_id: int = Form(0),
    name: str = Form(...),
    modifier_type: str = Form("REVIEW"),
    action: str = Form("REVIEW"),
    item_id: int = Form(0),
    subrecipe_id: int = Form(0),
    qty_delta: float = Form(0),
    unit: str = Form("g"),
    affects_stock: int = Form(1),
    price_extra: float = Form(0),
    notes: str = Form(""),
):
    conn = db(); cur = conn.cursor(); ensure_columns(cur); ensure_pos_modifier_tables(cur)
    try:
        create_recipe_modifier(
            cur, recipe_id=recipe_id, name=name, modifier_type=modifier_type, action=action,
            item_id=item_id, subrecipe_id=subrecipe_id, qty_delta=qty_delta, unit=unit,
            affects_stock=affects_stock, price_extra=price_extra, notes=notes,
        )
        conn.commit(); conn.close()
        return redirect_admin(center_id=0, ok="modifier_created")
    except Exception:
        conn.rollback(); conn.close()
        return redirect_admin(center_id=0, err="modifier_failed")


@router.post("/recipe_modifier/{modifier_id}/delete_form")
def recipe_modifier_delete_form(modifier_id: int):
    conn = db(); cur = conn.cursor(); ensure_pos_modifier_tables(cur)
    deactivate_recipe_modifier(cur, modifier_id)
    conn.commit(); conn.close()
    return redirect_admin(center_id=0, ok="modifier_disabled")


@router.post("/pos_modifier_map/create_form")
def pos_modifier_map_create_form(
    pos_modifier_name: str = Form(...),
    modifier_id: int = Form(...),
    recipe_id: int = Form(0),
    provider_name: str = Form(""),
    business_type: str = Form(""),
    notes: str = Form(""),
):
    conn = db(); cur = conn.cursor(); ensure_columns(cur); ensure_pos_modifier_tables(cur)
    try:
        create_pos_modifier_map(
            cur, pos_modifier_name=pos_modifier_name, modifier_id=modifier_id,
            recipe_id=recipe_id, provider_name=provider_name, business_type=business_type, notes=notes,
        )
        conn.commit(); conn.close()
        return redirect_admin(center_id=0, ok="modifier_map_created")
    except Exception:
        conn.rollback(); conn.close()
        return redirect_admin(center_id=0, err="modifier_map_failed")


@router.post("/pos_modifier_map/{map_id}/delete_form")
def pos_modifier_map_delete_form(map_id: int):
    conn = db(); cur = conn.cursor(); ensure_pos_modifier_tables(cur)
    deactivate_pos_modifier_map(cur, map_id)
    conn.commit(); conn.close()
    return redirect_admin(center_id=0, ok="modifier_map_disabled")


@router.post("/pos_modifier_review/create_form")
def pos_modifier_review_create_form(
    recipe_id: int = Form(0),
    raw_customer_note: str = Form(...),
    center_id: int = Form(0),
    pos_item_name: str = Form(""),
):
    """Guarda una nota libre TPV para aprendizaje supervisado.

    No mueve stock ni modifica receta maestra; sirve para simular/registrar excepciones.
    """
    conn = db(); cur = conn.cursor(); ensure_columns(cur); ensure_pos_modifier_tables(cur)
    try:
        register_modifier_review_from_note(cur, recipe_id=recipe_id, note=raw_customer_note, center_id=center_id, pos_item_name=pos_item_name)
        conn.commit(); conn.close()
        return redirect_admin(center_id=0, ok="modifier_review_created")
    except Exception:
        conn.rollback(); conn.close()
        return redirect_admin(center_id=0, err="modifier_review_failed")


@router.post("/pos_modifier_review/{review_id}/archive_form")
def pos_modifier_review_archive_form(review_id: int):
    conn = db(); cur = conn.cursor(); ensure_pos_modifier_tables(cur)
    cur.execute("UPDATE pos_modifier_review_queue SET review_status='ARCHIVADO', updated_at=datetime('now') WHERE id=?", (int(review_id or 0),))
    conn.commit(); conn.close()
    return redirect_admin(center_id=0, ok="modifier_review_archived")
