from __future__ import annotations
import os
import html
import re
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse

from app.core import DB_PATH, UPLOADS_DIR, _normalize_uploaded_image_bytes_to_jpeg
from .ai_provider_service import RecipeAIService
from .voice_service import RecipeVoiceService
from .storage_service import (
    init_recipe_ai_storage,
    save_imported_recipe_draft,
    list_imported_recipe_drafts,
    get_imported_recipe_draft,
    link_ingredient_to_catalog_item,
    link_ingredient_to_subrecipe,
    mark_ingredient_pending_catalog,
    mark_draft_ready_to_convert,
    update_draft_cost_status,
)
from .costing_service import calculate_recipe_cost_preview
from .commit_service import commit_imported_draft_to_master_recipe

router = APIRouter(prefix="/recipe-ai", tags=["Recipe AI LAB"])

ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
ALLOWED_AUDIO_EXT = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm", ".ogg"}
MAX_UPLOAD_MB = int(os.environ.get("RECIPE_AI_MAX_UPLOAD_MB", "25"))


def get_db_path() -> str:
    return str(DB_PATH)


def ensure_upload_dir() -> Path:
    p = Path(os.environ.get("RECIPE_AI_UPLOAD_DIR") or (UPLOADS_DIR / "recipe_ai_lab"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _safe_filename(filename: str | None, allowed_ext: set[str], fallback_ext: str) -> str:
    raw = filename or f"recipe_ai{fallback_ext}"
    suffix = Path(raw).suffix.lower() or fallback_ext
    if suffix not in allowed_ext:
        raise HTTPException(status_code=400, detail=f"Formato no permitido: {suffix}")
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(raw).stem).strip("._-")[:60] or "recipe_ai"
    return f"{stem}_{uuid.uuid4().hex[:10]}{suffix}"


async def _save_upload(file: UploadFile, allowed_ext: set[str], fallback_ext: str) -> Path:
    name = _safe_filename(file.filename, allowed_ext, fallback_ext)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Archivo vacío.")
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Archivo superior a {MAX_UPLOAD_MB} MB.")
    path = ensure_upload_dir() / name
    path.write_bytes(data)
    return path


async def _save_image_upload(file: UploadFile) -> Path:
    """Guarda fotos de Recetas IA normalizadas a JPG.

    Motivo: iPhone/Safari puede subir HEIC/HEIF aunque el formulario use image/*.
    Antes se rechazaba con JSON crudo {"detail":"Formato no permitido: .heic"}.
    Ahora se acepta HEIC/HEIF y se convierte a JPG con el normalizador común del sistema
    (Pillow para JPG/PNG/WEBP y sips en Mac para HEIC/HEIF).
    """
    original = file.filename or "recipe_ai.jpg"
    suffix = Path(original).suffix.lower() or ".jpg"
    if suffix not in ALLOWED_IMAGE_EXT:
        raise HTTPException(status_code=400, detail=f"Formato no permitido: {suffix}")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Archivo vacío.")
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Archivo superior a {MAX_UPLOAD_MB} MB.")

    jpg_name, jpg_bytes = _normalize_uploaded_image_bytes_to_jpeg(original, data, quality=92, max_side=2400)
    if not jpg_bytes:
        if suffix in {".heic", ".heif"}:
            raise HTTPException(
                status_code=400,
                detail="No se pudo convertir HEIC/HEIF a JPG en este equipo. Prueba de nuevo o cambia la cámara a formato compatible; en Mac se usa sips automáticamente.",
            )
        raise HTTPException(status_code=400, detail="No se pudo leer la imagen. Usa JPG, PNG, WEBP, HEIC o HEIF.")

    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(jpg_name).stem).strip("._-")[:60] or "recipe_ai"
    name = f"{stem}_{uuid.uuid4().hex[:10]}.jpg"
    path = ensure_upload_dir() / name
    path.write_bytes(jpg_bytes)
    return path


def _connect():
    try:
        from app.core import db as core_db
        return core_db()
    except Exception:
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        return conn


def load_catalog_items() -> list[dict]:
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT id, name, unit, current_price, waste_default_pct, stock_area
                  FROM items
                 ORDER BY LOWER(name)
                """
            ).fetchall()
            return [
                {
                    "item_id": int(r["id"]),
                    "name": r["name"],
                    "unit": r["unit"],
                    "unit_cost": float(r["current_price"] or 0),
                    "waste_default_pct": float(r["waste_default_pct"] or 0),
                    "stock_area": r["stock_area"] or "",
                }
                for r in rows
            ]
    except Exception:
        return []


def load_subrecipes() -> list[dict]:
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT id, name, yield_final_qty, yield_final_unit, suggested_price
                  FROM recipes
                 WHERE COALESCE(is_subrecipe,0)=1
                 ORDER BY LOWER(name)
                """
            ).fetchall()
            return [
                {
                    "subrecipe_id": int(r["id"]),
                    "name": r["name"],
                    "yield_quantity": float(r["yield_final_qty"] or 0),
                    "yield_unit": r["yield_final_unit"] or "g",
                    "unit_cost": float(r["suggested_price"] or 0),
                }
                for r in rows
            ]
    except Exception:
        return []


def load_price_map() -> dict:
    try:
        with _connect() as conn:
            rows = conn.execute("SELECT id, name, unit, current_price FROM items ORDER BY LOWER(name)").fetchall()
            return {int(r["id"]): {"name": r["name"], "unit_cost": float(r["current_price"] or 0), "unit": r["unit"] or "kg"} for r in rows}
    except Exception:
        return {}


def load_subrecipe_cost_map() -> dict:
    # Conservador: solo usa coste si existe suggested_price. No inventa coste de subreceta.
    try:
        with _connect() as conn:
            rows = conn.execute("SELECT id, name, yield_final_unit, suggested_price FROM recipes WHERE COALESCE(is_subrecipe,0)=1").fetchall()
            return {int(r["id"]): {"name": r["name"], "unit_cost": float(r["suggested_price"] or 0), "unit": r["yield_final_unit"] or "kg"} for r in rows if float(r["suggested_price"] or 0) > 0}
    except Exception:
        return {}


@router.on_event("startup")
def startup_recipe_ai_lab():
    init_recipe_ai_storage(get_db_path())


@router.post("/import/text")
def import_recipe_text(text: str = Form(...), actor: Optional[str] = Form(None)):
    draft = RecipeAIService(load_catalog_items(), load_subrecipes()).import_from_text(text, actor)
    draft_id = save_imported_recipe_draft(get_db_path(), draft, actor)
    return {"ok": True, "draft_id": draft_id, "draft": draft.to_dict()}


@router.post("/import/image")
async def import_recipe_image(file: UploadFile = File(...), actor: Optional[str] = Form(None)):
    path = await _save_image_upload(file)
    draft = RecipeAIService(load_catalog_items(), load_subrecipes()).import_from_image(str(path), actor)
    draft_id = save_imported_recipe_draft(get_db_path(), draft, actor)
    return {"ok": True, "draft_id": draft_id, "draft": draft.to_dict()}


@router.post("/import/voice")
async def import_recipe_voice(file: UploadFile = File(...), actor: Optional[str] = Form(None)):
    path = await _save_upload(file, ALLOWED_AUDIO_EXT, ".m4a")
    result = RecipeVoiceService(load_catalog_items(), load_subrecipes()).import_recipe_from_audio(
        str(path), actor, str(ensure_upload_dir() / f"response_{path.stem}.mp3")
    )
    draft_id = save_imported_recipe_draft(get_db_path(), result.draft, actor) if result.draft else None
    return {"ok": result.draft is not None, "draft_id": draft_id, "result": result.to_dict()}


@router.get("/drafts")
def list_drafts(status: Optional[str] = None, limit: int = 50):
    return {"ok": True, "drafts": list_imported_recipe_drafts(get_db_path(), status, limit)}


@router.get("/drafts/{draft_id}")
def get_draft(draft_id: int):
    draft = get_imported_recipe_draft(get_db_path(), draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Borrador no encontrado.")
    return {"ok": True, "draft": draft.to_dict()}


@router.post("/ingredients/{ingredient_id}/link-item")
def link_item(ingredient_id: int, item_id: int = Form(...), item_name: str = Form(...), actor: Optional[str] = Form(None)):
    return {"ok": link_ingredient_to_catalog_item(get_db_path(), ingredient_id, item_id, item_name, actor)}


@router.post("/ingredients/{ingredient_id}/link-subrecipe")
def link_subrecipe(ingredient_id: int, subrecipe_id: int = Form(...), subrecipe_name: str = Form(...), actor: Optional[str] = Form(None)):
    return {"ok": link_ingredient_to_subrecipe(get_db_path(), ingredient_id, subrecipe_id, subrecipe_name, actor)}


@router.post("/ingredients/{ingredient_id}/pending-catalog")
def pending_catalog(ingredient_id: int, actor: Optional[str] = Form(None)):
    return {"ok": mark_ingredient_pending_catalog(get_db_path(), ingredient_id, actor)}


@router.post("/drafts/{draft_id}/cost")
def calculate_cost(draft_id: int, actor: Optional[str] = Form(None)):
    draft = get_imported_recipe_draft(get_db_path(), draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Borrador no encontrado.")
    preview = calculate_recipe_cost_preview(draft, load_price_map(), load_subrecipe_cost_map())
    update_draft_cost_status(get_db_path(), draft_id, preview.cost_status, preview.warnings, actor)
    return {"ok": True, "cost": preview.to_dict()}


@router.post("/drafts/{draft_id}/ready")
def mark_ready(draft_id: int, actor: Optional[str] = Form(None)):
    ok, errors = mark_draft_ready_to_convert(get_db_path(), draft_id, actor)
    return {"ok": ok, "errors": errors}


@router.post("/drafts/{draft_id}/commit")
def commit_draft(draft_id: int, actor: Optional[str] = Form(None)):
    return commit_imported_draft_to_master_recipe(get_db_path(), draft_id, actor).to_dict()



def _fmt_date_time(value: str | None) -> tuple[str, str]:
    raw = (value or "").strip()
    if not raw:
        return "--/--/----", "--:--"
    raw2 = raw.replace("T", " ").split(".")[0]
    try:
        dt = datetime.fromisoformat(raw2)
        return dt.strftime("%d/%m/%Y"), dt.strftime("%H:%M")
    except Exception:
        return (raw2[:10] if len(raw2) >= 10 else raw2), (raw2[11:16] if len(raw2) >= 16 else "--:--")

def _get_draft_row(draft_id: int) -> dict | None:
    try:
        with _connect() as conn:
            r = conn.execute("SELECT * FROM recipe_import_drafts WHERE id=?", (int(draft_id),)).fetchone()
            return {k: r[k] for k in r.keys()} if r else None
    except Exception:
        return None

def _html_list(items) -> str:
    return "".join(f"<li>{html.escape(str(x))}</li>" for x in (items or [])) or "<li>Sin datos.</li>"

def _render_draft_result(draft_id: int, *, title: str = "Resultado IA") -> HTMLResponse:
    draft = get_imported_recipe_draft(get_db_path(), int(draft_id))
    row = _get_draft_row(int(draft_id)) or {}
    if not draft:
        return HTMLResponse(_ui_shell(title, "<div class='card danger'><h1>Borrador no encontrado</h1><p>No se pudo recuperar el borrador.</p><div class='actions'><a class='btn' href='/recipe-ai/ui'>Volver</a></div></div>"), status_code=404)
    rev_date, rev_time = _fmt_date_time(row.get("review_at") or row.get("created_at"))
    created_date, created_time = _fmt_date_time(row.get("created_at"))
    ing_rows = ""
    for ing in draft.ingredients:
        ing_rows += f"""
        <tr><td>{html.escape(ing.normalized_name or ing.original_text or '')}</td><td>{html.escape(str(ing.quantity_net or ''))}</td><td>{html.escape(str(ing.unit or ''))}</td><td>{html.escape(str(ing.match_status or ''))}</td><td>{html.escape(str(ing.notes or ''))}</td></tr>
        """
    if not ing_rows:
        ing_rows = "<tr><td colspan='5' class='muted'>No se detectaron ingredientes. Reintenta la lectura o revisa manualmente.</td></tr>"
    empty_warning = ""
    if not draft.ingredients:
        empty_warning = """
        <div class='notice'><strong>Imagen pendiente de revisión.</strong><br>No se detectaron ingredientes. No se convierte en receta maestra y no se inventan datos.</div>
        """
    body = f"""
    <h1>{html.escape(title)}</h1>
    <div class='card'>
      <div class='draft-head'>
        <div><div class='muted'>Borrador #{int(draft_id)}</div><h2>{html.escape(draft.recipe_name or 'RECETA PENDIENTE DE REVISION')}</h2></div>
        <div class='chip-wrap'>
          <span class='chip'>Estado: {html.escape(str(draft.import_status))}</span>
          <span class='chip'>Coste: {html.escape(str(draft.cost_status))}</span>
          <span class='chip'>Revisión: {rev_date}</span>
          <span class='chip'>Hora: {rev_time}</span>
          <span class='chip chip-muted'>Creado: {created_date}</span>
          <span class='chip chip-muted'>Hora: {created_time}</span>
        </div>
      </div>
      {empty_warning}
      <h3>Ingredientes detectados</h3>
      <table><tr><th>Ingrediente</th><th>Cant.</th><th>Ud.</th><th>Estado</th><th>Notas</th></tr>{ing_rows}</table>
      <h3>Elaboración</h3><ol>{_html_list(draft.elaboration_steps)}</ol>
      <h3>Avisos</h3><ul>{_html_list(draft.warnings)}</ul>
      <div class='actions'>
        <a class='btn' href='/recipe-ai/ui'>Volver a IA Recetas</a>
        <a class='btn' href='/recipe-ai/ui/drafts'>Ver borradores</a>
        <a class='btn' href='/recipe-ai/ui/import-image'>Reintentar foto</a>
      </div>
    </div>
    """
    return HTMLResponse(_ui_shell(title, body))


def _ui_shell(title: str, body: str) -> str:
    nav = """
    <div class='ai-nav'>
      <a class='ai-main-return' href='/?page=inicio&center_id=1'>← Inicio System MAC</a>
      <a href='/?page=laboratorio&center_id=1'>🔬 Laboratorio</a>
      <a href='/recipe-ai/ui'>🤖 IA Recetas</a>
      <a href='/recipe-ai/ui/drafts'>Borradores</a>
    </div>
    """
    return f"""<!doctype html><html lang='es'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
    <title>System MAC · {html.escape(title)}</title>
    <style>
      :root{{--bg:#080d15;--panel:#111827;--panel2:#151d29;--line:rgba(255,255,255,.11);--text:#f3f4f6;--muted:#aeb6c2;--gold:#d4a64a}}
      *{{box-sizing:border-box}} body{{margin:0;font-family:Inter,Arial,sans-serif;background:radial-gradient(circle at 20% 0%,#172033 0,#080d15 42%,#060910 100%);color:var(--text)}}
      .shell{{max-width:1100px;margin:0 auto;padding:28px 18px 44px}} .brand{{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:18px}}
      .brand-main{{font-size:24px;font-weight:900}} .brand-main span{{color:var(--gold)}} .brand-sub{{font-size:11px;color:var(--muted);margin-top:2px}}
      .ai-nav{{display:flex;gap:8px;flex-wrap:wrap}} .ai-nav a,.btn,button{{display:inline-flex;align-items:center;justify-content:center;gap:6px;min-height:40px;padding:9px 13px;border-radius:12px;border:1px solid var(--line);background:#151d29;color:var(--text);text-decoration:none;font-weight:800;cursor:pointer}}
      .ai-nav a:hover,.btn:hover,button:hover{{border-color:rgba(212,166,74,.55);color:#ffe4a5}} .ai-main-return{{border-color:rgba(212,166,74,.45)!important;background:rgba(212,166,74,.12)!important;color:#ffe4a5!important}} .primary{{background:linear-gradient(180deg,#e3b455,#c9912e);color:#201400;border-color:#e6b95d}}
      h1{{font-size:26px;margin:8px 0 6px}} p{{color:var(--muted);line-height:1.45}} .card{{background:rgba(17,24,39,.94);border:1px solid var(--line);border-radius:18px;padding:16px;margin:12px 0;box-shadow:0 16px 38px rgba(0,0,0,.22)}}
      .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}} .choice{{display:block;padding:16px;border-radius:16px;background:#151d29;border:1px solid var(--line);text-decoration:none;color:var(--text)}} .choice b{{display:block;font-size:17px;margin-bottom:4px}} .choice small{{color:var(--muted)}}
      textarea,input[type=file],input[type=text],select{{width:100%;border-radius:13px;border:1px solid var(--line);background:#0b111b;color:var(--text);padding:11px;font-size:15px}} textarea{{min-height:260px}} table{{width:100%;border-collapse:collapse;margin-top:10px}} th,td{{padding:9px;border-bottom:1px solid var(--line);text-align:left;font-size:13px}} th{{color:#ffe4a5}} .notice{{border:1px solid rgba(212,166,74,.35);background:rgba(212,166,74,.08);border-radius:14px;padding:12px;color:#f6e6bd}} .actions{{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}} .chip-wrap{{display:flex;gap:7px;flex-wrap:wrap;align-items:center}} .chip{{display:inline-flex;padding:6px 9px;border-radius:999px;background:rgba(212,166,74,.13);border:1px solid rgba(212,166,74,.28);color:#ffe4a5;font-size:12px;font-weight:900}} .chip-muted{{background:rgba(255,255,255,.06);border-color:var(--line);color:var(--muted)}} .draft-head{{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap}} .danger{{border-color:rgba(255,80,80,.45)}} h2{{margin:.2rem 0 .6rem}} ol,ul{{line-height:1.55}} .muted{{color:var(--muted)}}
      @media(max-width:760px){{.brand{{align-items:flex-start;flex-direction:column}} .ai-nav{{width:100%;display:grid;grid-template-columns:1fr 1fr;}} .ai-nav a{{min-height:44px;font-size:14px}} h1{{font-size:23px}}}}
    </style></head><body><div class='shell'><div class='brand'><div><div class='brand-main'>System <span>MAC</span></div><div class='brand-sub'>Created by Mauro Ciccarelli · IA laboratorio aislado</div></div>{nav}</div>{body}</div></body></html>"""


@router.get("/ui", response_class=HTMLResponse)
def ui_home():
    body = """
    <h1>Recetas IA · laboratorio aislado</h1>
    <p>Crea borradores desde texto, foto o voz. No modifica recetas maestras salvo que se active explícitamente <b>RECIPE_AI_ALLOW_COMMIT=1</b>.</p>
    <div class='grid'>
      <a class='choice' href='/recipe-ai/ui/import-text'><b>Texto</b><small>Pegar receta o escandallo escrito.</small></a>
      <a class='choice' href='/recipe-ai/ui/import-image'><b>Foto / lectura</b><small>Subir foto de receta para crear borrador.</small></a>
      <a class='choice' href='/recipe-ai/ui/import-voice'><b>Voz</b><small>Subir audio de receta para transcribir.</small></a>
      <a class='choice' href='/recipe-ai/ui/drafts'><b>Borradores</b><small>Revisar pendientes, coste y alta de ingredientes.</small></a>
    </div>
    <div class='notice'><strong>Regla de seguridad:</strong> ingredientes nuevos quedan dentro del borrador como <b>PENDIENTE_ALTA</b> y el coste queda <b>COSTE_INCOMPLETO</b> hasta vincularlos o darlos de alta.</div>
    """
    return _ui_shell("Recetas IA LAB", body)


@router.get("/ui/import-text", response_class=HTMLResponse)
def ui_import_text():
    body = """
    <h1>Importar receta por texto</h1><p>Se guardará como borrador IA para revisión.</p>
    <div class='card'><form method='post' action='/recipe-ai/ui/import-text'><input type='hidden' name='actor' value='Mauro'><textarea name='text' placeholder='Pega aquí receta, ingredientes, cantidades, elaboración y alérgenos si los tienes.'></textarea><div class='actions'><button class='primary' type='submit'>Crear borrador IA</button><a class='btn' href='/recipe-ai/ui'>Volver</a></div></form></div>
    """
    return _ui_shell("Importar receta por texto", body)


@router.get("/ui/import-image", response_class=HTMLResponse)
def ui_import_image():
    body = """
    <h1>Importar receta por foto</h1><p>Sube una foto o captura de una receta. La IA crea un borrador; no toca recetas maestras.</p>
    <div class='card'><form method='post' action='/recipe-ai/ui/import-image' enctype='multipart/form-data'><input type='hidden' name='actor' value='Mauro'><input type='file' name='file' accept='image/*,.heic,.heif,image/heic,image/heif' capture='environment'><p class='muted'>Acepta JPG, PNG, WEBP y fotos HEIC/HEIF de iPhone; el sistema las normaliza a JPG antes de analizarlas.</p><div class='actions'><button class='primary' type='submit'>Subir y analizar</button><a class='btn' href='/recipe-ai/ui'>Volver</a></div></form></div>
    """
    return _ui_shell("Foto receta", body)


@router.get("/ui/import-voice", response_class=HTMLResponse)
def ui_import_voice():
    body = """
    <h1>Dictar receta por voz</h1><p>Sube un audio con la receta. El sistema transcribe y crea un borrador revisable.</p>
    <div class='card'><form method='post' action='/recipe-ai/ui/import-voice' enctype='multipart/form-data'><input type='hidden' name='actor' value='Mauro'><input type='file' name='file' accept='audio/*' capture><div class='actions'><button class='primary' type='submit'>Transcribir y analizar</button><a class='btn' href='/recipe-ai/ui'>Volver</a></div></form></div>
    """
    return _ui_shell("Voz receta", body)


@router.post("/ui/import-text", response_class=HTMLResponse)
def ui_import_text_post(text: str = Form(...), actor: Optional[str] = Form(None)):
    draft = RecipeAIService(load_catalog_items(), load_subrecipes()).import_from_text(text, actor)
    draft_id = save_imported_recipe_draft(get_db_path(), draft, actor)
    return _render_draft_result(draft_id, title="Borrador IA desde texto")

@router.post("/ui/import-image", response_class=HTMLResponse)
async def ui_import_image_post(file: UploadFile = File(...), actor: Optional[str] = Form(None)):
    try:
        path = await _save_image_upload(file)
        draft = RecipeAIService(load_catalog_items(), load_subrecipes()).import_from_image(str(path), actor)
        draft_id = save_imported_recipe_draft(get_db_path(), draft, actor)
        return _render_draft_result(draft_id, title="Borrador IA desde foto")
    except HTTPException as exc:
        msg = html.escape(str(exc.detail or "No se pudo importar la imagen."))
        body = f"""
        <div class='card danger'>
          <h1>No se pudo importar la foto</h1>
          <p>{msg}</p>
          <p class='muted'>No se ha creado ningún borrador vacío. Vuelve a intentarlo desde la cámara o selecciona JPG/PNG/HEIC.</p>
          <div class='actions'><a class='btn' href='/recipe-ai/ui/import-image'>Reintentar foto</a><a class='btn' href='/recipe-ai/ui'>Volver</a></div>
        </div>
        """
        return HTMLResponse(_ui_shell("Foto receta", body), status_code=exc.status_code)

@router.post("/ui/import-voice", response_class=HTMLResponse)
async def ui_import_voice_post(file: UploadFile = File(...), actor: Optional[str] = Form(None)):
    path = await _save_upload(file, ALLOWED_AUDIO_EXT, ".m4a")
    result = RecipeVoiceService(load_catalog_items(), load_subrecipes()).import_recipe_from_audio(
        str(path), actor, str(ensure_upload_dir() / f"response_{path.stem}.mp3")
    )
    if not result.draft:
        body = "<div class='card'><h1>No se pudo crear borrador</h1><p>No se detectó una receta válida en el audio.</p><div class='actions'><a class='btn' href='/recipe-ai/ui/import-voice'>Reintentar</a><a class='btn' href='/recipe-ai/ui'>Volver</a></div></div>"
        return HTMLResponse(_ui_shell("Voz receta", body))
    draft_id = save_imported_recipe_draft(get_db_path(), result.draft, actor)
    return _render_draft_result(draft_id, title="Borrador IA desde voz")

@router.get("/ui/drafts/{draft_id}", response_class=HTMLResponse)
def ui_draft_detail(draft_id: int):
    return _render_draft_result(draft_id, title="Detalle borrador IA")


@router.get("/ui/drafts", response_class=HTMLResponse)
def ui_drafts():
    rows = ""
    for d in list_imported_recipe_drafts(get_db_path(), None, 50):
        did = int(d.get('id') or 0)
        rev_d, rev_h = _fmt_date_time(d.get('review_at') or d.get('created_at'))
        rows += "<tr><td>{}</td><td>{}</td><td><span class='chip'>{}</span><br><span class='chip chip-muted'>Hora: {}</span></td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td><a class='btn' href='/recipe-ai/ui/drafts/{}'>Abrir</a></td><td><form method='post' action='/recipe-ai/drafts/{}/cost'><button>Coste</button></form></td></tr>".format(
            did, html.escape(str(d.get('recipe_name') or '')), rev_d, rev_h, html.escape(str(d.get('import_status') or '')), html.escape(str(d.get('cost_status') or '')), int(d.get('ingredient_count') or 0), int(d.get('pending_count') or 0), did, did
        )
    body = f"""
    <h1>Borradores IA</h1><p>Revisa coste, pendientes y estado antes de convertir.</p>
    <div class='card'><table><tr><th>ID</th><th>Receta</th><th>Revisión</th><th>Estado</th><th>Coste</th><th>Ingredientes</th><th>Pendientes</th><th>Abrir</th><th>Coste</th></tr>{rows}</table></div>
    <div class='actions'><a class='btn' href='/recipe-ai/ui'>Volver a IA Recetas</a></div>
    """
    return _ui_shell("Borradores IA", body)
