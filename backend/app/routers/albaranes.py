# ==============================================================================
# BLOQUE ALBARANES · Albaranes, fotos, OCR, validación
# ==============================================================================
from fastapi import APIRouter, Form, File, UploadFile, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from typing import Optional
from datetime import datetime
from pathlib import Path
import re
import sqlite3
import threading
import time
import multiprocessing as mp
import queue as queue_mod
from difflib import SequenceMatcher

from app.services.receipts_service import form_int, parse_receipt_base_form, receipt_page_url

from app.core import (
    db, _retry_db_write, _is_db_locked_error, _parse_float, fmt_num,
    _resolve_item_id, _resolve_item_id_strict, _norm_text,
    _ensure_pending_supplier, _insert_supplier_compatible, _resolve_supplier_id_by_name,
    _cleanup_pending_supplier, _collect_uploads_from_form, _resolve_receipt_warehouse,
    _normalize_receipt_upload_to_jpg, _build_receipt_ocr_work_jpg,
    _factor_for_units, _supplier_factor_for_item,
    _ocr_lock_path, _ocr_lock_is_recent, _ocr_lock_touch, _ocr_lock_clear,
    _refresh_ocr_summary, cleanup_receipt_photos,
    UPLOADS_DIR, _cache_bust_token,
)
from app.core import safe_insert_returning

router = APIRouter()


# ==============================================================================
# HELPERS INTERNOS ALBARANES
# ==============================================================================

def _mark_receipt_ocr_processing(receipt_id: int):
    now = datetime.utcnow().isoformat()
    def _writer(connx, curx):
        curx.execute("DELETE FROM receipt_ocr_lines WHERE ocr_run_id IN (SELECT id FROM receipt_ocr_runs WHERE receipt_id=?)", (int(receipt_id),))
        curx.execute("DELETE FROM receipt_ocr_runs WHERE receipt_id=?", (int(receipt_id),))
        curx.execute(
            """INSERT INTO receipt_ocr_runs(receipt_id,status,supplier_raw,doc_number_raw,doc_date_raw,summary,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (int(receipt_id), "PROCESSING", "", "", None, "Procesando OCR…", now))
    _retry_db_write(_writer, attempts=5, delay=0.35)


def _mark_receipt_ocr_error(receipt_id: int, message: str):
    safe_msg = (message or "OCR falló").strip()[:220]
    def _writer_err(connx, curx):
        row = curx.execute("SELECT id FROM receipt_ocr_runs WHERE receipt_id=? ORDER BY id DESC LIMIT 1",
                           (int(receipt_id),)).fetchone()
        if row:
            curx.execute("UPDATE receipt_ocr_runs SET status=?,summary=? WHERE id=?",
                         ("ERROR", safe_msg, int(row["id"])))
        else:
            curx.execute(
                """INSERT INTO receipt_ocr_runs(receipt_id,status,supplier_raw,doc_number_raw,doc_date_raw,summary,created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (int(receipt_id), "ERROR", "", "", None, safe_msg, datetime.utcnow().isoformat()))
    _retry_db_write(_writer_err, attempts=3, delay=0.35)


def _ocr_run_worker_entry(receipt_id: int, q):
    """Worker subprocess — importa el OCR engine solo en el subprocess para aislar memoria."""
    try:
        from app.ocr.engine import _build_receipt_ocr_stub
        connx = db()
        curx = connx.cursor()
        run_id = _build_receipt_ocr_stub(curx, int(receipt_id))
        connx.commit()
        rr = curx.execute("SELECT status,summary FROM receipt_ocr_runs WHERE id=?", (int(run_id),)).fetchone()
        count_row = curx.execute("SELECT COUNT(*) c FROM receipt_ocr_lines WHERE ocr_run_id=?", (int(run_id),)).fetchone()
        connx.close()
        q.put({"ok": True, "run_id": int(run_id), "status": (rr["status"] if rr else ""),
               "summary": (rr["summary"] if rr else ""), "lines": int(count_row["c"] if count_row else 0)})
    except Exception as e:
        try:
            q.put({"ok": False, "error": str(e)[:400]})
        except Exception:
            pass


def _run_receipt_ocr_background(receipt_id: int):
    proc = None
    q = None
    timeout_sec = 70
    photo_count = 0
    try:
        try:
            connc = db(); curc = connc.cursor()
            prow = curc.execute("SELECT COUNT(*) c FROM receipt_photos WHERE receipt_id=?", (int(receipt_id),)).fetchone()
            photo_count = int(prow["c"] if prow and prow["c"] is not None else 0)
            connc.close()
        except Exception:
            photo_count = 0
        if photo_count >= 2:
            timeout_sec = min(180, 70 + ((photo_count - 1) * 45))
        print(f"OCR_BG_START receipt={int(receipt_id)} photos={photo_count} timeout={timeout_sec}")
        ctx = mp.get_context("spawn")
        q = ctx.Queue()
        proc = ctx.Process(target=_ocr_run_worker_entry, args=(int(receipt_id), q), daemon=True)
        proc.start()
        proc.join(timeout_sec)
        if proc.is_alive():
            print(f"OCR_TIMEOUT receipt={int(receipt_id)} timeout={timeout_sec}")
            try:
                proc.terminate(); proc.join(5)
            except Exception:
                pass
            extra = f" con {photo_count} foto(s)" if photo_count > 1 else ""
            _mark_receipt_ocr_error(int(receipt_id), f"OCR agotó tiempo ({timeout_sec}s){extra}. Usa carga manual o reintenta.")
            return
        try:
            payload = q.get_nowait()
        except queue_mod.Empty:
            payload = {"ok": False, "error": "worker_sin_respuesta"}
        if payload.get("ok"):
            print(f"OCR_BG_DONE receipt={int(receipt_id)} status={payload.get('status','')} lines={int(payload.get('lines',0))}")
        else:
            err = payload.get("error") or "worker_error"
            print(f"OCR_BG_FAIL receipt={int(receipt_id)} reason={err}")
            _mark_receipt_ocr_error(int(receipt_id), f"OCR falló: {str(err)[:160]}")
    except Exception as e:
        print(f"OCR_BG_FAIL receipt={int(receipt_id)} reason={e}")
        try:
            _mark_receipt_ocr_error(int(receipt_id), f"OCR falló: {str(e)[:160]}")
        except Exception:
            pass
    finally:
        try:
            if q is not None: q.close()
        except Exception:
            pass
        try:
            if proc is not None and proc.is_alive():
                proc.terminate(); proc.join(2)
        except Exception:
            pass
        _ocr_lock_clear(int(receipt_id))


def _process_receipt_ocr_redirect(receipt_id: int):
    print(f"OCR_TRIGGER receipt={int(receipt_id)}")
    conn = db(); cur = conn.cursor()
    rh = cur.execute("SELECT id,status,center_id FROM receipts WHERE id=?", (int(receipt_id),)).fetchone()
    latest_run = cur.execute("SELECT id,status,summary FROM receipt_ocr_runs WHERE receipt_id=? ORDER BY id DESC LIMIT 1",
                             (int(receipt_id),)).fetchone()
    conn.close()
    if not rh:
        return RedirectResponse(url=receipt_page_url(aid=receipt_id, err=1), status_code=303)
    latest_status = (latest_run["status"] or "").upper() if latest_run else ""
    if latest_run and latest_status in ("READ", "PARTIAL", "DONE", "READY", "ERROR", "EMPTY"):
        print(f"OCR_FORCE_REBUILD receipt={int(receipt_id)} prev_status={latest_status}")
    if latest_run and latest_status == "PROCESSING":
        print(f"OCR_FORCE_BREAK_PROCESSING receipt={int(receipt_id)}")
    if _ocr_lock_is_recent(int(receipt_id), max_age_sec=90):
        print(f"OCR_FORCE_BREAK_LOCK receipt={int(receipt_id)}")
        _ocr_lock_clear(int(receipt_id))
    try:
        _ocr_lock_touch(int(receipt_id))
        _mark_receipt_ocr_processing(int(receipt_id))
        print(f"OCR_BG_QUEUE receipt={int(receipt_id)}")
        t = threading.Thread(target=_run_receipt_ocr_background, args=(int(receipt_id),), daemon=True)
        t.start()
        return RedirectResponse(
            url=receipt_page_url(center_id=int(rh['center_id']), aid=receipt_id, ocr_wait=1, ts=_cache_bust_token(), anchor="ocrSection"),
            status_code=303)
    except sqlite3.OperationalError as e:
        msg = str(e).lower()
        print(f"OCR_FAIL receipt={int(receipt_id)} reason={e}")
        _ocr_lock_clear(int(receipt_id))
        if "locked" in msg:
            return RedirectResponse(
                url=receipt_page_url(center_id=int(rh['center_id']), aid=receipt_id, ocr_err="locked", ts=_cache_bust_token(), anchor="ocrSection"),
                status_code=303)
        return RedirectResponse(
            url=receipt_page_url(center_id=int(rh['center_id']), aid=receipt_id, ocr_err=1, ts=_cache_bust_token(), anchor="ocrSection"),
            status_code=303)


# ==============================================================================
# CREAR ALBARÁN
# ==============================================================================

@router.post("/receipt/new_form")
async def receipt_new_form(request: Request):
    now = datetime.utcnow().isoformat()
    form = await request.form()

    receipt_data = parse_receipt_base_form(form)
    center_id = receipt_data["center_id"]
    warehouse_id = receipt_data["warehouse_id"]
    supplier_id = receipt_data["supplier_id"]
    doc_number = receipt_data["doc_number"]
    doc_date = receipt_data["doc_date"]
    note = receipt_data["note"]
    new_supplier_name = receipt_data["new_supplier_name"]
    new_supplier_phone = receipt_data["new_supplier_phone"]
    new_supplier_email = receipt_data["new_supplier_email"]
    new_supplier_tax_id = receipt_data["new_supplier_tax_id"]
    new_supplier_address = receipt_data["new_supplier_address"]

    conn = db(); cur = conn.cursor()
    if center_id <= 0:
        row = cur.execute("SELECT id FROM centers ORDER BY id LIMIT 1").fetchone()
        if row:
            center_id = int(row["id"])
    if center_id <= 0:
        conn.close()
        return RedirectResponse(url="/?page=albaranes&err=1", status_code=303)
    try:
        warehouse_id = _resolve_receipt_warehouse(cur, center_id, warehouse_id)
    except Exception:
        conn.close()
        return RedirectResponse(url=f"/?page=albaranes&center_id={center_id}&err=1", status_code=303)
    conn.close()

    upload_blobs = []
    for f in _collect_uploads_from_form(form, "files", "files_camera", "files_library"):
        if not f or not getattr(f, "filename", None):
            continue
        content = await f.read()
        if not content:
            continue
        safe, original_content = _normalize_receipt_upload_to_jpg(f.filename, content)
        work_safe, work_content = _build_receipt_ocr_work_jpg(f.filename, content)
        upload_blobs.append((safe, original_content, work_safe, work_content))

    def _write_receipt(conn2, cur2):
        sid = int(supplier_id) if supplier_id else 0
        local_note = note
        if new_supplier_name:
            hit = cur2.execute("SELECT id FROM suppliers WHERE lower(name)=lower(?)",
                               (new_supplier_name,)).fetchone()
            if hit:
                sid = int(hit["id"])
            else:
                sqlite_sql = "INSERT INTO suppliers(name,phone,email,tax_id,address,is_active) VALUES(?,?,?,?,?,1)"
                pg_sql = sqlite_sql.replace('?', '%s')
                sid = safe_insert_returning(
                    cur2,
                    sqlite_sql,
                    (new_supplier_name, new_supplier_phone or None, new_supplier_email or None, new_supplier_tax_id or None, new_supplier_address or None),
                    pg_sql=pg_sql,
                ) or 0
        if sid <= 0:
            sid = _ensure_pending_supplier(cur2)
            local_note = (local_note + (" | " if local_note else "") + "Proveedor pendiente de revisar por OCR").strip()
            sqlite_sql = """INSERT INTO receipts(center_id,warehouse_id,supplier_id,status,doc_number,doc_date,note,created_at)
                    VALUES(?,?,?,?,?,?,?,?)"""
            pg_sql = sqlite_sql.replace('?', '%s')
            rid = safe_insert_returning(
                cur2,
                sqlite_sql,
                (int(center_id), int(warehouse_id), int(sid), "PENDING", doc_number or None, doc_date or None, local_note, now),
                pg_sql=pg_sql,
            ) or 0
        if upload_blobs:
            target_dir = UPLOADS_DIR / "receipts" / str(rid)
            target_dir.mkdir(parents=True, exist_ok=True)
            nowp = datetime.utcnow().isoformat()
            for safe, content, work_safe, work_content in upload_blobs:
                stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
                fname = f"{stamp}_{safe}"
                out_path = target_dir / fname
                out_path.write_bytes(content)
                if work_content:
                    try:
                        (target_dir / f"{stamp}_{work_safe}").write_bytes(work_content)
                    except Exception:
                        pass
                rel = f"receipts/{rid}/{fname}"
                cur2.execute("INSERT INTO receipt_photos(receipt_id,file_path,created_at) VALUES(?,?,?)",
                             (int(rid), rel, nowp))
        return rid

    try:
        rid = _retry_db_write(_write_receipt, attempts=8, delay=0.4)
    except sqlite3.OperationalError as exc:
        if _is_db_locked_error(exc):
            return RedirectResponse(url=f"/?page=albaranes&center_id={center_id}&err=db_locked", status_code=303)
        raise

    try:
        conn_chk = db(); cur_chk = conn_chk.cursor()
        photo_row = cur_chk.execute("SELECT COUNT(*) c FROM receipt_photos WHERE receipt_id=?", (int(rid),)).fetchone()
        conn_chk.close()
        has_saved_photos = bool(photo_row and int(photo_row["c"] or 0) > 0)
    except Exception:
        has_saved_photos = bool(upload_blobs)

    ts = _cache_bust_token()
    return RedirectResponse(
        url=f"/?page=albaranes&center_id={center_id}&aid={rid}&created=1&ts={ts}#ocrSection", status_code=303)


# ==============================================================================
# FOTOS
# ==============================================================================

@router.post("/receipt/{receipt_id}/upload_photos")
async def receipt_upload_photos(receipt_id: int, request: Request):
    conn = db(); cur = conn.cursor()
    r = cur.execute("SELECT id,center_id FROM receipts WHERE id=?", (int(receipt_id),)).fetchone()
    if not r:
        conn.close()
        return RedirectResponse(url=f"/?page=albaranes&aid={receipt_id}&upmsg=missing&ts={_cache_bust_token()}#ocrSection",
                                status_code=303)
    center_id = int(r["center_id"] or 0)
    form = await request.form()
    auto_ocr = str(form.get("auto_ocr") or "1").strip() in {"1", "true", "on", "yes"}
    files = _collect_uploads_from_form(form, "files", "files_camera", "files_library", "photo", "photos")
    if not files:
        conn.close()
        return RedirectResponse(
            url=f"/?page=albaranes&center_id={center_id}&aid={receipt_id}&upmsg=empty&ts={_cache_bust_token()}#ocrSection",
            status_code=303)
    target_dir = UPLOADS_DIR / "receipts" / str(receipt_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.utcnow().isoformat()
    saved = 0
    for f in files:
        if not f or not getattr(f, "filename", None):
            continue
        stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        content = await f.read()
        if not content:
            continue
        safe, content = _normalize_receipt_upload_to_jpg(f.filename, content)
        work_safe, work_content = _build_receipt_ocr_work_jpg(f.filename, content)
        fname = f"{stamp}_{safe}"
        out_path = target_dir / fname
        out_path.write_bytes(content)
        if work_content:
            try:
                (target_dir / f"{stamp}_{work_safe}").write_bytes(work_content)
            except Exception:
                pass
        rel = f"receipts/{receipt_id}/{fname}"
        cur.execute("INSERT INTO receipt_photos(receipt_id,file_path,created_at) VALUES(?,?,?)",
                    (int(receipt_id), rel, now))
        saved += 1
    conn.commit(); conn.close()
    if saved > 0 and auto_ocr:
        return _process_receipt_ocr_redirect(int(receipt_id))
    if saved > 0:
        return RedirectResponse(
            url=f"/?page=albaranes&center_id={center_id}&aid={receipt_id}&upmsg=saved{saved}#ocrSection",
            status_code=303)
    return RedirectResponse(
        url=f"/?page=albaranes&center_id={center_id}&aid={receipt_id}&upmsg=empty&ts={_cache_bust_token()}#ocrSection",
        status_code=303)


@router.post("/receipt/{receipt_id}/delete_photo/{photo_id}")
def receipt_delete_photo(receipt_id: int, photo_id: int):
    conn = db(); cur = conn.cursor()
    rh = cur.execute("SELECT status FROM receipts WHERE id=?", (int(receipt_id),)).fetchone()
    if not rh:
        conn.close()
        return RedirectResponse(url=receipt_page_url(aid=receipt_id, err=1), status_code=303)
    ph = cur.execute("SELECT file_path FROM receipt_photos WHERE id=? AND receipt_id=?",
                     (int(photo_id), int(receipt_id))).fetchone()
    if not ph:
        conn.close()
        return RedirectResponse(url=f"/?page=albaranes&aid={receipt_id}", status_code=303)
    cur.execute("DELETE FROM receipt_photos WHERE id=? AND receipt_id=?", (int(photo_id), int(receipt_id)))
    conn.commit(); conn.close()
    try:
        fpath = UPLOADS_DIR / ph["file_path"]
        if fpath.exists(): fpath.unlink()
        try:
            ocrp = fpath.with_name(fpath.stem + ".ocr.jpg")
            if ocrp.exists(): ocrp.unlink()
        except Exception:
            pass
    except Exception:
        pass
    return RedirectResponse(url=f"/?page=albaranes&aid={receipt_id}", status_code=303)


@router.post("/receipts/cleanup_photos_form")
def receipts_cleanup_photos_form(center_id: int = Form(0)):
    conn = db(); cur = conn.cursor()
    try:
        cleanup_receipt_photos(cur, int(center_id) if int(center_id or 0) > 0 else None)
        conn.commit()
    except Exception:
        pass
    conn.close()
    return RedirectResponse(url=f"/?page=albaranes&center_id={int(center_id or 0)}&ok=1", status_code=303)


@router.post("/receipts/clear_pending_form")
def receipts_clear_pending_form(center_id: int = Form(0)):
    conn = db(); cur = conn.cursor()
    rows = cur.execute("SELECT id FROM receipts WHERE status='PENDING' AND (?=0 OR center_id=?) ORDER BY id",
                       (int(center_id or 0), int(center_id or 0))).fetchall()
    ids = [int(r["id"]) for r in rows]
    for rid in ids:
        try:
            ph_rows = cur.execute("SELECT file_path FROM receipt_photos WHERE receipt_id=?", (rid,)).fetchall()
            for ph in ph_rows:
                try:
                    fp = UPLOADS_DIR / ph["file_path"]
                    if fp.exists(): fp.unlink()
                    try:
                        ocrp = fp.with_name(fp.stem + ".ocr.jpg")
                        if ocrp.exists(): ocrp.unlink()
                    except Exception:
                        pass
                except Exception:
                    pass
            cur.execute("DELETE FROM receipt_ocr_lines WHERE ocr_run_id IN (SELECT id FROM receipt_ocr_runs WHERE receipt_id=?)", (rid,))
            cur.execute("DELETE FROM receipt_ocr_runs WHERE receipt_id=?", (rid,))
            cur.execute("DELETE FROM receipt_lines WHERE receipt_id=?", (rid,))
            cur.execute("DELETE FROM receipt_photos WHERE receipt_id=?", (rid,))
            cur.execute("DELETE FROM receipts WHERE id=? AND status='PENDING'", (rid,))
        except Exception:
            pass
    conn.commit(); conn.close()
    return RedirectResponse(url=f"/?page=albaranes&center_id={int(center_id or 0)}&cleared_pending={len(ids)}",
                            status_code=303)


# ==============================================================================
# LÍNEAS DE ALBARÁN
# ==============================================================================

@router.post("/receipt/{receipt_id}/add_line_form")
def receipt_add_line_form(
    receipt_id: int,
    item_id: str = Form(""),
    item_query: str = Form(""),
    qty_value: str = Form(""),
    qty_unit: str = Form(""),
    price_unit: str = Form(""),
):
    conn = db(); cur = conn.cursor()
    rh = cur.execute("SELECT center_id,warehouse_id,supplier_id,status FROM receipts WHERE id=?",
                     (int(receipt_id),)).fetchone()
    if not rh or rh["status"] != "PENDING":
        conn.close()
        return RedirectResponse(url=receipt_page_url(aid=receipt_id, err=1), status_code=303)
    resolved_item_id = _resolve_item_id(cur, item_id, item_query)
    if not resolved_item_id:
        conn.close()
        return RedirectResponse(url=receipt_page_url(aid=receipt_id, err=1), status_code=303)
    it = cur.execute("SELECT unit FROM items WHERE id=?", (int(resolved_item_id),)).fetchone()
    if not it:
        conn.close()
        return RedirectResponse(url=receipt_page_url(aid=receipt_id, err=1), status_code=303)
    base_unit = (it["unit"] or "ud").strip() or "ud"
    iu = (qty_unit or base_unit).strip().lower() or base_unit
    # Directriz System MAC: litros/ml entran como compra de líquidos, pero se calculan internamente por peso.
    # Se aceptan contra artículos base g/kg. Se rechazan contra ud/manojo para evitar errores operativos.
    if iu in {"l", "lt", "lts", "litro", "litros", "ml"} and base_unit.lower() not in {"g", "kg"}:
        conn.close()
        return RedirectResponse(url=receipt_page_url(aid=receipt_id, err=1), status_code=303)
    qty_input = _parse_float(qty_value, 0.0)
    if qty_input <= 0:
        conn.close()
        return RedirectResponse(url=receipt_page_url(aid=receipt_id, err=1), status_code=303)
    supplier_id = int(rh["supplier_id"] or 0)
    factor = _supplier_factor_for_item(cur, int(rh["center_id"]), supplier_id, int(resolved_item_id), iu, base_unit)
    qty_base = float(qty_input) * float(factor)
    if qty_base <= 0:
        conn.close()
        return RedirectResponse(url=receipt_page_url(aid=receipt_id, err=1), status_code=303)
    pu = _parse_float(price_unit, 0.0)
    line_total = pu * qty_input if pu > 0 else None
    cur.execute(
        "INSERT INTO receipt_lines(receipt_id,item_id,qty_input,input_unit,factor,qty_base,price_unit,line_total) VALUES(?,?,?,?,?,?,?,?)",
        (int(receipt_id), int(resolved_item_id), float(qty_input), iu, float(factor), float(qty_base),
         (pu if pu > 0 else None), line_total))
    conn.commit(); conn.close()
    return RedirectResponse(url=f"/?page=albaranes&aid={receipt_id}&ok=1", status_code=303)


@router.post("/receipt/{receipt_id}/delete_line/{line_id}")
def receipt_delete_line(receipt_id: int, line_id: int):
    conn = db(); cur = conn.cursor()
    rh = cur.execute("SELECT status,center_id,warehouse_id FROM receipts WHERE id=?", (int(receipt_id),)).fetchone()
    if not rh or rh["status"] not in ("PENDING", "CONFIRMED", "ARCHIVED"):
        conn.close()
        return RedirectResponse(url=receipt_page_url(aid=receipt_id, err=1), status_code=303)
    ln = cur.execute(
        "SELECT id,item_id,qty_input,input_unit,qty_base,COALESCE(price_unit,0) price_unit FROM receipt_lines WHERE id=? AND receipt_id=?",
        (int(line_id), int(receipt_id))).fetchone()
    if not ln:
        conn.close()
        return RedirectResponse(url=receipt_page_url(aid=receipt_id, err=1), status_code=303)
    if rh["status"] in ("CONFIRMED", "ARCHIVED"):
        note = f"Albarán #{receipt_id}"
        mv = cur.execute(
            "SELECT id FROM movements WHERE center_id=? AND warehouse_id=? AND item_id=? AND note=? AND abs(qty-?)<0.000001 ORDER BY id DESC LIMIT 1",
            (int(rh["center_id"]), int(rh["warehouse_id"]), int(ln["item_id"] or 0),
             note, float(ln["qty_base"] or 0))).fetchone()
        if mv:
            cur.execute("DELETE FROM movements WHERE id=?", (int(mv["id"]),))
    cur.execute("DELETE FROM receipt_lines WHERE id=? AND receipt_id=?", (int(line_id), int(receipt_id)))
    if rh["status"] == "PENDING":
        run = cur.execute("SELECT id FROM receipt_ocr_runs WHERE receipt_id=? ORDER BY id DESC LIMIT 1",
                          (int(receipt_id),)).fetchone()
        if run:
            cur.execute(
                "DELETE FROM receipt_ocr_lines WHERE ocr_run_id=? AND COALESCE(matched_item_id,0)=? AND abs(COALESCE(qty_raw,0)-?)<0.000001 AND lower(COALESCE(unit_raw,''))=lower(?) AND abs(COALESCE(price_raw,0)-?)<0.000001",
                (int(run["id"]), int(ln["item_id"] or 0), float(ln["qty_input"] or 0),
                 (ln["input_unit"] or ""), float(ln["price_unit"] or 0)))
            _refresh_ocr_summary(cur, int(receipt_id))
    conn.commit(); conn.close()
    return RedirectResponse(url=f"/?page=albaranes&center_id={int(rh['center_id'])}&aid={receipt_id}&del_ok=1",
                            status_code=303)


# ==============================================================================
# OCR ROUTES
# ==============================================================================

@router.get("/api/receipt/{receipt_id}/ocr_status")
def api_receipt_ocr_status(receipt_id: int):
    conn = db(); conn.row_factory = __import__("sqlite3").Row; cur = conn.cursor()
    try:
        row = cur.execute(
            "SELECT status,summary,supplier_name,doc_number,date_text,line_count FROM receipt_ocr_runs WHERE receipt_id=? ORDER BY id DESC LIMIT 1",
            (int(receipt_id),)).fetchone()
        if not row:
            return JSONResponse({"ok": True, "status": "EMPTY", "line_count": 0})
        data = {k: row[k] for k in row.keys()}
        data["ok"] = True
        data["status"] = str(data.get("status") or "").upper()
        data["line_count"] = int(data.get("line_count") or 0)
        return JSONResponse(data)
    finally:
        conn.close()


@router.get("/receipt/{receipt_id}/process_ocr")
def receipt_process_ocr_get(receipt_id: int):
    return _process_receipt_ocr_redirect(receipt_id)


@router.post("/receipt/{receipt_id}/process_ocr_form")
def receipt_process_ocr_form(receipt_id: int):
    return _process_receipt_ocr_redirect(receipt_id)


@router.post("/receipt/{receipt_id}/clear_ocr_form")
def receipt_clear_ocr_form(receipt_id: int):
    conn = db(); cur = conn.cursor()
    rh = cur.execute("SELECT id,center_id FROM receipts WHERE id=?", (int(receipt_id),)).fetchone()
    conn.close()
    if not rh:
        return RedirectResponse(url=receipt_page_url(aid=receipt_id, err=1), status_code=303)
    def _writer(conn2, cur2):
        cur2.execute("DELETE FROM receipt_ocr_lines WHERE ocr_run_id IN (SELECT id FROM receipt_ocr_runs WHERE receipt_id=?)", (int(receipt_id),))
        cur2.execute("DELETE FROM receipt_ocr_runs WHERE receipt_id=?", (int(receipt_id),))
    try:
        _retry_db_write(_writer, attempts=10, delay=0.45)
        return RedirectResponse(url=f"/?page=albaranes&center_id={int(rh['center_id'])}&aid={receipt_id}",
                                status_code=303)
    except sqlite3.OperationalError as exc:
        return RedirectResponse(
            url=f"/?page=albaranes&center_id={int(rh['center_id'])}&aid={receipt_id}&err=db_lock#ocrSection",
            status_code=303)


@router.post("/receipt/{receipt_id}/ocr_line/{ocr_line_id}/delete")
def receipt_ocr_line_delete(receipt_id: int, ocr_line_id: int):
    conn = db(); cur = conn.cursor()
    rh = cur.execute("SELECT id,center_id,status FROM receipts WHERE id=?", (int(receipt_id),)).fetchone()
    run = cur.execute("SELECT id FROM receipt_ocr_runs WHERE receipt_id=? ORDER BY id DESC LIMIT 1",
                      (int(receipt_id),)).fetchone()
    conn.close()
    if not rh:
        return RedirectResponse(url=receipt_page_url(aid=receipt_id, err=1), status_code=303)
    if not run:
        return RedirectResponse(url=f"/?page=albaranes&center_id={int(rh['center_id'])}&aid={receipt_id}",
                                status_code=303)
    def _writer(conn2, cur2):
        cur2.execute("DELETE FROM receipt_ocr_lines WHERE id=? AND ocr_run_id=?", (int(ocr_line_id), int(run["id"])))
        _refresh_ocr_summary(cur2, int(receipt_id))
    try:
        _retry_db_write(_writer, attempts=10, delay=0.45)
        return RedirectResponse(
            url=f"/?page=albaranes&center_id={int(rh['center_id'])}&aid={receipt_id}&ocr_ok=1&ts={_cache_bust_token()}#ocrSection",
            status_code=303)
    except sqlite3.OperationalError:
        return RedirectResponse(
            url=f"/?page=albaranes&center_id={int(rh['center_id'])}&aid={receipt_id}&err=db_lock#ocrSection",
            status_code=303)


@router.post("/receipt/{receipt_id}/ocr_line/{ocr_line_id}/accept")
def receipt_ocr_line_accept(
    receipt_id: int, ocr_line_id: int,
    item_query: str = Form(""), qty_raw: str = Form(""), price_raw: str = Form(""),
    unit_raw: str = Form(""), create_if_missing: str = Form("0"), new_unit_family: str = Form("unidad"),
):
    conn = db(); cur = conn.cursor()
    rh = cur.execute("SELECT * FROM receipts WHERE id=?", (int(receipt_id),)).fetchone()
    center_id = int(rh["center_id"]) if rh else 0
    conn.close()
    if not rh or rh["status"] != "PENDING":
        return RedirectResponse(url=receipt_page_url(aid=receipt_id, err=1), status_code=303)

    requested_name = re.sub(r"\s+", " ", (item_query or "").strip())
    requested_qty = (qty_raw or "").strip()
    requested_price = (price_raw or "").strip()
    requested_unit = (unit_raw or "").strip().lower()
    requested_family = (new_unit_family or "").strip().lower()
    requested_create = str(create_if_missing or "0") == "1"

    def _writer(conn2, cur2):
        rh2 = cur2.execute("SELECT * FROM receipts WHERE id=?", (int(receipt_id),)).fetchone()
        if not rh2 or rh2["status"] != "PENDING":
            raise sqlite3.OperationalError("receipt_not_pending")
        run = cur2.execute("SELECT id FROM receipt_ocr_runs WHERE receipt_id=? ORDER BY id DESC LIMIT 1",
                           (int(receipt_id),)).fetchone()
        line = cur2.execute("SELECT * FROM receipt_ocr_lines WHERE id=? AND ocr_run_id=?",
                            (int(ocr_line_id), int(run["id"]) if run else 0)).fetchone()
        if not line:
            raise sqlite3.OperationalError("ocr_line_missing")

        raw_name = re.sub(r"\s+", " ", (requested_name or line["item_name_raw"] or line["source_text"] or "").strip())
        unit = (requested_unit or line["unit_raw"] or "").strip().lower()
        inferred_family = requested_family
        if not inferred_family:
            if unit in ("kg", "g", "gr"):
                inferred_family = "peso"
            elif unit in ("l", "lt", "ml"):
                inferred_family = "peso"
            else:
                inferred_family = "unidad"
        base_unit = "ud"
        if inferred_family == "peso":
            base_unit = "g"
        elif inferred_family == "volumen":
            base_unit = "g"

        resolved_item_id = None
        matched_name = None
        if raw_name:
            exact = cur2.execute(
                "SELECT id,name,unit FROM items WHERE lower(name)=lower(?) AND unit=? ORDER BY id LIMIT 1",
                (raw_name, base_unit)).fetchone()
            if exact:
                resolved_item_id = int(exact["id"]); matched_name = exact["name"]; base_unit = exact["unit"] or base_unit
        if not resolved_item_id:
            candidate_id = _resolve_item_id_strict(cur2, line["matched_item_id"],
                                                   raw_name or line["matched_item_name"] or line["item_name_raw"] or "")
            if candidate_id:
                rr = cur2.execute("SELECT name,unit FROM items WHERE id=?", (int(candidate_id),)).fetchone()
                candidate_name = rr["name"] if rr else raw_name
                score = SequenceMatcher(None, _norm_text(candidate_name), _norm_text(raw_name or candidate_name)).ratio() if (raw_name or candidate_name) else 0.0
                if score >= 0.78:
                    resolved_item_id = int(candidate_id); matched_name = candidate_name
                    base_unit = rr["unit"] if rr and rr["unit"] else base_unit
        if not resolved_item_id and requested_create and raw_name:
            exact2 = cur2.execute("SELECT id,name,unit FROM items WHERE lower(name)=lower(?) AND unit=? ORDER BY id LIMIT 1",
                                  (raw_name, base_unit)).fetchone()
            if exact2:
                resolved_item_id = int(exact2["id"]); matched_name = exact2["name"]; base_unit = exact2["unit"] or base_unit
            else:
                sqlite_sql = "INSERT INTO items(name,unit,min_qty,max_qty,current_price) VALUES(?,?,?,?,?)"
                pg_sql = sqlite_sql.replace('?', '%s')
                resolved_item_id = safe_insert_returning(
                    cur2,
                    sqlite_sql,
                    (raw_name, base_unit, 0.0, 0.0, 0.0),
                    pg_sql=pg_sql,
                ) or 0
                matched_name = raw_name
        if not resolved_item_id:
            raise sqlite3.OperationalError("resolve_item_failed")

        qty_input = _parse_float((requested_qty or line["qty_raw"]), 0.0)
        if qty_input <= 0: qty_input = 1.0
        input_unit = ((requested_unit or line["unit_raw"] or base_unit or "ud").strip().lower() or base_unit)
        if input_unit in {"l", "lt", "lts", "litro", "litros", "ml"} and str(base_unit or '').lower() not in {"g", "kg"}:
            # No validar litros contra artículos por unidad/manojo; queda pendiente de revisión manual.
            cur.execute("UPDATE receipt_ocr_lines SET review_status='PENDING' WHERE id=?", (int(line_id),))
            conn.commit(); conn.close()
            return RedirectResponse(url=f"/?page=albaranes&aid={receipt_id}&err=1#ocr", status_code=303)
        factor = _factor_for_units(input_unit, base_unit)
        qty_base = float(qty_input) * float(factor)
        if qty_base <= 0: qty_base = float(qty_input); factor = 1.0
        pu = _parse_float((requested_price or line["price_raw"]), 0.0)
        line_total = pu * qty_input if pu > 0 else None

        exists = cur2.execute(
            "SELECT id FROM receipt_lines WHERE receipt_id=? AND item_id=? AND abs(qty_input-?)<0.000001 AND input_unit=? AND abs(COALESCE(price_unit,0)-?)<0.000001 ORDER BY id LIMIT 1",
            (int(receipt_id), int(resolved_item_id), float(qty_input), input_unit, float(pu))).fetchone()
        if not exists:
            cur2.execute(
                "INSERT INTO receipt_lines(receipt_id,item_id,qty_input,input_unit,factor,qty_base,price_unit,line_total) VALUES(?,?,?,?,?,?,?,?)",
                (int(receipt_id), int(resolved_item_id), float(qty_input), input_unit, float(factor),
                 float(qty_base), (pu if pu > 0 else None), line_total))
        cur2.execute(
            "UPDATE receipt_ocr_lines SET matched_item_id=?,matched_item_name=?,item_name_raw=?,qty_raw=?,unit_raw=?,price_raw=?,review_status='ACCEPTED' WHERE id=?",
            (int(resolved_item_id), matched_name, raw_name, fmt_num(qty_input), input_unit,
             (fmt_num(pu, 2) if pu > 0 else ""), int(ocr_line_id)))
        _refresh_ocr_summary(cur2, int(receipt_id))

    try:
        _retry_db_write(_writer, attempts=10, delay=0.45)
        return RedirectResponse(
            url=f"/?page=albaranes&center_id={center_id}&aid={receipt_id}&ocr_line_ok=1&ocr_line_id={int(ocr_line_id)}&ts={_cache_bust_token()}#ocrLineRow{int(ocr_line_id)}",
            status_code=303)
    except sqlite3.OperationalError as exc:
        msg = str(exc).lower()
        if "resolve_item_failed" in msg:
            return RedirectResponse(
                url=f"/?page=albaranes&center_id={center_id}&aid={receipt_id}&ocr_line_err=resolve&ocr_line_id={int(ocr_line_id)}&ts={_cache_bust_token()}#ocrLineRow{int(ocr_line_id)}",
                status_code=303)
        if "locked" in msg:
            return RedirectResponse(
                url=f"/?page=albaranes&center_id={center_id}&aid={receipt_id}&ocr_line_err=locked&ocr_line_id={int(ocr_line_id)}&ts={_cache_bust_token()}#ocrLineRow{int(ocr_line_id)}",
                status_code=303)
        return RedirectResponse(
            url=f"/?page=albaranes&center_id={center_id}&aid={receipt_id}&ocr_line_err=1&ocr_line_id={int(ocr_line_id)}&ts={_cache_bust_token()}#ocrLineRow{int(ocr_line_id)}",
            status_code=303)


@router.post("/receipt/{receipt_id}/ocr_supplier_apply")
def receipt_ocr_supplier_apply(
    receipt_id: int,
    supplier_query: str = Form(""),
    create_if_missing: str = Form("0"),
):
    conn = db(); cur = conn.cursor()
    rh = cur.execute("SELECT * FROM receipts WHERE id=?", (int(receipt_id),)).fetchone()
    if not rh or rh["status"] != "PENDING":
        conn.close()
        return RedirectResponse(
            url=f"/?page=albaranes&aid={receipt_id}&ocr_supplier_err=1&ts={_cache_bust_token()}#ocrSection",
            status_code=303)
    supplier_name = re.sub(r"\s+", " ", (supplier_query or "").strip())
    supplier_id = None; resolved_name = None
    if supplier_name:
        supplier_id, resolved_name = _resolve_supplier_id_by_name(cur, supplier_name)
        if not supplier_id and str(create_if_missing or "0") == "1":
            supplier_id = _insert_supplier_compatible(cur, supplier_name[:120], is_active=1)
            resolved_name = supplier_name[:120]
    if not supplier_id:
        conn.close()
        return RedirectResponse(
            url=f"/?page=albaranes&aid={receipt_id}&ocr_supplier_err=1&ts={_cache_bust_token()}#ocrSection",
            status_code=303)
    run = cur.execute(
        "SELECT id,doc_number_raw,doc_date_raw,supplier_phone_raw,supplier_email_raw,supplier_tax_id_raw,supplier_address_raw FROM receipt_ocr_runs WHERE receipt_id=? ORDER BY id DESC LIMIT 1",
        (int(receipt_id),)).fetchone()
    doc_number = rh["doc_number"] or (run["doc_number_raw"] if run else None) or None
    doc_date = rh["doc_date"] or (run["doc_date_raw"] if run else None) or None
    cur.execute("UPDATE receipts SET supplier_id=?,doc_number=COALESCE(doc_number,?),doc_date=COALESCE(doc_date,?) WHERE id=?",
                (int(supplier_id), doc_number, doc_date, int(receipt_id)))
    if run:
        cur.execute("UPDATE receipt_ocr_runs SET supplier_raw=? WHERE id=?",
                    (resolved_name or supplier_name, int(run["id"])))
        try:
            for col in ["supplier_phone_raw", "supplier_email_raw", "supplier_tax_id_raw", "supplier_address_raw"]:
                val = (run[col] or "").strip() if col in run.keys() else ""
                if val:
                    db_col = col.replace("_raw", "").replace("supplier_", "")
                    if db_col in ("phone", "email", "tax_id", "address"):
                        cur.execute(f"UPDATE suppliers SET {db_col}=COALESCE(NULLIF({db_col},''),NULLIF(?,'')) WHERE id=?",
                                    (val, int(supplier_id)))
        except Exception:
            pass
    _cleanup_pending_supplier(cur)
    conn.commit(); conn.close()
    return RedirectResponse(
        url=f"/?page=albaranes&center_id={int(rh['center_id'])}&aid={receipt_id}&ocr_ok=1&head_ok=1&ts={_cache_bust_token()}#ocrSection",
        status_code=303)


# ==============================================================================
# VALIDAR / ARCHIVAR / CANCELAR
# ==============================================================================

@router.post("/receipt/{receipt_id}/validate_form")
def receipt_validate_form(receipt_id: int):
    conn = db(); cur = conn.cursor()
    rh = cur.execute("SELECT * FROM receipts WHERE id=?", (int(receipt_id),)).fetchone()
    if not rh or rh["status"] != "PENDING":
        conn.close()
        return RedirectResponse(url=receipt_page_url(aid=receipt_id, err=1), status_code=303)
    lines = cur.execute(
        "SELECT item_id,qty_base,qty_input,input_unit,factor,price_unit,line_total FROM receipt_lines WHERE receipt_id=?",
        (int(receipt_id),)).fetchall()
    if not lines:
        conn.close()
        return RedirectResponse(url=receipt_page_url(aid=receipt_id, err=1), status_code=303)
    now = datetime.utcnow().isoformat()
    ocr_run = cur.execute("SELECT * FROM receipt_ocr_runs WHERE receipt_id=? ORDER BY id DESC LIMIT 1",
                          (int(receipt_id),)).fetchone()
    supplier_id = int(rh["supplier_id"] or 0)
    pending_supplier = _ensure_pending_supplier(cur)
    if supplier_id == pending_supplier and ocr_run and (ocr_run["supplier_raw"] or "").strip():
        # No inventar proveedor al validar. Solo reutilizar un proveedor ya existente
        # si el nombre OCR encaja exactamente; en otro caso, mantener pendiente.
        supplier_name = re.sub(r"\s+", " ", (ocr_run["supplier_raw"] or "").strip())[:120]
        ex = cur.execute("SELECT id FROM suppliers WHERE lower(name)=lower(?) ORDER BY id LIMIT 1",
                         (supplier_name,)).fetchone()
        if ex:
            supplier_id = int(ex["id"])
            cur.execute("UPDATE receipts SET supplier_id=? WHERE id=?", (supplier_id, int(receipt_id)))
    doc_number = rh["doc_number"] or (ocr_run["doc_number_raw"] if ocr_run else None)
    doc_date = rh["doc_date"] or (ocr_run["doc_date_raw"] if ocr_run else None)
    for ln in lines:
        item = cur.execute("SELECT unit FROM items WHERE id=?", (int(ln["item_id"]),)).fetchone()
        base_unit = (item["unit"] if item else "ud") or "ud"
        cur.execute(
            "INSERT INTO movements(movement_type,item_id,center_id,warehouse_id,qty,unit,note,created_at) VALUES('ENTRADA',?,?,?,?,?,?,?)",
            (int(ln["item_id"]), int(rh["center_id"]), int(rh["warehouse_id"]),
             float(ln["qty_base"]), base_unit, f"Albarán #{receipt_id}", now))
        pu = float(ln["price_unit"] or 0.0)
        factor = float(ln["factor"] or 0.0)
        iu = (ln["input_unit"] or base_unit).strip() or base_unit
        if pu > 0 and factor > 0:
            prev_pref = cur.execute(
                "SELECT is_preferred FROM supplier_item_prices WHERE supplier_id=? AND item_id=? AND (center_id IS NULL OR center_id=?) ORDER BY is_preferred DESC, updated_at DESC LIMIT 1",
                (int(supplier_id), int(ln["item_id"]), int(rh["center_id"]))).fetchone()
            is_pref = int(prev_pref["is_preferred"]) if prev_pref else 0
            if int(supplier_id or 0) > 0 and int(supplier_id) != int(pending_supplier):
                cur.execute(
                    """INSERT INTO supplier_item_prices(supplier_id,item_id,center_id,price_per_purchase,purchase_unit,purchase_to_base_factor,is_preferred,updated_at)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (int(supplier_id), int(ln["item_id"]), int(rh["center_id"]),
                     float(pu), iu, float(factor), is_pref, now))
            cur.execute("UPDATE items SET current_price=? WHERE id=?",
                        (float(pu) / float(factor), int(ln["item_id"])))
    cur.execute("UPDATE receipts SET status='CONFIRMED',validated_at=?,doc_number=COALESCE(doc_number,?),doc_date=COALESCE(doc_date,?) WHERE id=?",
                (now, doc_number, doc_date, int(receipt_id)))
    conn.commit(); conn.close()
    return RedirectResponse(url=f"/?page=albaranes&center_id={int(rh['center_id'])}&aid={receipt_id}&validated_ok=1",
                            status_code=303)


@router.post("/receipt/{receipt_id}/cancel_form")
def receipt_cancel_form(receipt_id: int):
    conn = db(); cur = conn.cursor()
    rh = cur.execute("SELECT center_id,status FROM receipts WHERE id=?", (int(receipt_id),)).fetchone()
    if not rh or rh["status"] != "PENDING":
        conn.close()
        return RedirectResponse(url=receipt_page_url(aid=receipt_id, err=1), status_code=303)
    cur.execute("UPDATE receipts SET status='CANCELED' WHERE id=?", (int(receipt_id),))
    conn.commit(); conn.close()
    return RedirectResponse(url=f"/?page=albaranes&center_id={int(rh['center_id'])}", status_code=303)


@router.post("/receipt/{receipt_id}/archive_form")
def receipt_archive_form(receipt_id: int):
    conn = db(); cur = conn.cursor()
    rh = cur.execute("SELECT status,center_id FROM receipts WHERE id=?", (receipt_id,)).fetchone()
    if not rh or rh["status"] != "CONFIRMED":
        conn.close()
        return RedirectResponse(url=f"/?page=albaranes&aid={receipt_id}&err=1#receiptPanel", status_code=303)
    cur.execute("UPDATE receipts SET status='ARCHIVED' WHERE id=?", (receipt_id,))
    conn.commit(); conn.close()
    return RedirectResponse(url=f"/?page=albaranes&center_id={int(rh['center_id'])}&ok=1", status_code=303)


@router.post("/receipt/{receipt_id}/restore_form")
def receipt_restore_form(receipt_id: int):
    conn = db(); cur = conn.cursor()
    rh = cur.execute("SELECT status,center_id FROM receipts WHERE id=?", (receipt_id,)).fetchone()
    if not rh or rh["status"] != "ARCHIVED":
        conn.close()
        return RedirectResponse(url=f"/?page=albaranes&aid={receipt_id}&err=1#receiptPanel", status_code=303)
    cur.execute("UPDATE receipts SET status='CONFIRMED' WHERE id=?", (receipt_id,))
    conn.commit(); conn.close()
    return RedirectResponse(
        url=f"/?page=albaranes&center_id={int(rh['center_id'])}&show_archived_receipts=1&aid={receipt_id}&ok=1#receiptPanel",
        status_code=303)


@router.post("/receipt/{receipt_id}/delete_confirmed_form")
def receipt_delete_confirmed_form(receipt_id: int):
    conn = db(); cur = conn.cursor()
    rh = cur.execute("SELECT * FROM receipts WHERE id=?", (int(receipt_id),)).fetchone()
    if not rh or rh["status"] not in ("CONFIRMED", "ARCHIVED"):
        conn.close()
        return RedirectResponse(url=f"/?page=albaranes&aid={receipt_id}&err=1#receiptPanel", status_code=303)
    note = f"Albarán #{receipt_id}"
    rows = cur.execute("SELECT id,file_path FROM receipt_photos WHERE receipt_id=?", (int(receipt_id),)).fetchall()
    cur.execute("DELETE FROM movements WHERE center_id=? AND warehouse_id=? AND note=?",
                (int(rh["center_id"]), int(rh["warehouse_id"]), note))
    cur.execute("DELETE FROM receipt_lines WHERE receipt_id=?", (int(receipt_id),))
    cur.execute("DELETE FROM receipt_ocr_lines WHERE ocr_run_id IN (SELECT id FROM receipt_ocr_runs WHERE receipt_id=?)", (int(receipt_id),))
    cur.execute("DELETE FROM receipt_ocr_runs WHERE receipt_id=?", (int(receipt_id),))
    cur.execute("DELETE FROM receipt_photos WHERE receipt_id=?", (int(receipt_id),))
    cur.execute("DELETE FROM receipts WHERE id=?", (int(receipt_id),))
    conn.commit(); conn.close()
    for r in rows:
        try:
            fpath = UPLOADS_DIR / r["file_path"]
            if fpath.exists(): fpath.unlink()
        except Exception:
            pass
    return RedirectResponse(url=f"/?page=albaranes&center_id={int(rh['center_id'])}&deleted_ok=1",
                            status_code=303)


@router.post("/receipt/{receipt_id}/reset_test_form")
def receipt_reset_test_form(receipt_id: int):
    conn = db(); cur = conn.cursor()
    rh = cur.execute("SELECT * FROM receipts WHERE id=?", (int(receipt_id),)).fetchone()
    if not rh:
        conn.close()
        return RedirectResponse(url=receipt_page_url(aid=receipt_id, err=1), status_code=303)
    rows = cur.execute("SELECT id,file_path FROM receipt_photos WHERE receipt_id=?", (int(receipt_id),)).fetchall()
    note = f"Albarán #{receipt_id}"
    cur.execute("DELETE FROM movements WHERE center_id=? AND warehouse_id=? AND note=?",
                (int(rh["center_id"]), int(rh["warehouse_id"]), note))
    cur.execute("DELETE FROM receipt_lines WHERE receipt_id=?", (int(receipt_id),))
    cur.execute("DELETE FROM receipt_ocr_lines WHERE ocr_run_id IN (SELECT id FROM receipt_ocr_runs WHERE receipt_id=?)", (int(receipt_id),))
    cur.execute("DELETE FROM receipt_ocr_runs WHERE receipt_id=?", (int(receipt_id),))
    cur.execute("DELETE FROM receipt_photos WHERE receipt_id=?", (int(receipt_id),))
    pending_supplier_id = _ensure_pending_supplier(cur)
    cur.execute("UPDATE receipts SET status='PENDING',validated_at=NULL,supplier_id=?,doc_number=NULL,doc_date=NULL,note=NULL WHERE id=?",
                (int(pending_supplier_id), int(receipt_id)))
    conn.commit(); conn.close()
    for r in rows:
        try:
            fpath = UPLOADS_DIR / r["file_path"]
            if fpath.exists(): fpath.unlink()
        except Exception:
            pass
    return RedirectResponse(url=f"/?page=albaranes&center_id={int(rh['center_id'])}&aid={receipt_id}&reset_ok=1",
                            status_code=303)
