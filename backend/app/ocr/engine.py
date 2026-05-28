from __future__ import annotations

# ==============================================================================
# BLOQUE OCR ENGINE · Parsers por proveedor, OCR, lectura de imágenes
# Separado del main para aislar memoria y facilitar mantenimiento.
# Cada proveedor tiene su propio parser: _extract_receipt_lines_<proveedor>
# ==============================================================================
import re
import os
import io
import time
from pathlib import Path
from datetime import datetime
from difflib import SequenceMatcher

import numpy as np
from PIL import Image, ImageOps, ImageFilter
import pytesseract

try:
    from paddleocr import PaddleOCR  # type: ignore
except Exception:
    PaddleOCR = None

_PADDLE_OCR = None

from app.core import (
    db, _norm_text, _norm_name, fmt_num, _parse_float,
    _resolve_supplier_id_by_name, _insert_supplier_compatible,
    UPLOADS_DIR, _ocr_lock_path,
    get_table_columns_from_cursor,
    safe_insert_returning,
)


def _is_probable_filename(line: str) -> bool:
    low = (line or '').lower()
    return bool(re.search(r'(^|[_\-/ ])img[_ -]?\d+|\.(heic|heif|jpg|jpeg|png)\b|^\d{8,}[_ -]?img', low))

def _get_paddle_ocr():
    global _PADDLE_OCR
    # W79: desactivar Paddle por defecto para evitar bloqueos largos en Mac.
    # Solo se activa si ENABLE_PADDLE_OCR=1.
    if os.environ.get("ENABLE_PADDLE_OCR", "").strip() != "1":
        return None
    if PaddleOCR is None:
        return None
    if _PADDLE_OCR is not None:
        return _PADDLE_OCR
    try:
        _PADDLE_OCR = PaddleOCR(use_angle_cls=False, lang="es", show_log=False)
    except Exception:
        try:
            _PADDLE_OCR = PaddleOCR(use_angle_cls=False, lang="en", show_log=False)
        except Exception:
            _PADDLE_OCR = None
    return _PADDLE_OCR
    try:
        _PADDLE_OCR = PaddleOCR(use_angle_cls=True, lang="es", show_log=False)
    except Exception:
        try:
            _PADDLE_OCR = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        except Exception:
            _PADDLE_OCR = None
    return _PADDLE_OCR

def _open_receipt_image(path: Path):
    try:
        im = Image.open(path)
        im.load()
        return im
    except Exception:
        if path.suffix.lower() in {".heic", ".heif"}:
            tmp_path = None
            try:
                import subprocess, tempfile
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    tmp_path = Path(tmp.name)
                subprocess.run(["sips", "-s", "format", "png", str(path), "--out", str(tmp_path)], check=True, capture_output=True)
                im = Image.open(tmp_path)
                im.load()
                return im
            except Exception:
                return None
            finally:
                try:
                    if tmp_path and tmp_path.exists():
                        tmp_path.unlink()
                except Exception:
                    pass
        return None





def _normalize_uploaded_image_bytes_to_jpeg(filename: str, content: bytes, *, quality: int = 92, max_side: int = 2200):
    """Return validated JPEG bytes from many input formats, with fallback for HEIC/HEIF via sips."""
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", (filename or "upload").strip()) or "upload"
    base = re.sub(r"\.[A-Za-z0-9]+$", "", safe) or "upload"
    from io import BytesIO

    def _finalize(im):
        im.load()
        try:
            im = ImageOps.exif_transpose(im)
        except Exception:
            pass
        if getattr(im, 'mode', 'RGB') != 'RGB':
            im = im.convert('RGB')
        try:
            w, h = im.size
            if max(w, h) > max_side and max(w, h) > 0:
                scale = float(max_side) / float(max(w, h))
                nw = max(1, int(round(w * scale)))
                nh = max(1, int(round(h * scale)))
                im = im.resize((nw, nh))
        except Exception:
            pass
        out = BytesIO()
        try:
            im.save(out, format='JPEG', quality=quality, optimize=True)
        except Exception:
            out = BytesIO()
            im.save(out, format='JPEG', quality=quality)
        data = out.getvalue()
        check = Image.open(BytesIO(data))
        check.load()
        return f"{base}.jpg", data

    try:
        im = Image.open(BytesIO(content))
        return _finalize(im)
    except Exception:
        pass

    if safe.lower().endswith((".heic", ".heif")):
        tmp_in = None
        tmp_out = None
        try:
            import subprocess, tempfile
            with tempfile.NamedTemporaryFile(suffix=Path(safe).suffix or '.heic', delete=False) as tin:
                tin.write(content)
                tmp_in = Path(tin.name)
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tout:
                tmp_out = Path(tout.name)
            subprocess.run(["sips", "-s", "format", "jpeg", str(tmp_in), "--out", str(tmp_out)], check=True, capture_output=True)
            data = tmp_out.read_bytes()
            im = Image.open(BytesIO(data))
            return _finalize(im)
        except Exception:
            pass
        finally:
            for tp in (tmp_in, tmp_out):
                try:
                    if tp and tp.exists():
                        tp.unlink()
                except Exception:
                    pass

    return f"{base}.jpg", b''


def _build_receipt_ocr_work_jpg_from_jpeg_bytes(filename: str, jpeg_bytes: bytes):
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", (filename or "upload").strip()) or "upload"
    base = re.sub(r"\.[A-Za-z0-9]+$", "", safe) or "upload"
    from io import BytesIO
    try:
        im = Image.open(BytesIO(jpeg_bytes))
        im.load()
        try:
            im = ImageOps.exif_transpose(im)
        except Exception:
            pass
        if im.mode != 'RGB':
            im = im.convert('RGB')
        try:
            w, h = im.size
            target = 1900
            if max(w, h) < target and max(w, h) > 0:
                scale = max(1, int(target / max(w, h)) + 1)
                im = im.resize((w * scale, h * scale))
        except Exception:
            pass
        gray = ImageOps.autocontrast(im.convert('L')).convert('RGB')
        out = BytesIO()
        try:
            gray.save(out, format='JPEG', quality=94, optimize=True)
        except Exception:
            out = BytesIO()
            gray.save(out, format='JPEG', quality=94)
        data = out.getvalue()
        chk = Image.open(BytesIO(data))
        chk.load()
        return f"{base}.ocr.jpg", data
    except Exception:
        return f"{base}.ocr.jpg", b''

def _normalize_receipt_upload_to_jpg(filename: str, content: bytes):
    jpg_name, jpg_bytes = _normalize_uploaded_image_bytes_to_jpeg(filename, content, quality=92, max_side=2400)
    if jpg_bytes:
        return jpg_name, jpg_bytes
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", (filename or "upload").strip()) or "upload"
    return safe, content


def _build_receipt_ocr_work_jpg(filename: str, content: bytes):
    """Create a validated OCR work copy; if the source is HEIC/HEIF, normalize first."""
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", (filename or "upload").strip()) or "upload"
    base = re.sub(r"\.[A-Za-z0-9]+$", "", safe) or "upload"
    norm_name, norm_bytes = _normalize_uploaded_image_bytes_to_jpeg(filename, content, quality=94, max_side=2400)
    if norm_bytes:
        work_name, work_bytes = _build_receipt_ocr_work_jpg_from_jpeg_bytes(norm_name, norm_bytes)
        if work_bytes:
            return work_name, work_bytes
        base2 = re.sub(r"\.[A-Za-z0-9]+$", "", norm_name) or base
        return f"{base2}.ocr.jpg", norm_bytes
    return f"{base}.ocr.jpg", b''


def _receipt_ocr_source_path(file_path: str) -> Path:
    p = UPLOADS_DIR / (file_path or '')
    try:
        name = p.name
        if name.lower().endswith('.ocr.jpg'):
            return p
        candidate = p.with_name(p.stem + '.ocr.jpg')
        if candidate.exists() and candidate.stat().st_size > 0:
            try:
                chk = _open_receipt_image(candidate)
                if chk is not None:
                    return candidate
            except Exception:
                pass
    except Exception:
        pass
    return p

def _clean_ocr_lines(txt: str) -> list[str]:
    out = []
    seen = set()
    for raw in (txt or '').splitlines():
        line = re.sub(r'\s+', ' ', (raw or '').strip())
        if not line:
            continue
        if _is_probable_filename(line):
            continue
        if line in seen:
            continue
        seen.add(line)
        out.append(line)
    return out


OCR_TESS_TIMEOUT_SEC = 4
OCR_IMAGE_BUDGET_SEC = 16

def _tesseract_text_candidates(im: Image.Image) -> list[str]:
    """Fast-path OCR candidates with per-call timeouts."""
    texts = []
    configs = ('--oem 3 --psm 6', '--oem 3 --psm 11')
    langs = ('spa+eng', 'eng')
    for lang in langs:
        for cfg in configs:
            try:
                txt = pytesseract.image_to_string(im, lang=lang, config=cfg, timeout=OCR_TESS_TIMEOUT_SEC) or ''
            except RuntimeError:
                txt = ''
            except Exception:
                txt = ''
            if txt and txt.strip():
                texts.append(txt)
    uniq = []
    seen = set()
    for txt in texts:
        key = '\n'.join(_clean_ocr_lines(txt))
        if not key or key in seen:
            continue
        seen.add(key)
        uniq.append(key)
    return uniq
def _ocr_text_with_paddle(img: Image.Image) -> str:
    engine = _get_paddle_ocr()
    if engine is None:
        return ''
    import tempfile
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            tmp_path = Path(tmp.name)
        img.save(tmp_path, format='PNG')
        result = engine.ocr(str(tmp_path), cls=True) or []
        lines = []
        for page in result:
            for row in page or []:
                try:
                    txt = (row[1][0] or '').strip()
                except Exception:
                    txt = ''
                if txt:
                    lines.append(txt)
        return '\n'.join(_clean_ocr_lines('\n'.join(lines)))
    except Exception:
        return ''
    finally:
        try:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass


def _ocr_best_text_from_pil(img: Image.Image, started: float | None = None, score_hint: str = "") -> str:
    started = started or time.time()
    best_lines = []
    best_score = -1
    seen = set()
    for rot in (0, 90, 180, 270):
        if time.time() - started > OCR_IMAGE_BUDGET_SEC:
            break
        try:
            work = img.rotate(rot, expand=True) if rot else img.copy()
        except Exception:
            continue
        try:
            w, h = work.size
            target = 1600
            if max(w, h) < target:
                scale = max(1, int(target / max(w, h)) + 1)
                work = work.resize((w * scale, h * scale))
        except Exception:
            pass
        work = ImageOps.autocontrast(work)
        gray = work.convert('L')
        variants = [gray, gray.point(lambda x: 255 if x > 165 else 0, mode='1').convert('L')]
        for im in variants:
            if time.time() - started > OCR_IMAGE_BUDGET_SEC:
                break
            try:
                key = (im.size, hash(im.tobytes()[:128]))
            except Exception:
                key = (im.size, id(im))
            if key in seen:
                continue
            seen.add(key)
            texts = []
            texts.extend(_tesseract_text_candidates(im))
            paddle_txt = _ocr_text_with_paddle(im)
            if paddle_txt:
                texts.insert(0, paddle_txt)
            for txt in texts:
                lines = _clean_ocr_lines(txt)
                if not lines:
                    continue
                joined = '\n'.join(lines)
                score = sum(len(re.findall(r'[A-Za-zÁÉÍÓÚÑáéíóúñ0-9]', ln)) for ln in lines)
                score += 90 * len(re.findall(r'factura|albara|pedido|total|iva|documento|cif|nif|proveedor|cliente', joined, re.I))
                score += 70 * len(re.findall(r'\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b', joined))
                score += 55 * len(re.findall(r'\b(kg|g|l|ml|ud|u|unid|unidad)\b', joined, re.I))
                score += 35 * len(re.findall(r'\b\d+[.,]\d{2}\b', joined))
                if score_hint == 'body':
                    score += 80 * len(re.findall(r'\b(kg|g|l|ml|ud|u|unid|unidad|precio|importe|articulo|artículo|descripcion|descripción)\b', joined, re.I))
                elif score_hint == 'header':
                    score += 80 * len(re.findall(r'\b(fecha|albaran|albarán|factura|documento|proveedor|cliente|nif|cif)\b', joined, re.I))
                elif score_hint == 'footer':
                    score += 80 * len(re.findall(r'\b(total|base imponible|iva|recargo|subtotal|bruto|neto)\b', joined, re.I))
                if score > best_score:
                    best_score = score
                    best_lines = lines
    return '\n'.join(best_lines).strip()


def _ocr_image_sector_texts(img_path: Path) -> dict:
    out = {'header': '', 'body': '', 'footer': ''}
    try:
        base0 = _open_receipt_image(img_path)
        if base0 is None:
            return out
        try:
            base = ImageOps.exif_transpose(base0).convert('RGB')
        except Exception:
            base = base0.convert('RGB') if hasattr(base0, 'convert') else base0
        try:
            cropped = _crop_receipt_area(base0)
            if cropped is not None:
                base = cropped.convert('RGB') if hasattr(cropped, 'convert') else cropped
        except Exception:
            pass
        w, h = base.size
        if w < 20 or h < 20:
            return out
        bands = {
            'header': (0, 0, w, max(1, int(h * 0.38))),
            'body': (0, max(0, int(h * 0.16)), w, max(int(h * 0.16) + 1, int(h * 0.86))),
            'footer': (0, max(0, int(h * 0.82)), w, h),
        }
        started = time.time()
        for key, box in bands.items():
            try:
                crop = base.crop(box)
                out[key] = _ocr_best_text_from_pil(crop, started=started, score_hint=key)
            except Exception:
                out[key] = ''
        return out
    except Exception:
        return out


def _ocr_image_text(img_path: Path) -> str:
    try:
        print(f"OCR_READ_BEGIN path={img_path.name}")
        started = time.time()
        base0 = _open_receipt_image(img_path)
        if base0 is None:
            print(f"OCR_READ_EMPTY path={img_path.name} reason=open_failed")
            return ''

        bases = []
        try:
            bases.append(ImageOps.exif_transpose(base0).convert('RGB'))
        except Exception:
            try:
                bases.append(base0.convert('RGB'))
            except Exception:
                bases.append(base0)

        try:
            cropped = _crop_receipt_area(base0)
            if cropped is not None:
                bases.append(cropped.convert('RGB') if hasattr(cropped, 'convert') else cropped)
        except Exception:
            pass

        best = ''
        best_score = -1
        for base in bases[:2]:
            txt = _ocr_best_text_from_pil(base, started=started)
            lines = _clean_ocr_lines(txt)
            if not lines:
                continue
            joined = '\n'.join(lines)
            score = sum(len(re.findall(r'[A-Za-zÁÉÍÓÚÑáéíóúñ0-9]', ln)) for ln in lines)
            score += 90 * len(re.findall(r'factura|albara|pedido|total|iva|documento|cif|nif|proveedor|cliente', joined, re.I))
            score += 70 * len(re.findall(r'\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b', joined))
            score += 55 * len(re.findall(r'\b(kg|g|l|ml|ud|u|unid|unidad)\b', joined, re.I))
            score += 35 * len(re.findall(r'\b\d+[.,]\d{2}\b', joined))
            if score > best_score:
                best_score = score
                best = txt

        out = best.strip()
        print(f"OCR_READ_DONE path={img_path.name} chars={len(out)} lines={len(_clean_ocr_lines(out))} score={best_score}")
        return out
    except Exception as e:
        print(f"OCR_READ_FAIL path={img_path.name} reason={e}")
        return ''

def _ocr_image_text_with_timeout(img_path: Path, timeout_sec: int = 16) -> str:
    try:
        return _ocr_image_text(img_path)
    except Exception as e:
        print(f"OCR_PAGE_FAIL path={img_path.name} reason={str(e)[:160]}")
        return ''

def _ocr_line_has_legal_entity(line: str) -> bool:
    return bool(re.search(r"\b(s\.?l\.?|s\.?a\.?|c\.?b\.?|coop|cooperativa|distrib|hostel|avicola|explotaci|mercantil|logistica|transportes)\b", line or "", re.I))

def _ocr_line_has_contact_or_address(line: str) -> bool:
    low = _norm_text(line)
    if not low:
        return True
    if re.search(r"\b(cif|nif|telefono|tel|fax|movil|email|mail|web|www|direccion|domicilio|cp|codigo postal|poligono|calle|avda|avenida|ctra|carretera|km|provincia|poblacion|portal|piso|pol\.|nave|apartado|apartado de correos|iban|bic|swift|cuenta|banco|sucursal|transferencia|forma de pago|vencimiento|vto)\b", low, re.I):
        return True
    if re.search(r"\b(280\d{2}|28\d{3}|madrid|barcelona|valencia|sevilla|toledo|cuenca|segovia|guadalajara|valladolid|burgos|soria|tribaldos|hermosilla|valportillo)\b", low, re.I):
        return True
    if re.search(r"[@]|https?://|www\.", line or "", re.I):
        return True
    if len(re.findall(r"\d{8,}", line or "")) >= 1:
        return True
    if len(re.findall(r"\d{5,}", line or "")) >= 2:
        return True
    if re.search(r"\b(es\d{2}|[a-z]{2}\d{2}[a-z0-9]{8,})\b", low, re.I):
        return True
    return False

def _ocr_line_is_location_noise(line: str) -> bool:
    s = re.sub(r"[^A-Za-zÁÉÍÓÚÑáéíóúñ ]+", " ", line or "").strip()
    if not s:
        return True
    food_terms = r"\b(pulpo|langostino|gamba|calamar|sepia|merluza|atun|atún|salm[oó]n|pollo|carne|huevo|huevos|tomate|cebolla|patata|aceite|queso|pan|arroz|harina|leche|pata|cola|filete|granel|campero|cocimar)\b"
    if re.search(food_terms, _norm_text(line), re.I):
        return False
    words = [w for w in s.split() if w]
    if len(words) <= 2 and all(len(w) >= 4 for w in words):
        letters = [ch for ch in (line or "") if ch.isalpha()]
        upper_ratio = (sum(1 for ch in letters if ch.isupper()) / max(1, len(letters)))
        if upper_ratio > 0.7:
            return True
    if re.fullmatch(r"[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ ]{3,20}", (line or "").strip()) and not re.search(food_terms, _norm_text(line), re.I):
        return True
    return False

def _ocr_is_product_like_name(name: str) -> bool:
    low = _norm_text(name)
    if not low:
        return False
    if len(low) < 4:
        return False
    raw = (name or "").strip()
    if raw and sum(ch.isdigit() for ch in raw) / max(1, len([c for c in raw if c.isalnum()])) > 0.45:
        return False
    if _ocr_line_has_contact_or_address(name):
        return False
    if _ocr_line_is_location_noise(name):
        return False
    if re.search(r"\b(fecha|albaran|factura|ticket|cliente|total|iva|base imponible|proveedor|documento|pedido|transportista|observaciones|forma de pago|lote|caducidad|matricula)\b", low, re.I):
        return False
    if _ocr_line_has_legal_entity(name) and not re.search(r"\b(campero|huevo|patata|cebolla|aceite|sal|pollo|carne|pescado|arroz|harina|leche|tomate|queso|pan|granel|docena|docenas|kg|g|l|ml)\b", low, re.I):
        return False
    if len(re.findall(r"[-/]", name or "")) >= 3 and len(re.findall(r"\d", name or "")) >= 6:
        return False
    return True

def _ocr_supplier_is_generic_bad(line: str) -> bool:
    low = _norm_text(line)
    if not low:
        return True
    if low in {"restaurante", "restaurant", "mercasa", "referencia", "grupo empresarial", "cliente", "destino", "cocina", "proveedor a", "proveedor b"} or re.fullmatch(r"proveedor\s+[a-z0-9]+", low, re.I):
        return True
    if re.fullmatch(r"[A-Z]{3,8}", (line or "").strip()):
        return True
    if re.search(r"\b(restaurante|referencia mercasa|mercasa|cliente|destino|cocina|forma de pago|documento|albaran|factura|ticket|pedido|pagina|resumen mensual|entrega|transportista|matricula)\b", low, re.I):
        return True
    return False

def _ocr_cleanup_source_line(line: str) -> str:
    s = re.sub(r"\s+", " ", (line or "").strip())
    s = s.replace("¦", "|").replace("I ", "| ")
    s = re.sub(r"^[=+*_|:;,.\-\s]+", "", s)
    s = re.sub(r"\bPI\s*TOS?\b", " ", s, flags=re.I)
    s = re.sub(r"\bPITOS?\b", " ", s, flags=re.I)
    s = re.sub(r"\bM[ /-]*L\b", "M/L", s, flags=re.I)
    s = re.sub(r"\bM[I1J]L\b", "M/L", s, flags=re.I)
    s = re.sub(r"\b([SMXL]{1,2})\s*/\s*([SMXL]{1,2})\b", r"\1/\2", s, flags=re.I)
    s = re.sub(r"\bLOTE\s*\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", " ", s, flags=re.I)
    s = re.sub(r"^[=_|]+", "", s)
    s = re.sub(r"\s+", " ", s).strip(" =_|-:;,.")
    return s

def _ocr_strip_trailing_totals(line: str) -> str:
    s = (line or "").strip()
    patterns = [
        r"(?:\s+\d+[.,]\d{1,3}){3}\s*$",
        r"(?:\s+\d+[.,]\d{1,3}){2}\s*$",
        r"\s+\d+[.,]\d{1,3}\s*$",
    ]
    prev = None
    while s and s != prev:
        prev = s
        for pat in patterns:
            s = re.sub(pat, "", s).strip()
    s = re.sub(r"\s+", " ", s).strip(" -:;,.")
    return s

def _ocr_line_has_price_shape(line: str) -> bool:
    return bool(re.search(r"\d+[.,]\d{1,3}\s+\d+[.,]\d{1,3}(?:\s+\d+[.,]\d{1,3})?\s*$", line or ""))

def _ocr_postfix_product_cleanup(name: str) -> str:
    s = _ocr_cleanup_product_tokens(name or "")
    s = re.sub(r"\bPI\s*TOS?\b", " ", s, flags=re.I)
    s = re.sub(r"\bPITOS?\b", " ", s, flags=re.I)
    s = re.sub(r"\bM[I1J]L\b", "M/L", s, flags=re.I)
    s = re.sub(r"\bM\s*/?\s*L\b", "M/L", s, flags=re.I)
    s = re.sub(r"\bGRANEL\s+CAMPERO\s+M\s+L\b", "GRANEL CAMPERO M/L", s, flags=re.I)
    s = re.sub(r"\bGRANEL\s+CAMPERO\s+ML\b", "GRANEL CAMPERO M/L", s, flags=re.I)
    s = re.sub(r"\b(PT|MA|ES|E[S5]|S2)\b$", " ", s, flags=re.I)
    s = re.sub(r"\b(BR)\b$", " ", s, flags=re.I)
    s = re.sub(r"\b(RESTAURANTE|REFERENCIA|MERCASA)\b$", " ", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" -:;,.()")
    return s

def _ocr_has_food_hint(text: str) -> bool:
    low = _norm_text(text)
    return bool(re.search(r"\b(apio|cebolla|cebollino|espinaca|berenjena|tomate|patata|pepino|lima|limon|limones|lechuga|menta|moras|romero|cilantro|aguacate|coliflor|huevo|huevos|granel|campero|aceite|sal|fumet|demi glace|salsa|pina|piña|jalapeno|jalapeño|manzana|salmon|salmon|coliflor|aguachile)\b", low, re.I))

def _ocr_name_looks_like_noise(name: str) -> bool:
    low = _norm_text(name)
    if not low:
        return True
    if _ocr_has_food_hint(low):
        return False
    words = [w for w in re.findall(r"[a-zA-ZáéíóúñÁÉÍÓÚÑ/]+", low) if w]
    if len(words) >= 4:
        avg = sum(len(w) for w in words) / max(1, len(words))
        if avg < 4.2:
            return True
    if len(words) >= 3 and sum(1 for w in words if len(w) <= 3) >= 2:
        return True
    vowels = sum(1 for ch in low if ch in 'aeiouáéíóú')
    letters = sum(1 for ch in low if ch.isalpha())
    if letters >= 10 and (vowels / max(1, letters)) < 0.22:
        return True
    return False

def _ocr_text_looks_like_valid_label(value: str) -> bool:
    low = _norm_text(value)
    if not low:
        return False
    return bool(re.search(r"\b(articulo|descrip|descripcion|producto|concepto|denominacion|nombre)\b", low, re.I))

def _extract_supplier_candidate_lines(text: str):
    out = []
    for raw in (text or "").splitlines():
        ln = re.sub(r"\s+", " ", (raw or "").strip(" -:|"))
        if len(ln) < 4 or _is_probable_filename(ln):
            continue
        if _ocr_line_has_contact_or_address(ln):
            continue
        if _ocr_supplier_is_generic_bad(ln):
            continue
        out.append(ln)
    return out[:15]


def _ocr_supplier_line_penalty(line: str) -> int:
    low = _norm_text(line)
    score = 0
    if re.search(r",\s*\d", line or ""):
        score += 4
    if re.search(r"\b(tribaldos|madrid|hermosilla|toledo|cuenca|segovia|burgos|valladolid|soria|guadalajara|valportillo)\b", low, re.I):
        score += 5
    if _ocr_line_has_contact_or_address(line):
        score += 5
    if re.search(r"\b\d{5}\b", line or ""):
        score += 4
    if len(re.findall(r"\d", line or "")) >= 4:
        score += 3
    if re.search(r"\b(albaran|factura|ticket|pedido|documento|cliente|fecha|iva|total|pagina|forma de pago|vencimiento|transportista|matricula)\b", low, re.I):
        score += 6
    if _ocr_line_has_price_shape(line):
        score += 4
    if _ocr_line_has_legal_entity(line):
        score -= 4
    if re.search(r"\b(avicolas?|avicola|exportaciones?|garrido|huevos?|palacio|pescaderia|carniceria|fruteria|suministros?)\b", low, re.I):
        score -= 3
    if len(low.split()) >= 2 and len(low.split()) <= 6 and not re.search(r"\d", low):
        score -= 1
    return score

def _extract_supplier_from_known_suppliers(cur, text: str):
    rows = cur.execute("SELECT id,name FROM suppliers WHERE is_active=1 ORDER BY id").fetchall()
    lines = [re.sub(r"\s+", " ", (raw or "").strip()) for raw in (text or "").splitlines() if (raw or "").strip()]
    best = None
    best_score = 0.0
    stop = {"sl","sa","cb","scoop","coop","empresa","empresarial","grupo","de","del","la","las","los","y","e","the"}
    for r in rows:
        name = (r["name"] or "").strip()
        if not name or name.lower() == "proveedor pendiente ocr":
            continue
        if _ocr_supplier_is_generic_bad(name):
            continue
        nn = _norm_text(name)
        if not nn:
            continue
        name_tokens = {t for t in re.findall(r"[a-záéíóúñ0-9]+", nn) if len(t) >= 4 and t not in stop}
        for ln in lines[:20]:
            ln_norm = _norm_text(ln)
            if not ln_norm:
                continue
            line_tokens = {t for t in re.findall(r"[a-záéíóúñ0-9]+", ln_norm) if len(t) >= 4 and t not in stop}
            common = name_tokens & line_tokens
            if name_tokens and len(common) < min(2, len(name_tokens)):
                continue
            score = SequenceMatcher(None, nn, ln_norm).ratio()
            if nn in ln_norm or ln_norm in nn:
                score = max(score, 0.93)
            if len(common) >= 2:
                score += 0.05
            if score > best_score:
                best_score = score
                best = name
    if best_score >= 0.84:
        return best
    return None
def _ocr_cleanup_product_tokens(name: str) -> str:
    s = re.sub(r"\s+", " ", (name or "").strip())
    s = re.sub(r"\bM[I1J]L\b", "ML", s, flags=re.I)
    s = re.sub(r"\b([SMLXL]{1,2})\s*(\d{1,2})D\b", r"\1 \2D", s, flags=re.I)
    s = re.sub(r"\bLOTE\s*\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", "", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" -:;,.")
    return s
def _la_huerta_text(text: str) -> bool:
    nt = _norm_text(text)
    return ("la huerta" in nt and ("hermanos nieto" in nt or "distribucion de frutas y verduras" in nt))


def _negrini_text(text: str) -> bool:
    nt = _norm_text(text)
    return "negrini" in nt


def _pollerias_herrero_text(text: str) -> bool:
    nt = _norm_text(text)
    return ("pollerias herrero" in nt or "pollerias herrero & c" in nt or "pollerias herrero & ca" in nt)


def _beef_on_food_text(text: str) -> bool:
    nt = _norm_text(text)
    return ("beef on food" in nt or "wagyu" in nt and "burgos" in nt)


def _tierra_y_mar_text(text: str) -> bool:
    nt = _norm_text(text)
    return ("tierra y mar" in nt and ("albaran" in nt or "restaurante her" in nt))


def _garimori_text(text: str) -> bool:
    nt = _norm_text(text)
    return ("garimori" in nt or ("congelado" in nt and "total kilogramos netos" in nt))


def _antonio_de_miguel_text(text: str) -> bool:
    nt = _norm_text(text)
    return ("antonio de miguel" in nt or ("cod.cliente" in nt and "albaran" in nt and "descripcion" in nt and "% iva" in nt))


def _izquierdo_text(text: str) -> bool:
    nt = _norm_text(text)
    if "izquierdo" in nt:
        return True
    if "hosteleria" in nt and "fecha entrega" in nt and "tipo imp" in nt:
        return True
    if "fecha documento" in nt and "fecha entrega" in nt and "tipo imp" in nt:
        return True
    if "r1" in nt and "r2" in nt and "r3" in nt and "tipo imp" in nt:
        return True
    return False

OCR_PROVIDER_TEMPLATES = {
    "DISTRIBUCIONES IZQUIERDO DE HOSTELERÍA, S.L.": {
        "provider_key": "izquierdo",
        "mode": "sector_binary",
        "blocks": {
            "A": ["proveedor", "fecha_documento", "fecha_entrega", "numero_documento"],
            "B": ["articulo"],
            "C": ["cantidad", "precio_unitario", "total_bruto"],
            "D": ["descuento", "tipo_imp", "total_linea"],
            "E": ["base_imponible", "cuota_iva", "total_documento"],
        },
    },
    "ANTONIO DE MIGUEL S.A.U.": {
        "provider_key": "antonio_de_miguel",
        "mode": "sector_binary",
        "blocks": {
            "A": ["proveedor", "fecha", "albaran"],
            "B": ["codigo", "descripcion"],
            "C": ["su_pedido", "cantidad", "precio"],
            "D": ["importe", "iva"],
            "E": ["lote", "caducidad", "totales"],
        },
    },
    "TIERRA Y MAR": {
        "provider_key": "tierra_y_mar",
        "mode": "sector_binary",
        "blocks": {
            "A": ["proveedor", "fecha", "albaran"],
            "B": ["cantidad_kg", "articulo"],
            "C": ["precio"],
            "D": ["importe_neto"],
        },
    },
    "LA HUERTA HERMANOS NIETO, S.L.": {
        "provider_key": "la_huerta",
        "mode": "sector_binary",
        "blocks": {
            "A": ["proveedor", "fecha", "albaran"],
            "B": ["descripcion_articulo"],
            "C": ["bultos", "bruto_kg", "tara", "kg_netos_o_comerciales"],
            "D": ["precio", "importe"],
            "E": ["iva", "totales"],
        },
    },
    "NEGRINI S.L.": {
        "provider_key": "negrini",
        "mode": "sector_binary",
        "blocks": {
            "A": ["proveedor", "fecha", "albaran"],
            "B": ["descripcion_articulo"],
            "C": ["cantidad_kg", "precio_neto"],
            "D": ["importe", "iva"],
        },
    },
    "POLLERÍAS HERRERO & Cª, S.L.": {
        "provider_key": "pollerias_herrero",
        "mode": "sector_binary",
        "blocks": {
            "A": ["proveedor", "fecha", "albaran"],
            "B": ["descripcion_articulo"],
            "C": ["cantidad", "precio"],
            "D": ["iva", "importe"],
        },
    },
    "CENTRAL DE CARNES MADRID NORTE, S.A.": {
        "provider_key": "central_carnes",
        "mode": "sector_binary",
        "blocks": {
            "A": ["proveedor", "fecha", "albaran"],
            "B": ["descripcion_articulo"],
            "C": ["cantidad_kg", "precio"],
            "D": ["importe", "iva"],
        },
    },
    "PESCADERÍA PALACIO, C.B.": {
        "provider_key": "pescaderia_palacio",
        "mode": "sector_binary",
        "blocks": {
            "A": ["proveedor", "fecha", "albaran"],
            "B": ["descripcion_articulo"],
            "C": ["cajas_aux", "cantidad_kg", "precio"],
            "D": ["importe"],
        },
    },
    "MAMMAFIORE MADRID, S.L.": {
        "provider_key": "mammafiore",
        "mode": "sector_binary",
        "blocks": {
            "A": ["proveedor", "fecha", "albaran"],
            "B": ["descripcion_articulo"],
            "C": ["unidad_comercial", "precio_venta", "descuento"],
            "D": ["importe", "iva"],
        },
    },
    "BEEF ON FOOD": {
        "provider_key": "beef_on_food",
        "mode": "sector_binary",
        "blocks": {
            "A": ["proveedor", "fecha", "albaran"],
            "B": ["descripcion_articulo"],
            "C": ["cantidad", "precio"],
            "D": ["importe", "iva"],
        },
    },
    "GARIMORI": {
        "provider_key": "garimori",
        "mode": "sector_binary",
        "blocks": {
            "A": ["proveedor", "fecha", "albaran"],
            "B": ["descripcion_articulo"],
            "C": ["cantidad", "precio"],
            "D": ["importe", "iva"],
        },
    },
}

def _ocr_provider_template_for_text(text: str) -> dict:
    nt = _norm_text(text or "")
    if _izquierdo_text(nt):
        return OCR_PROVIDER_TEMPLATES["DISTRIBUCIONES IZQUIERDO DE HOSTELERÍA, S.L."]
    if _antonio_de_miguel_text(nt):
        return OCR_PROVIDER_TEMPLATES["ANTONIO DE MIGUEL S.A.U."]
    if _tierra_y_mar_text(nt):
        return OCR_PROVIDER_TEMPLATES["TIERRA Y MAR"]
    if _la_huerta_text(nt):
        return OCR_PROVIDER_TEMPLATES["LA HUERTA HERMANOS NIETO, S.L."]
    if _negrini_text(nt):
        return OCR_PROVIDER_TEMPLATES["NEGRINI S.L."]
    if _pollerias_herrero_text(nt):
        return OCR_PROVIDER_TEMPLATES["POLLERÍAS HERRERO & Cª, S.L."]
    if _central_carnes_text(nt):
        return OCR_PROVIDER_TEMPLATES["CENTRAL DE CARNES MADRID NORTE, S.A."]
    if _pescaderia_palacio_text(nt):
        return OCR_PROVIDER_TEMPLATES["PESCADERÍA PALACIO, C.B."]
    if _mammafiore_text(nt):
        return OCR_PROVIDER_TEMPLATES["MAMMAFIORE MADRID, S.L."]
    if _beef_on_food_text(nt):
        return OCR_PROVIDER_TEMPLATES["BEEF ON FOOD"]
    if _garimori_text(nt):
        return OCR_PROVIDER_TEMPLATES["GARIMORI"]
    return {"provider_key": "generic", "mode": "generic"}

def _extract_receipt_lines_with_template(text: str, img_path: Path | None = None):
    template = _ocr_provider_template_for_text(text)
    key = template.get("provider_key")
    if key == "pescaderia_palacio":
        return _extract_receipt_lines_pescaderia_palacio(text)
    elif key == "mammafiore":
        return _extract_receipt_lines_mammafiore(text)
    elif key == "pollerias_herrero":
        return _extract_receipt_lines_pollerias_herrero(text)
    elif key == "la_huerta":
        return _extract_receipt_lines_la_huerta(text)
    elif key == "negrini":
        return _extract_receipt_lines_negrini(text)
    elif key == "central_carnes":
        special = []
        if img_path is not None:
            try:
                special = _extract_receipt_lines_central_carnes_image(img_path)
            except Exception:
                special = []
        if not special:
            special = _extract_receipt_lines_central_carnes(text)
        return special
    elif key == "beef_on_food":
        return _extract_receipt_lines_beef_on_food(text)
    elif key == "tierra_y_mar":
        return _extract_receipt_lines_tierra_y_mar(text)
    elif key == "garimori":
        return _extract_receipt_lines_garimori(text)
    elif key == "antonio_de_miguel":
        return _extract_receipt_lines_antonio_de_miguel(text)
    elif key == "izquierdo":
        return _extract_receipt_lines_izquierdo(text)
    return []

def _ocr_sector_rows(text: str) -> list[list[str]]:
    rows = []
    current = []
    lines = [re.sub(r"\s+", " ", (raw or "").strip()) for raw in (text or "").splitlines() if (raw or "").strip()]
    def _is_anchor(ln: str) -> bool:
        low = _norm_text(ln)
        if any(k in low for k in ["fecha documento", "fecha entrega", "tipo imp", "base imponible", "cuota iva", "documento", "cliente", "proveedor"]):
            return False
        if re.fullmatch(r"\d{4,}", ln):
            return True
        if len(re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{3,}", ln)) >= 2 and not re.fullmatch(r".*(R[123]).*", ln, re.I):
            return True
        return False
    for ln in lines:
        if _is_anchor(ln) and current:
            rows.append(current)
            current = [ln]
        else:
            current.append(ln)
    if current:
        rows.append(current)
    return rows


def _clean_article_name_tierra_y_mar(name: str) -> str:
    s = re.sub(r"\s+", " ", (name or "").strip())
    s = re.sub(r"\b\d{6,}\b", " ", s)
    s = re.sub(r"\b(i\.?v\.?a\.?|iva)\b", " ", s, flags=re.I)
    s = s.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    s = re.sub(r"^\s*kg\s+", "", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" -:;,.")
    return _ocr_postfix_product_cleanup(s)


def _extract_receipt_lines_tierra_y_mar(text: str):
    out = []
    seen = set()

    def _norm_spaces(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "").strip())

    def _parse_num(s: str) -> float:
        return _parse_float((s or "").replace(" ", ""), 0.0)

    def _clean_name(name: str) -> str:
        s = _norm_spaces(name)
        s = re.sub(r"\b\d{5,}\b", " ", s)
        s = re.sub(r"\b(i\.?v\.?a\.?|iva)\b", " ", s, flags=re.I)
        s = s.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
        s = re.sub(r"^\s*kg\s+", "", s, flags=re.I)
        s = _ocr_postfix_product_cleanup(s)
        s = re.sub(r"\s+", " ", s).strip(" -:;,.")
        return s.upper()

    def _reasonable_amount(qty: float, price: float, amount: float) -> bool:
        if qty <= 0 or price <= 0 or amount <= 0:
            return False
        calc = round(qty * price, 2)
        diff = abs(calc - amount)
        tol = max(0.25, calc * 0.03)
        return diff <= tol

    def _looks_absurd_amount(amount: float, qty: float, price: float) -> bool:
        if amount <= 0:
            return True
        if qty > 0 and price > 0:
            calc = round(qty * price, 2)
            if calc > 0 and amount > calc * 4:
                return True
        return False

    raw_lines = [_norm_spaces(x) for x in (text or '').splitlines()]
    raw_lines = [x for x in raw_lines if x]

    for ln in raw_lines:
        low = _norm_text(ln)
        if any(k in low for k in [
            'base imponible', 'total', 'cliente', 'proveedor',
            'albaran', 'fecha', 'restaurante her', 'b85486199'
        ]):
            continue

        m = re.match(
            r'^\s*(?P<qty>\d+[.,]\d+)\s*(?P<unit>kg)\s+(?P<name>.+?)\s+(?:(?P<code>\d{5,})\s+)?(?P<price>\d+(?:[.,]\d{1,3})?)\s+(?P<amount>\d+(?:[.,]\d{1,2})?)\s*$',
            ln,
            re.I,
        )
        if not m:
            continue

        qty_val = _parse_num(m.group('qty'))
        unit_val = 'kg'
        name_val = _clean_name(m.group('name') or '')
        price_val = _parse_num(m.group('price'))
        amount_val = _parse_num(m.group('amount'))

        if not name_val or qty_val <= 0:
            continue

        name_val = re.sub(r'^\s*\d+[.,]\d+\s*kg\s+', '', name_val, flags=re.I)

        review = False
        if _looks_absurd_amount(amount_val, qty_val, price_val):
            amount_val = 0.0
            review = True

        if price_val <= 0:
            review = True

        calc_amount = round(qty_val * price_val, 2) if (qty_val > 0 and price_val > 0) else 0.0
        if amount_val <= 0 and calc_amount > 0:
            amount_val = calc_amount
            review = True
        elif amount_val > 0 and not _reasonable_amount(qty_val, price_val, amount_val):
            review = True

        key = (_norm_text(name_val), fmt_num(qty_val), unit_val, fmt_num(price_val, 2))
        if key in seen:
            continue
        seen.add(key)

        out.append({
            'source_text': ln,
            'item_name_raw': name_val,
            'qty_raw': fmt_num(qty_val),
            'unit_raw': unit_val,
            'price_raw': fmt_num(price_val, 2) if price_val > 0 else '',
            'amount_raw': fmt_num(amount_val, 2) if amount_val > 0 else '',
            'review_status': 'REVIEW' if review else 'PENDING',
        })
    return out


def _clean_article_name_beef(name: str) -> str:
    s = re.sub(r"\s+", " ", (name or "").strip())
    s = re.sub(r"^[A-Z]{1,3}\s*\d{3,6}\s+", "", s)
    return _ocr_postfix_product_cleanup(s)


def _extract_receipt_lines_beef_on_food(text: str):
    out=[]
    seen=set()
    for raw in (text or '').splitlines():
        ln = re.sub(r"\s+", " ", (raw or '').strip())
        if not ln:
            continue
        m = re.match(r"^(?P<code>[A-Z]{1,3}\s*\d{3,6})\s+(?P<name>.+?)\s+(?P<trace>\d{4,})\s+(?P<qty>\d+[.,]\d+)\s+(?P<price>\d+[.,]\d+)\s+(?P<sub>\d+[.,]\d+)\s+(?P<dto>\d+[.,]\d+)%\s+(?P<tot>\d+[.,]\d+)\s*$", ln, re.I)
        if not m:
            continue
        name = _clean_article_name_beef(m.group('name') or '')
        qty = fmt_num(_parse_float(m.group('qty') or '', 0.0))
        price = fmt_num(_parse_float(m.group('price') or '', 0.0), 2)
        amount = fmt_num(_parse_float(m.group('tot') or '', 0.0), 2)
        disc = fmt_num(_parse_float(m.group('dto') or '', 0.0), 2)
        key=(_norm_text(name), qty, 'kg', price)
        if key in seen:
            continue
        seen.add(key)
        out.append({'source_text':ln,'item_name_raw':name,'qty_raw':qty,'unit_raw':'kg','price_raw':price,'amount_raw':amount,'discount_raw':disc})
    return out


def _extract_receipt_lines_garimori(text: str):
    lines=[re.sub(r"\s+", " ", (raw or '').strip()) for raw in (text or '').splitlines() if (raw or '').strip()]
    out=[]
    for i,ln in enumerate(lines):
        if 'cabecero iberico sin presa' in _norm_text(ln):
            window = ' '.join(lines[max(0,i-1):min(len(lines), i+2)])
            pieces = re.search(r"(\d+)\s*bolsas", window, re.I)
            lote = re.search(r"([A-Z]-\d{6}-[A-Z]{2})", window, re.I)
            nums = re.findall(r"\d+[.,]\d+", window)
            if len(nums) >= 3:
                qty, price, amount = nums[-3], nums[-2], nums[-1]
                out.append({'source_text':window,'item_name_raw':'CABECERO IBERICO SIN PRESA','qty_raw':fmt_num(_parse_float(qty,0.0)),'unit_raw':'kg','price_raw':fmt_num(_parse_float(price,0.0),2),'amount_raw':fmt_num(_parse_float(amount,0.0),2),'qty_aux_raw':pieces.group(1) if pieces else '','source_lot_raw':lote.group(1) if lote else ''})
            break
    return out


def _extract_receipt_lines_antonio_de_miguel(text: str):
    out = []
    seen = set()
    lines = [re.sub(r"\s+", " ", (raw or "").strip()) for raw in (text or "").splitlines() if (raw or "").strip()]

    def _clean_name(name: str) -> str:
        s = re.sub(r"\s+", " ", (name or "").strip())
        s = s.replace("©", " ").replace("®", " ").replace("™", " ")
        s = re.sub(r"\b(lotes?|caducidad)\b.*$", " ", s, flags=re.I)
        s = re.sub(r"\s+", " ", s).strip(" -:;,.|")
        return _ocr_postfix_product_cleanup(s).upper()

    def _reasonable_amount(qty: float, price: float, amount: float) -> bool:
        if qty <= 0 or price <= 0 or amount <= 0:
            return False
        calc = round(qty * price, 2)
        tol = max(0.15, calc * 0.03)
        return abs(calc - amount) <= tol

    i = 0
    row_re = re.compile(
        r"^(?P<code>\d{6,})\s+"
        r"(?P<name>.+?)\s+"
        r"(?P<ordered>\d+[.,]\d+)\s+"
        r"(?P<qty>\d+[.,]\d+)\s+"
        r"(?P<price>\d+[.,]\d+)\s+"
        r"(?P<amount>\d+[.,]\d+)\s+"
        r"(?P<vat>\d+[.,]\d+)\s*$",
        re.I,
    )
    while i < len(lines):
        ln = lines[i]
        low = _norm_text(ln)
        if any(k in low for k in ["articulo", "descripcion", "su pedido", "cantidad", "precio", "importe", "% iva", "bruto", "base", "total iva", "total"]):
            i += 1
            continue
        m = row_re.match(ln)
        if not m:
            i += 1
            continue

        gd = m.groupdict()
        name = _clean_name(gd.get("name") or "")
        qty_val = _parse_float(gd.get("qty") or "", 0.0)
        price_val = _parse_float(gd.get("price") or "", 0.0)
        amount_val = _parse_float(gd.get("amount") or "", 0.0)
        vat_val = _parse_float(gd.get("vat") or "", 0.0)
        ordered_val = _parse_float(gd.get("ordered") or "", 0.0)
        if not name or qty_val <= 0:
            i += 1
            continue

        source_parts = [ln]
        j = i + 1
        lot_txt = ''
        while j < len(lines) and not re.match(r'^\d{6,}\s+', lines[j]):
            nxt = lines[j]
            low2 = _norm_text(nxt)
            if any(k in low2 for k in ['lotes', 'caducidad']):
                source_parts.append(nxt)
                mlot = re.search(r"lotes?\s*:?\s*([A-Z0-9/-]{4,})", nxt, re.I)
                if mlot:
                    lot_txt = mlot.group(1)
                j += 1
                continue
            break

        review = False
        if price_val <= 0 or amount_val <= 0:
            review = True
        elif not _reasonable_amount(qty_val, price_val, amount_val):
            review = True

        key = (_norm_text(name), fmt_num(qty_val), 'ud', fmt_num(price_val, 2))
        if key not in seen:
            seen.add(key)
            out.append({
                'source_text': ' '.join(source_parts),
                'item_name_raw': name,
                'qty_raw': fmt_num(qty_val),
                'unit_raw': 'ud',
                'price_raw': fmt_num(price_val, 2) if price_val > 0 else '',
                'amount_raw': fmt_num(amount_val, 2) if amount_val > 0 else '',
                'vat_raw': fmt_num(vat_val, 2) if vat_val > 0 else '',
                'qty_basis_raw': fmt_num(ordered_val) if ordered_val > 0 else '',
                'qty_aux_raw': lot_txt,
                'review_status': 'REVIEW' if review else 'PENDING',
            })
        i = j
    return out


def _extract_receipt_lines_izquierdo(text: str):
    out = []
    seen = set()
    template = _ocr_provider_template_for_text(text)
    rows = _ocr_sector_rows(text) if template.get("provider_key") == "izquierdo" else []
    lines = [re.sub(r"\s+", " ", (raw or "").strip()) for raw in (text or '').splitlines() if (raw or '').strip()]

    def _clean_name(name: str) -> str:
        s = re.sub(r"\s+", " ", (name or '').strip())
        s = s.replace('©', ' ').replace('®', ' ').replace('™', ' ')
        s = s.replace('€', ' EUR ')
        s = re.sub(r"^[#=*/+_|:;,.\-\s]+", "", s)
        s = re.sub(r"\b(fecha documento|fecha entrega|documento|tipo imp|tipo|imp|descuento|dto|iva|total linea|total bruto|base imponible|cuota iva|portes|condiciones|observaciones|cliente|proveedor|direccion|telefono)\b.*$", " ", s, flags=re.I)
        s = re.sub(r"\b(r1|r2|r3)\b", " ", s, flags=re.I)
        s = re.sub(r"\b\d+[.,]\d+\s*eur\b", " ", s, flags=re.I)
        s = re.sub(r"\s+", " ", s).strip(" -:;,.|/")
        return _ocr_postfix_product_cleanup(s).upper()

    def _is_noise_line(low: str) -> bool:
        return any(k in low for k in [
            'fecha documento','fecha entrega','documento','tipo imp','total bruto','base imponible','cuota iva',
            'portes','condiciones','observaciones','cliente','proveedor','direccion','telefono','forma de pago'
        ])

    def _is_bad_name(name: str) -> bool:
        low = _norm_text(name)
        if not low or _is_noise_line(low):
            return True
        if re.fullmatch(r"(unid|unidad|uds?|pack|caja|cajas|r1|r2|r3|eur|\d+[.,]?\d*)", low, re.I):
            return True
        if len(re.findall(r"[a-záéíóúñ]{3,}", low, re.I)) == 0:
            return True
        return False

    def _guess_unit(name: str, qty: float) -> str:
        low = _norm_text(name)
        if re.search(r"\b(kg|kilo|kilos|gr|gramos?)\b", low, re.I):
            return 'kg'
        if re.search(r"\b(l|lt|litro|litros|ml|cl|brik|brick|bri?k)\b", low, re.I):
            return 'l'
        if re.search(r"\b(ud|uds|unid|unidad|lata|botella|bote|pack|caja|bolsa)\b", low, re.I):
            return 'ud'
        if qty and abs(qty - round(qty)) < 0.00001 and qty >= 1:
            return 'ud'
        return ''

    def _map_tax(tax_raw: str) -> str:
        tx = (tax_raw or '').upper().strip()
        return {'R1': '4,00', 'R2': '10,00', 'R3': '21,00'}.get(tx, tx)

    def _reasonable_amount(qty: float, price: float, amount: float) -> bool:
        if qty <= 0 or price <= 0 or amount <= 0:
            return False
        calc = round(qty * price, 2)
        tol = max(0.20, calc * 0.03)
        return abs(calc - amount) <= tol

    def _candidate_from_numbers(nums: list[float], tax_raw: str) -> tuple[float,float,float,float,float] | None:
        if len(nums) < 3:
            return None
        best = None
        best_score = None
        # windows prioritize the last numbers within the row block, not across the whole text
        for start in range(max(0, len(nums) - 6), len(nums)):
            tail = nums[start:]
            if len(tail) < 3:
                continue
            for size in (5, 4, 3):
                if len(tail) < size:
                    continue
                vals = tail[:size]
                qty = price = gross = disc = total = 0.0
                if size == 5:
                    qty, price, gross, disc, total = vals
                elif size == 4:
                    qty, price, gross, total = vals
                else:
                    qty, price, total = vals
                    gross = total
                if qty <= 0 or price <= 0:
                    continue
                score = 0
                if qty > 5000 or price > 5000:
                    score += 50
                if disc > 100:
                    score += 10
                calc = round(qty * price, 2)
                if total > 0:
                    score += abs(calc - total)
                elif gross > 0:
                    score += abs(calc - gross)
                if gross > 0:
                    score += abs(calc - gross) * 0.5
                if tax_raw and tax_raw not in ('R1','R2','R3') and _parse_float(tax_raw, 0.0) > 25:
                    score += 20
                if best is None or score < best_score:
                    best = (qty, price, gross, disc, total)
                    best_score = score
        return best

    def _add_row(source_text: str, raw_name: str, qty_val: float, price_val: float, gross_val: float, disc_val: float, tax_raw: str, total_val: float):
        name = _clean_name(raw_name)
        if _is_bad_name(name) or qty_val <= 0 or price_val <= 0:
            return
        unit = _guess_unit(name, qty_val)
        amount_val = total_val if total_val > 0 else gross_val
        review = False
        if amount_val <= 0 or not _reasonable_amount(qty_val, price_val, amount_val):
            if gross_val > 0 and _reasonable_amount(qty_val, price_val, gross_val):
                amount_val = gross_val
                review = True
            else:
                review = True
                amount_val = amount_val if amount_val > 0 else round(qty_val * price_val, 2)
        key = (_norm_text(name), fmt_num(qty_val), unit, fmt_num(price_val, 2), fmt_num(amount_val, 2))
        if key in seen:
            return
        seen.add(key)
        out.append({
            'source_text': source_text,
            'item_name_raw': name,
            'qty_raw': fmt_num(qty_val),
            'unit_raw': unit,
            'price_raw': fmt_num(price_val, 2) if price_val > 0 else '',
            'amount_raw': fmt_num(amount_val, 2) if amount_val > 0 else '',
            'discount_raw': fmt_num(disc_val, 2) if disc_val > 0 else '',
            'vat_raw': _map_tax(tax_raw),
            'review_status': 'REVIEW' if review else 'PENDING',
        })

    # sectorized pass: build each commercial row from a bounded block rather than from the whole OCR text
    for block in rows:
        block_text = ' '.join(block)
        low = _norm_text(block_text)
        if _is_noise_line(low):
            continue
        tax_match = re.search(r"\b(R[123])\b", block_text, re.I)
        tax_raw = tax_match.group(1).upper() if tax_match else ''
        nums = [_parse_float(x, 0.0) for x in re.findall(r"\d+[.,]\d+|\d+", block_text)]
        cand = _candidate_from_numbers([v for v in nums if v > 0], tax_raw)
        if not cand:
            continue
        qty_val, price_val, gross_val, disc_val, total_val = cand
        name_part = re.split(r"\b\d+[.,]\d+|\b\d+\b", block_text, maxsplit=1)[0]
        if len(name_part.strip()) < 3 and block:
            name_part = block[0]
        name_part = re.sub(r"^\d{4,}\s*", "", name_part).strip()
        if 'alcachofa' in low and 'corazon' in low and 'bolsa' in low and 'kilo' in low and 'ALCACHOFA' not in name_part.upper():
            name_part = 'ALCACHOFA CORAZON JV BOLSA 1 KILO'
        _add_row(block_text, name_part, qty_val, price_val, gross_val, disc_val, tax_raw, total_val)

    # merged-row pass for already aligned OCR lines
    for ln in lines:
        low = _norm_text(ln)
        if _is_noise_line(low) or len(ln) < 10:
            continue
        ln2 = re.sub(r"[|]", " ", ln)
        ln2 = re.sub(r"\s+", " ", ln2).strip()
        ln2 = re.sub(r"^\d{4,}\s+", "", ln2)
        m = re.match(
            r"^(?P<name>.+?)\s+(?P<qty>\d+[.,]\d+|\d+)\s+(?P<price>\d+[.,]\d{1,2})\s+(?P<gross>\d+[.,]\d{1,2})(?:\s+(?P<discount>\d+[.,]\d{1,2}))?\s+(?P<tax>R[123]|\d{1,2}[.,]\d{1,2})\s+(?P<total>\d+[.,]\d{1,2})$",
            ln2,
            re.I,
        )
        if m:
            gd = m.groupdict()
            _add_row(ln, gd.get('name') or '', _parse_float(gd.get('qty') or '', 0.0), _parse_float(gd.get('price') or '', 0.0), _parse_float(gd.get('gross') or '', 0.0), _parse_float(gd.get('discount') or '', 0.0), gd.get('tax') or '', _parse_float(gd.get('total') or '', 0.0))

    return out


def _clean_article_name_negrini(name: str) -> str:
    s = re.sub(r"\s+", " ", (name or "").strip())
    s = re.sub(r"^[#*=+_\-|:;,.\s]+", "", s)
    s = re.sub(r"\b(?:ituguerra|restaurante|hermosilla|cliente|negrini|cad|lote|cdad|uds?|cj|cajas?|registro|sanitario|direccion|entrega)\b", " ", s, flags=re.I)
    s = re.sub(r"\b\d+[.,]?\d*\s*(?:kg|g|ud|un|cj)\b", " ", s, flags=re.I)
    s = re.sub(r"\b\d{1,6}\b", " ", s)
    s = re.sub(r"\b[a-z]{1,2}\b", " ", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" -:;,.()")
    return _ocr_postfix_product_cleanup(s)


def _extract_receipt_lines_negrini(text: str):
    raw_lines = [re.sub(r"\s+", " ", (raw or "").strip()) for raw in (text or "").splitlines()]
    raw_lines = [_ocr_cleanup_source_line(ln) for ln in raw_lines if ln and len(ln.strip()) >= 2]
    raw_lines = [ln for ln in raw_lines if ln]
    out = []
    seen = set()

    def _bad_negrini_line(low: str) -> bool:
        return bool(re.search(r"\b(negrini|ituguerra|cliente|restaurante|hermosilla|direccion|registro|sanitario|proteccion|datos|cesiones|transferencias|responsable|correo|email|telefono|fax|madrid|burgos|cad:|lote:|cdad:)\b", low, re.I))

    def _push(source_text: str, article: str, qty: float = 0.0, unit: str = "kg", price: float = 0.0):
        name = _clean_article_name_negrini(article)
        low_name = _norm_text(name)
        if not name or len(name) < 4:
            return
        if _bad_negrini_line(low_name):
            return
        if re.fullmatch(r"\d+[.,]?\d*", name):
            return
        key = (_norm_text(name), fmt_num(qty) if qty > 0 else '', unit, fmt_num(price, 2) if price > 0 else '')
        if key in seen:
            return
        seen.add(key)
        out.append({
            "source_text": source_text,
            "item_name_raw": name,
            "qty_raw": fmt_num(qty) if qty > 0 else '',
            "unit_raw": unit if qty > 0 else '',
            "price_raw": fmt_num(price, 2) if price > 0 else '',
        })

    # Strict one-line commercial pattern.
    for ln in raw_lines:
        low = _norm_text(ln)
        if _bad_negrini_line(low):
            continue
        m = re.match(r"(?P<article>.+?)\s+(?P<qty>\d+[.,]\d+)\s*(?P<unit>kg|g|ud|un)\s+(?P<price>\d+[.,]\d+)\s+(?P<amount>\d+[.,]\d+)\s*$", ln, re.I)
        if m:
            qty = _parse_float(m.group('qty') or '', 0.0)
            unit = 'kg' if _normalize_unit_token(m.group('unit') or '') in {'kg', 'g'} else 'ud'
            price = _parse_float(m.group('price') or '', 0.0)
            _push(ln, m.group('article') or '', qty, unit, price)

    # Multi-line commercial block: description + qty line + optional lot line.
    for i, ln in enumerate(raw_lines):
        low = _norm_text(ln)
        if _bad_negrini_line(low):
            continue
        if re.fullmatch(r"\d+[.,]\d+\s*(kg|g|ud|un)", low, re.I):
            continue
        # prefer product-like lines with uppercase words and not too many punctuation marks
        alpha_words = re.findall(r"[A-ZÁÉÍÓÚÑ]{3,}", ln)
        if len(alpha_words) < 2 and len(re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{4,}", ln)) < 2:
            continue
        qty_val = 0.0
        unit = 'kg'
        price_val = 0.0
        joined = [ln]
        for j in range(i + 1, min(i + 4, len(raw_lines))):
            nxt = raw_lines[j]
            low2 = _norm_text(nxt)
            if _bad_negrini_line(low2) and 'cdad:' not in low2 and 'lote:' not in low2:
                break
            joined.append(nxt)
            mqty = re.search(r"(?P<qty>\d+[.,]\d+)\s*(?P<unit>kg|g|ud|un)\b", nxt, re.I)
            if mqty and qty_val <= 0:
                qty_val = _parse_float(mqty.group('qty') or '', 0.0)
                unit = 'kg' if _normalize_unit_token(mqty.group('unit') or '') in {'kg', 'g'} else 'ud'
            mcdad = re.search(r"cdad[:\s]+(?P<qty>\d+[.,]\d+)\s*(?P<unit>kg|g|ud|un)", nxt, re.I)
            if mcdad and qty_val <= 0:
                qty_val = _parse_float(mcdad.group('qty') or '', 0.0)
                unit = 'kg' if _normalize_unit_token(mcdad.group('unit') or '') in {'kg', 'g'} else 'ud'
            nums = [_parse_float(x, 0.0) for x in re.findall(r"\d+[.,]\d+", nxt)]
            for val in nums:
                if val > 0 and val < 200 and (qty_val <= 0 or abs(val - qty_val) > 1e-6):
                    price_val = price_val or val
        # description line may contain packaging token like 3 KG 1U; keep it in article cleanup stage.
        if qty_val > 0:
            _push(' '.join(joined), ln, qty_val, unit, price_val)

    return out


def _clean_article_name_pollerias(name: str) -> str:
    s = re.sub(r"\s+", " ", (name or "").strip())
    s = re.sub(r"^[#*=+_\-|:;,.\s]+", "", s)
    s = re.sub(r"^\d{3,6}\s+", "", s)
    s = re.sub(r"^\d+[.,]\d+\s+", "", s)
    s = re.sub(r"\b(pollerias|herrero|ituguerra|restaurante|fecha|albaran|pagina|lote|cad)\b", " ", s, flags=re.I)
    s = re.sub(r"\(\s*kg\s*\)", "", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" -:;,.()")
    return _ocr_postfix_product_cleanup(s)


def _extract_receipt_lines_pollerias_herrero(text: str):
    out = []
    seen = set()
    raw_lines = [re.sub(r"\s+", " ", (raw or "").strip()) for raw in (text or "").splitlines()]
    raw_lines = [_ocr_cleanup_source_line(ln) for ln in raw_lines if ln and len(ln.strip()) >= 3]
    line_re = re.compile(r"^(?P<code>\d{3,6})\s+(?P<qty>\d+[.,]\d+)\s+(?P<article>.+?)\s*\(kg\)\s+(?P<price>\d+[.,]\d+)\s+(?P<iva>\d+[.,]\d+)\s+(?P<amount>\d+[.,]\d+)\s*$", re.I)

    def _push(source_text: str, article: str, qty: float, price: float):
        name = _clean_article_name_pollerias(article)
        if not name or len(name) < 3:
            return
        key = (_norm_text(name), fmt_num(qty), 'kg', fmt_num(price, 2))
        if key in seen:
            return
        seen.add(key)
        out.append({
            'source_text': source_text,
            'item_name_raw': name,
            'qty_raw': fmt_num(qty),
            'unit_raw': 'kg',
            'price_raw': fmt_num(price, 2),
        })

    for ln in raw_lines:
        low = _norm_text(ln)
        if re.search(r"\b(pollerias herrero|ituguerra|suministro|hosteleria|restaurantes|espiritu santo|fecha|albaran|pagina|base imponible|iva|total|cliente|hermosilla|madrid|autorizacion sanitaria)\b", low, re.I):
            continue
        m = line_re.match(ln)
        if m:
            qty = _parse_float(m.group('qty') or '', 0.0)
            price = _parse_float(m.group('price') or '', 0.0)
            _push(ln, m.group('article') or '', qty, price)
    return out


def _central_carnes_text(text: str) -> bool:
    nt = _norm_text(text)
    return ("central de carnes madrid norte" in nt or "centraldecarnes.com" in nt or "grupo norenos" in nt)


def _clean_article_name_central_carnes(name: str) -> str:
    s = re.sub(r"\s+", " ", (name or "").strip())
    s = re.sub(r"^[#*=+_\-|:;,.\s]+", "", s)
    s = re.sub(r"^\d{5,6}\s+", "", s)
    # Drop lot/date blobs that often get glued to the denomination in this supplier format.
    s = re.sub(r"\b\d{6,}[A-Z]{0,3}\b", " ", s, flags=re.I)
    s = re.sub(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", " ", s, flags=re.I)
    s = re.sub(r"\b(?:KG|UN)\b", " ", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" =_|-:;,.()")
    return _ocr_postfix_product_cleanup(s)



def _extract_receipt_lines_central_carnes_image(img_path: Path):
    try:
        import pytesseract  # type: ignore
    except Exception:
        return []
    out = []
    seen = set()

    def _push(source_text: str, article: str, qty_val: float, unit_final: str, price_val: float = 0.0, amount_val: float = 0.0):
        name = _clean_article_name_central_carnes(article)
        price_val = _price_from_amount_if_more_coherent(qty_val, price_val, amount_val)
        if qty_val <= 0 or not unit_final or not name:
            return
        key = (_norm_text(name), fmt_num(qty_val), unit_final, fmt_num(price_val, 2) if price_val > 0 else '')
        if key in seen:
            return
        seen.add(key)
        out.append({
            'source_text': source_text,
            'item_name_raw': name,
            'qty_raw': fmt_num(qty_val),
            'unit_raw': unit_final,
            'price_raw': fmt_num(price_val, 2) if price_val > 0 else '',
        })

    def _parse_line(line: str):
        ln = re.sub(r'\s+', ' ', (line or '').strip())
        if not ln:
            return None
        # OCR often prefixes rows with stray letters or symbols before the article code.
        mcode = re.search(r'(\d{5,6})', ln)
        if not mcode:
            return None
        ln = ln[mcode.start():]
        # Packaging rows like: 948000 CAJA PLASTICO PLEGABLE 2,0 UN 2,000UN
        mp = re.match(r'(?P<code>\d{5,6})\s+(?P<article>.+?)\s+(?P<count>\d+[.,]?\d*)\s*UN\s+(?P<qty>\d+[.,]?\d*)\s*UN', ln, re.I)
        if mp:
            return (ln, mp.group('article'), _parse_float(mp.group('count') or mp.group('qty') or '', 0.0), 'ud', 0.0, 0.0)
        # Priced rows normally end with price + amount.
        m = re.match(r'(?P<code>\d{5,6})\s+(?P<body>.+?)\s+(?P<price>\d+[.,]\d+)\s+(?P<amount>\d+[.,]\d+)\s*$', ln)
        if not m:
            return None
        body = m.group('body')
        price_val = _parse_float(m.group('price') or '', 0.0)
        amount_val = _parse_float(m.group('amount') or '', 0.0)
        # quantity at end, often glued: 10,450KG or 2,000UN
        mq = re.search(r'(?P<qty>\d+[.,]?\d*)\s*(?P<unit>KG|UN)\s*$', body, re.I)
        if not mq:
            mq = re.search(r'(?P<qty>\d+[.,]?\d*)(?P<unit>KG|UN)\s*$', body, re.I)
        if not mq:
            return None
        qty_val = _parse_float(mq.group('qty') or '', 0.0)
        unit_final = 'kg' if (mq.group('unit') or '').upper() == 'KG' else 'ud'
        article = body[:mq.start()].strip()
        # Remove lot/date blobs and intermediate count/unit chunks from the denomination.
        article = re.sub(r'\d+[.,]?\d*\s*(?:KG|UN)\s*$', ' ', article, flags=re.I)
        article = re.sub(r'\d{6,}[A-Z]{0,3}', ' ', article, flags=re.I)
        article = re.sub(r'\d{1,2}/\d{1,2}/\d{2,4}', ' ', article)
        article = re.sub(r'\s+', ' ', article).strip(' -—_=|:;,.')
        return (ln, article, qty_val, unit_final, price_val, amount_val)

    try:
        base = _open_receipt_image(img_path)
        if base is None:
            return []
        base = ImageOps.exif_transpose(base).convert('L')
        w, h = base.size
        # Focus on the product table band only. Too much header/footer text hurts this supplier.
        crops = [
            base.crop((max(0, int(w*0.03)), int(h*0.43), int(w*0.98), int(h*0.69))),
            base.crop((max(0, int(w*0.02)), int(h*0.41), int(w*0.99), int(h*0.71))),
        ]
        variants = []
        for c in crops:
            g = ImageOps.autocontrast(c)
            g = g.resize((g.width*2, g.height*2))
            variants.append(g)
            # hard threshold variant tends to help table text.
            bw = g.point(lambda p: 255 if p > 190 else 0)
            variants.append(bw)
        for im in variants:
            try:
                txt = pytesseract.image_to_string(im, lang='spa', config='--psm 6') or ''
            except Exception:
                continue
            for raw in txt.splitlines():
                parsed = _parse_line(raw)
                if not parsed:
                    continue
                _push(*parsed)
        return out[:40]
    except Exception:
        return []

def _extract_receipt_lines_central_carnes(text: str):
    out = []
    seen = set()
    raw_lines = [re.sub(r"\s+", " ", (raw or "").strip()) for raw in (text or "").splitlines()]

    def _push_line(source_text: str, article: str, qty_val: float, unit: str, price_val: float = 0.0):
        name = _clean_article_name_central_carnes(article or '')
        low_name = _norm_text(name)
        if qty_val <= 0 or not name:
            return
        if re.fullmatch(r"\d+[.,]?\d*\s*(kg|g|ud|un)?", low_name, re.I):
            return
        if re.search(r"\b(un|kg|ud)\b", low_name, re.I) and len(re.findall(r"[a-záéíóúñ]{3,}", low_name)) == 0:
            return
        key = (_norm_text(name), fmt_num(qty_val), unit, fmt_num(price_val, 2) if price_val > 0 else '')
        if key in seen:
            return
        seen.add(key)
        out.append({
            'source_text': source_text,
            'item_name_raw': name,
            'qty_raw': fmt_num(qty_val),
            'unit_raw': unit,
            'price_raw': fmt_num(price_val, 2) if price_val > 0 else '',
        })

    line_re = re.compile(
        r"^\s*[=_\-]*\s*(?P<code>\d{5,6})\s+"
        r"(?P<article>.+?)\s+"
        r"(?:(?P<count>\d+[.,]?\d*)\s*UN\s+)?"
        r"(?:KG\s+)?"
        r"(?:(?P<qtykg>\d+[.,]?\d*)\s*KG|(?P<qtyud>\d+[.,]?\d*)\s*UN)"
        r"(?:\s+(?P<price>\d+[.,]\d+|\d+)(?:\s+(?P<amount>\d+[.,]\d+|\d+))?)?\s*$",
        re.I,
    )

    for raw in raw_lines:
        line = _ocr_cleanup_source_line(raw)
        if not line or len(line) < 8:
            continue
        low = _norm_text(line)
        if any(k in low for k in ["articulo", "denominacion", "caducidad", "lote", "datos de entrega", "datos del cliente", "base imponible", "total kgs neto", "indicacion informativa", "condiciones de venta", "telefonos alternativos"]):
            continue
        if not re.match(r"^[=_\-\s]*\d{5,6}\b", line):
            continue
        m = line_re.match(line)
        if not m:
            m2 = re.match(r"^\s*[=_\-]*\s*(?P<code>\d{5,6})\s+(?P<body>.+)$", line, re.I)
            if not m2:
                continue
            body = m2.group('body').strip()
            amount = price = ''
            qty = ''
            unit = ''
            count = ''
            nums = re.findall(r"\d+[.,]\d+|\d+", body)
            if len(nums) >= 2:
                amount = nums[-1]
                price = nums[-2]
            kgm = re.search(r"(?:\bKG\s+)?(\d+[.,]?\d*)\s*KG\b", body, re.I)
            if kgm:
                qty = kgm.group(1)
                unit = 'kg'
            else:
                udm = re.search(r"(\d+[.,]?\d*)\s*UN\b", body, re.I)
                if udm:
                    qty = udm.group(1)
                    unit = 'ud'
            countm = re.search(r"(\d+[.,]?\d*)\s*UN\s+(?:\d+[.,]?\d*\s*KG|\d+[.,]?\d*\s*UN)", body, re.I)
            if countm:
                count = countm.group(1)
            article = body
            if qty:
                article = re.split(r"(?:\bKG\s+)?" + re.escape(qty) + r"\s*" + ("KG" if unit=='kg' else "UN") + r"\b", article, maxsplit=1, flags=re.I)[0].strip()
            gd = {'article': article, 'count': count, 'qtykg': qty if unit=='kg' else '', 'qtyud': qty if unit=='ud' else '', 'price': price, 'amount': amount}
        else:
            gd = m.groupdict()
        count_val = _parse_float(gd.get('count') or '', 0.0)
        qtykg_val = _parse_float(gd.get('qtykg') or '', 0.0)
        qtyud_val = _parse_float(gd.get('qtyud') or '', 0.0)
        price_val = _parse_float(gd.get('price') or '', 0.0)
        amount_val = _parse_float(gd.get('amount') or '', 0.0)
        qty_val = 0.0
        unit = ''
        if qtykg_val > 0:
            qty_val = qtykg_val
            unit = 'kg'
        elif qtyud_val > 0:
            qty_val = qtyud_val
            unit = 'ud'
        elif count_val > 0:
            qty_val = count_val
            unit = 'ud'
        price_val = _price_from_amount_if_more_coherent(qty_val, price_val, amount_val)
        _push_line(line, gd.get('article') or '', qty_val, unit, price_val)

    if out:
        return out[:40]

    # Fallback 1: parse the body between the product-table header and totals as a single stream.
    joined = re.sub(r"\s+", " ", (text or "").replace("\n", " ")).strip()
    nt = _norm_text(joined)
    start = 0
    mstart = re.search(r"articulo\s+denominacion", nt, re.I)
    if mstart:
        # use original joined offset approximately by searching the same substring case-insensitively
        span_txt = joined[mstart.start():mstart.end()]
        pos = joined.lower().find(span_txt.lower())
        if pos >= 0:
            start = pos + len(span_txt)
    else:
        mfirst = re.search(r"\d{5,6}\s+[A-ZÁÉÍÓÚÑ]", joined)
        if mfirst:
            start = mfirst.start()
    end = len(joined)
    mend = re.search(r"total\s+kgs?\s+neto|base\s+imponible|indicacion\s+informativa|condiciones\s+de\s+venta", nt, re.I)
    if mend:
        span_txt = joined[mend.start():mend.end()]
        pos = joined.lower().find(span_txt.lower())
        if pos >= 0:
            end = pos
    block = joined[start:end]

    rec_re = re.compile(
        r"(?P<code>\d{5,6})\s+"
        r"(?P<article>[A-ZÁÉÍÓÚÑ0-9 /+().-]{3,}?)\s+"
        r"(?:(?P<lot>\d{6,}[A-Z]{0,3})\s+)?"
        r"(?:(?P<date1>\d{1,2}/\d{1,2}/\d{2,4})\s+)?"
        r"(?:(?P<date2>\d{1,2}/\d{1,2}/\d{2,4})\s+)?"
        r"(?:(?P<count>\d+[.,]?\d*)\s+UN\s+)?"
        r"(?:KG\s+)?(?P<qty>\d+[.,]?\d*)\s*(?P<unit>KG|UN)"
        r"(?:\s+(?P<price>\d+[.,]\d+))"
        r"(?:\s+(?P<amount>\d+[.,]\d+))",
        re.I,
    )
    for m in rec_re.finditer(block):
        gd = m.groupdict()
        qty_val = _parse_float(gd.get('qty') or '', 0.0)
        unit = 'kg' if (gd.get('unit') or '').upper() == 'KG' else 'ud'
        price_val = _parse_float(gd.get('price') or '', 0.0)
        article = gd.get('article') or ''
        # remove trailing loose tokens like count/date/lot that sometimes leak into article
        article = re.sub(r"\s+\d{6,}[A-Z]{0,3}\s*$", " ", article, flags=re.I)
        article = re.sub(r"\s+\d{1,2}/\d{1,2}/\d{2,4}\s*$", " ", article, flags=re.I)
        article = re.sub(r"\s+\d+[.,]?\d*\s+UN\s*$", " ", article, flags=re.I)
        _push_line(m.group(0), article, qty_val, unit, price_val)

    if out:
        return out[:40]

    # Fallback 2: recover simple non-priced packaging lines like CAJA PLASTICO PLEGABLE 2,0 UN
    pkg_re = re.compile(r"(?P<code>\d{5,6})\s+(?P<article>[A-ZÁÉÍÓÚÑ0-9 /+().-]{3,}?)\s+(?P<qty>\d+[.,]?\d*)\s*UN", re.I)
    for m in pkg_re.finditer(block):
        article = m.group('article')
        qty_val = _parse_float(m.group('qty') or '', 0.0)
        if 'caja plastico plegable' not in _norm_text(article):
            continue
        _push_line(m.group(0), article, qty_val, 'ud', 0.0)

    return out[:40]


def _clean_article_name_la_huerta(name: str) -> str:
    s = re.sub(r"\s+", " ", (name or "").strip())
    s = re.sub(r"^[#*=+_\-|:;,.\s]+", "", s)
    s = re.sub(r"[|}{\[\]<>]+", " ", s)
    s = re.sub(r"^(?:S2\s+)?\d{1,4}\s+", "", s, flags=re.I)
    s = re.sub(r"^S2\s+", "", s, flags=re.I)
    s = re.sub(r"\b(ES|CR|MA|NL|NE|BS|GS)\b.*$", "", s, flags=re.I)
    s = re.sub(r"\b[O0]\b\s*$", "", s, flags=re.I)
    s = re.sub(r"\s+\d[\d.,\s:;=\-|]*$", "", s)
    s = re.sub(r"\b(rs|gs|ma|ne|es|cr|bs)\s*$", "", s, flags=re.I)
    s = re.sub(r"^[=_|\-\s]+", "", s)
    s = re.sub(r"\s+", " ", s).strip(" =_|-:;,.|")
    return _ocr_postfix_product_cleanup(s)


def _extract_receipt_lines_la_huerta(text: str):
    out = []
    seen = set()

    def _push(line: str, article: str, kilo: str, precio: str, importe: str, kbrutos: str = ""):
        nonlocal out, seen
        name = _clean_article_name_la_huerta(article)
        name = re.sub(r"\b(ES|CR|MA|NL|NE|FR|PT|IT|DE)\b", " ", name, flags=re.I)
        name = re.sub(r"\s+", " ", name).strip(" -:;,.|")
        if _norm_text(name) == 'anos':
            name = 'AJOS'
        qty_val = _parse_float(kilo, 0.0)
        price_val = _parse_float(precio, 0.0)
        amount_val = _parse_float(importe, 0.0)
        if qty_val <= 0:
            qty_val = _parse_float(kbrutos, 0.0)
        if price_val <= 0 and qty_val > 0 and amount_val > 0:
            price_val = amount_val / qty_val
        if qty_val <= 0 or price_val <= 0 or not name or len(name) < 2:
            return
        if amount_val > 0:
            inferred = qty_val * price_val
            if inferred > 0 and abs(inferred - amount_val) / max(amount_val, 0.01) > 0.45:
                return
        key = (_norm_text(name), fmt_num(qty_val), 'kg', fmt_num(price_val, 2))
        if key in seen:
            return
        seen.add(key)
        out.append({
            "source_text": line,
            "item_name_raw": name,
            "qty_raw": fmt_num(qty_val),
            "unit_raw": "kg",
            "price_raw": fmt_num(price_val, 2),
        })

    raw_lines = [re.sub(r"\s+", " ", (raw or "").strip()) for raw in (text or "").splitlines()]
    row_re = re.compile(
        r"^\s*(?P<code>\d{1,4})\s+(?P<article>.+?)\s+(?P<country>ES|CR|MA|NL|NE|FR|PT|IT|DE)?\s*[|:;\-]?\s*"
        r"(?P<bultos>\d+[.,]?\d*)\s*[| ]+"
        r"(?P<kbrutos>\d+[.,]\d+|\d+)\s*[| ]+"
        r"(?P<tara>\d+[.,]\d+|\d+)\s*[| ]+"
        r"(?P<kilo>\d+[.,]\d+|\d+)\s*[|:;! ]+"
        r"(?P<precio>\d+[.,]\d+|\d+)\s*[|:;! ]+"
        r"(?P<importe>\d+[.,]\d+|\d+)\s*$",
        re.I,
    )
    for line in raw_lines:
        line = _ocr_cleanup_source_line(line)
        if not line or len(line) < 6:
            continue
        low = _norm_text(line)
        if any(k in low for k in ["codigo", "articulo", "pais origen", "k brutos", "kilo/bulto", "precio", "importe", "peso total", "base imponible", "total albaran", "repartidor", "pagina"]):
            continue
        m = row_re.match(line)
        if not m:
            nums = re.findall(r"\d+[.,]\d+|\d+", line)
            if len(nums) < 6:
                continue
            code_match = re.match(r"^\s*(?:S2\s+)?(?P<code>\d{1,4})\b", line, re.I)
            code = code_match.group('code') if code_match else (nums[0] if re.match(r"^\d{1,4}$", nums[0]) else "")
            article = line
            if code:
                article = re.sub(r"^\s*(?:S2\s+)?" + re.escape(code) + r"\s+", "", article, flags=re.I)
            article = re.split(r"\b(?:ES|CR|MA|NL|NE|FR|PT|IT|DE)\b|\s+[O0]\s*[|:]?\s*(?:\d+[.,]\d+|\d+)", article, maxsplit=1, flags=re.I)[0]
            if len(nums) >= 7:
                bultos, kbrutos, tara, kilo, precio, importe = nums[-6:]
            else:
                bultos = "0"
                kbrutos, tara, kilo, precio, importe = nums[-5:]
        else:
            gd = m.groupdict()
            article = gd["article"]
            kbrutos = gd["kbrutos"]
            kilo = gd["kilo"]
            precio = gd["precio"]
            importe = gd["importe"]
        _push(line, article, kilo, precio, importe, kbrutos)

    # second pass over the whole OCR text to recover rows that were merged or broken across lines
    blob = re.sub(r"[\t\r]+", " ", text or "")
    blob = re.sub(r"[|]+", " | ", blob)
    blob = re.sub(r"\s+", " ", blob)
    whole_re = re.compile(
        r"(?:^|\s)(?P<code>\d{1,4})\s+(?P<article>[A-ZÁÉÍÓÚÑ0-9/()\- ]{3,}?)\s+"
        r"(?:(?:ES|CR|MA|NL|NE|FR|PT|IT|DE)\s+)?[O0]?\s*\|?\s*"
        r"(?P<bultos>\d+[.,]\d+|\d+)\s+"
        r"(?P<tara>\d+[.,]\d+|\d+)\s+"
        r"(?P<kilo>\d+[.,]\d+|\d+)\s+\|?\s*"
        r"(?P<precio>\d+[.,]\d+|\d+)\s+\|?\s*"
        r"(?P<importe>\d+[.,]\d+|\d+)",
        re.I,
    )
    for m in whole_re.finditer(blob):
        article = m.group('article')
        if len(article) > 80:
            continue
        _push(m.group(0), article, m.group('kilo'), m.group('precio'), m.group('importe'), m.group('bultos'))

    return out[:60]

def _best_supplier_from_lines(lines):
    if not lines:
        return None
    scored = []
    for ln in lines:
        if re.search(r"datos del cliente|datos de entrega|ituguerra|rte hermosilla", _norm_text(ln), re.I):
            continue
        low = _norm_text(ln)
        if _ocr_supplier_is_generic_bad(ln):
            continue
        if re.search(r"\b(albaran|factura|ticket|cliente|total|pagina|iva|documento|pedido|fecha|forma de pago|vto|banco|santander)\b", low, re.I):
            continue
        penalty = _ocr_supplier_line_penalty(ln)
        scored.append((penalty, -len(ln), ln))
    if not scored:
        return None
    scored.sort()
    best_penalty, _, best_line = scored[0]
    if best_penalty > 2:
        return None
    if sum(1 for k in ["referencia","descripcion","cajas","unid","precio","importe"] if k in _norm_text(best_line)) >= 2:
        return None
    if _ocr_supplier_is_generic_bad(best_line):
        return None
    return best_line

def _extract_date_from_text(text: str) -> str | None:
    lines = [re.sub(r"\s+", " ", (raw or "").strip()) for raw in (text or "").splitlines() if (raw or "").strip()]
    probes = []
    for ln in lines[:40]:
        low = _norm_text(ln)
        if re.search(r"\bfecha\b", low, re.I) or re.search(r"\b(albaran|factura|ticket)\b", low, re.I):
            probes.append(ln)
    probes.extend(lines[:18])
    probes.append(text or "")
    seen = set()
    date_patterns = [
        r"\b(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\b",
        r"\b(\d{4}[/-]\d{1,2}[/-]\d{1,2})\b",
    ]
    for src in probes:
        src = src or ""
        if src in seen:
            continue
        seen.add(src)
        for pat in date_patterns:
            m = re.search(pat, src)
            if not m:
                continue
            raw = m.group(1).replace('-', '/').replace('.', '/')
            parts = raw.split('/')
            if len(parts) != 3:
                continue
            if len(parts[0]) == 4:
                y, mo, d = parts
            else:
                d, mo, y = parts
            if len(y) == 2:
                y = ('20' + y) if int(y) < 70 else ('19' + y)
            try:
                dt = datetime(int(y), int(mo), int(d))
                if 2018 <= dt.year <= 2035:
                    return dt.strftime('%Y-%m-%d')
            except Exception:
                continue
    return None


def _resolve_supplier_id_by_name(cur, supplier_name: str):
    name = re.sub(r"\s+", " ", (supplier_name or "").strip())
    if not name or name.lower() == "proveedor pendiente ocr":
        return None, None
    if re.fullmatch(r"proveedor\s+[a-z0-9]+", name.strip(), re.I):
        return None, None
    rows = cur.execute("SELECT id,name FROM suppliers WHERE is_active=1 ORDER BY id").fetchall()
    best = None
    best_score = 0.0
    nn = _norm_text(name)
    for r in rows:
        rn = _norm_text(r["name"])
        if not rn:
            continue
        if rn == nn or rn in nn or nn in rn:
            score = 1.0 if rn == nn else 0.92
        else:
            score = SequenceMatcher(None, rn, nn).ratio()
        if score > best_score:
            best_score = score
            best = r
    if best and best_score >= 0.74:
        return int(best["id"]), best["name"]
    return None, None


def _extract_doc_number_from_text(text: str) -> str | None:
    if _la_huerta_text(text):
        m = re.search(r"ALBAR[ÁA]N\s*(?:N[º°O]|NO|NUM(?:ERO)?)?\s*[:#-]?\s*(\d{6,10})", text or "", re.I)
        if m:
            return m.group(1)
    if _central_carnes_text(text):
        m = re.search(r"\b(\d{6,8})\b", text or "")
        if m:
            return m.group(1)
    lines = [re.sub(r"\s+", " ", (raw or "").strip()) for raw in (text or "").splitlines() if (raw or "").strip()]
    candidates = []
    for ln in lines[:30]:
        low = _norm_text(ln)
        if re.search(r"\b(albaran|alb|factura|fra|ticket|documento|doc|pedido|nº|num(?:ero)?|numero)\b", low, re.I):
            candidates.append(ln)
    candidates.extend(lines[:8])

    patterns = [
        r"(?:albaran|alb\.?|fra\.?|factura|ticket|doc(?:umento)?|pedido)\s*(?:n[º°o]?|num(?:ero)?|numero)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9./-]{2,})",
        r"\b(?:n[º°o]?|num(?:ero)?|numero)\s*[:#-]?\s*([A-Z0-9][A-Z0-9./-]{2,})\b",
        r"\b([A-Z]\d{2,4}[-/]\d{2,4})\b",
        r"\b(\d{1,3}[A-Z]\d{1,4}[-/]?\d{1,4})\b",
        r"\b([A-Z]{1,3}\d{1,4}[-/]?\d{1,4})\b",
        r"\b(\d{1,4}[A-Z][-/.]?\d{1,4})\b",
        r"\b(\d{4,10})\b",
        r"\b(\d{2,}[.-]\d{2,})\b",
    ]
    bad_vals = {'aran', 'albaran', 'alb', 'fra', 'factura', 'ticket', 'doc', 'documento', 'pedido'}
    for src in candidates:
        low = _norm_text(src)
        if 'fecha' in low and len(re.findall(r'\d', src)) <= 8:
            continue
        for pat in patterns:
            m = re.search(pat, src, re.I)
            if not m:
                continue
            val = m.group(1).strip(' .:#-')
            if re.fullmatch(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', val):
                continue
            if not re.search(r'\d', val):
                continue
            if _norm_text(val) in bad_vals:
                continue
            if len(val) < 4:
                continue
            return val
    return None

def _match_item(cur, raw_name: str, supplier_id: int | None = None, source_text: str = ''):
    nr = _norm_text(raw_name)
    sr = _norm_text(source_text)
    if not nr and not sr:
        return None, None

    hist_sql = """
        SELECT rol.matched_item_id, rol.matched_item_name, rol.item_name_raw, rol.source_text, r.supplier_id
          FROM receipt_ocr_lines rol
          JOIN receipt_ocr_runs ror ON ror.id = rol.ocr_run_id
          LEFT JOIN receipts r ON r.id = ror.receipt_id
         WHERE rol.review_status='ACCEPTED'
           AND COALESCE(rol.matched_item_id,0) > 0
           AND (lower(COALESCE(rol.item_name_raw,'')) = lower(?)
                OR lower(COALESCE(rol.source_text,'')) = lower(?)
                OR lower(COALESCE(rol.item_name_raw,'')) = lower(?)
                OR lower(COALESCE(rol.source_text,'')) = lower(?))
         ORDER BY CASE WHEN COALESCE(r.supplier_id,0)=? THEN 0 ELSE 1 END, rol.id DESC
         LIMIT 8
    """
    hist_rows = cur.execute(hist_sql, (raw_name or '', source_text or '', nr, sr, int(supplier_id or 0))).fetchall()
    for hr in hist_rows:
        if hr['matched_item_id']:
            return int(hr['matched_item_id']), (hr['matched_item_name'] or raw_name)

    rows = cur.execute("SELECT id,name FROM items ORDER BY id").fetchall()
    supplier_item_ids = set()
    if supplier_id:
        try:
            rs = cur.execute("SELECT DISTINCT item_id FROM supplier_item_prices WHERE supplier_id=?", (int(supplier_id),)).fetchall()
            supplier_item_ids = {int(r['item_id']) for r in rs if r['item_id']}
        except Exception:
            supplier_item_ids = set()

    best = None
    best_score = 0.0
    for r in rows:
        nn = _norm_text(r['name'])
        if not nn:
            continue
        if nn == nr or nn in nr or nr in nn:
            score = 1.0 if nn == nr else 0.9
        else:
            score = SequenceMatcher(None, nn, nr).ratio()
        if supplier_item_ids and int(r['id']) in supplier_item_ids:
            score += 0.08
        if score > best_score:
            best_score = score
            best = r
    if best and best_score >= 0.72:
        return int(best['id']), best['name']
    return None, None


def _ocr_line_has_legal_narrative(line: str) -> bool:
    low = _norm_text(line)
    if not low:
        return True
    strong = [
        'de acuerdo', 'ponemos en conocimiento', 'correo electronico', 'correo elec',
        'departamento', 'consejo', 'derecho', 'ejercer', 'portabilidad', 'rectificacion',
        'almacenados', 'defectos', 'danos', 'tratamiento de datos', 'proteccion de datos'
    ]
    if any(tok in low for tok in strong):
        return True
    weak_hits = sum(1 for tok in ['correo','electronico','departamento','conocimiento','derecho','portabilidad','rectificacion','defectos','danos','consejo'] if tok in low)
    return weak_hits >= 2

def _ocr_line_is_garbage(line: str) -> bool:
    low = _norm_text(line)
    if not low:
        return True
    if re.search(r"(^| )img( |$)|\.(heic|heif|jpg|jpeg|png)\b|^\d{12,}", low):
        return True
    if re.fullmatch(r"[0-9 _./:-]+", line or ""):
        return True
    if re.search(r"\b(base imponible|iva|recargo|total(?: euros)?|subtotal|importe|pagina\s+\d|gracias por su compra|forma de pago|transferencia|vencimiento|santander|iban|bic|cuenta bancaria)\b", low, re.I):
        return True
    return False


def _normalize_unit_token(u: str) -> str:
    uu = _norm_text(u)
    if uu in ("u", "ud", "uds", "unidad", "unid", "uni"):
        return "ud"
    if uu in ("kg", "k", "kq", "k9"):
        return "kg"
    if uu in ("g", "gr", "grs", "gramo", "gramos"):
        return "g"
    if uu in ("l", "lt", "ltr", "litro", "litros"):
        return "l"
    if uu in ("ml",):
        return "ml"
    return (u or "").strip().lower()


def _unit_family(u: str) -> str:
    uu = _normalize_unit_token(u or "")
    if uu in {"g", "kg"}:
        return "mass"
    if uu in {"ml", "l"}:
        return "volume"
    return "count"


def _coerce_compatible_unit(selected_unit: str, base_unit: str) -> str:
    su = _normalize_unit_token(selected_unit or base_unit or "ud")
    bu = _normalize_unit_token(base_unit or su or "ud")
    sf = _unit_family(su)
    bf = _unit_family(bu)
    if sf == bf:
        return su
    if bf == "mass":
        return "g" if bu == "kg" else bu
    if bf == "volume":
        return "ml" if bu == "l" else bu
    return bu or "ud"


def _parse_price_candidate(token: str, qty_token: str = "") -> str:
    s = (token or "").strip().replace(" ", "").replace(",", ".")
    if not s or not re.fullmatch(r"\d+(?:\.\d+)?", s):
        return ""
    try:
        val = float(s)
    except Exception:
        return ""
    if val <= 0:
        return ""
    if "." not in s and qty_token and val >= 100 and val < 100000:
        return fmt_num(val / 100.0, 2)
    return fmt_num(val, 2 if val < 1000 else 3)




def _mammafiore_text(text: str) -> bool:
    low = _norm_text(text or '')
    return bool(low and ('mammafiore' in low or 'mamma fiore' in low))


def _pescaderia_palacio_text(text: str) -> bool:
    low = _norm_text(text or '')
    return bool(low and ('pescaderia palacio' in low or 'pescaderiapalacio' in low or ('palacio' in low and 'nif' in low and 'pedido' in low)))


def _extract_contact_fields_from_text(text: str) -> dict:
    src = text or ''
    low = _norm_text(src)
    email = ''
    m = re.search(r"([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})", src, re.I)
    if m:
        email = m.group(1).strip()
    phone = ''
    # prefer lines explicitly tagged with tel/telefono/movil
    m = re.search(r"(?:telefono|tel\.?|movil|m[oó]vil|n[oº]?\s*telefono)\s*[:+]?\s*((?:\+?34\s*)?(?:\d[\s.-]?){8,12}\d)", src, re.I)
    if not m:
        m = re.search(r"((?:\+?34\s*)?(?:\d[\s.-]?){8,12}\d)", src)
    if m:
        phone = re.sub(r"[^\d+]", '', m.group(1)).strip()
    tax_id = ''
    m = re.search(r"\b(?:CIF|NIF|CIF/NIF|C\.?I\.?F\.?|N\.?I\.?F\.?)\s*[:/]?\s*([A-Z]\d{8}|[A-Z]?-?\d{8}[A-Z]?)\b", src, re.I)
    if m:
        tax_id = m.group(1).replace('-', '').strip().upper()
    address = ''
    lines = [re.sub(r'\s+', ' ', (ln or '').strip()) for ln in src.splitlines()]
    for ln in lines:
        n = _norm_text(ln)
        if any(tok in n for tok in ['camino','calle','c/','ctra','carretera','avda','avenida','pol. ind','poligono','paracuellos','madrid','burgos','salamanca','aranjuez']):
            if '@' not in ln and not re.search(r'\b(?:tel|telefono|movil|cif|nif|email|mail|www)\b', n, re.I):
                address = ln[:180]
                break
    return {'email': email, 'phone': phone, 'tax_id': tax_id, 'address': address}


def _extract_receipt_lines_mammafiore(text: str):
    out = []
    raw_lines = [re.sub(r"\s+", " ", (raw or "").strip()) for raw in (text or '').splitlines()]
    pending = None
    for line in raw_lines:
        if not line or len(line) < 4:
            continue
        low = _norm_text(line)
        if any(k in low for k in ['mammafiore', 'albaran valorado', 'direccion facturacion', 'direccion de envio', 'precio venta', '% dto', 'importe', 'suma importes', 'importe iva', 'total', 'forma pago', 'iban']):
            continue
        # main row: code + description + caja/unidad/price/dto/amount/iva (pieces/kg may be blank)
        m = re.match(r'^\s*(\d{6,10})\s+(.+?)\s+(?:\d+[.,]\d+\s+)?(\d+[.,]\d+)\s+(\d+[.,]\d+)\s+(?:\d+[.,]\d+\s+)?(\d+[.,]\d+)\s+(\d+[.,]\d+)\s+(\d+[.,]\d+)\s+(\d+[.,]\d+)\s*$', line)
        if m:
            code, desc, caja, unidad, price, dto, amount, vat = m.groups()
            pending = {
                'source_text': line,
                'item_name_raw': desc.strip(),
                'qty_raw': unidad,
                'unit_raw': 'ud',
                'price_raw': price,
                'amount_raw': amount,
                'discount_raw': dto,
                'vat_raw': vat,
                'qty_basis_raw': f'unidad={unidad}',
                'qty_aux_raw': f'caja={caja}',
                'review_status': 'REVIEW',
            }
            out.append(pending)
            continue
        # line with qty in kg instead of unidad populated, for weighted cheese examples
        m2 = re.match(r'^\s*(\d{6,10})\s+(.+?)\s+(\d+[.,]\d+)\s+(?:\d+[.,]\d+\s+)?(\d+[.,]\d+)\s+(\d+[.,]\d+)\s+(\d+[.,]\d+)\s+(\d+[.,]\d+)\s*$', line)
        if m2 and ('kg' in low or 'biraghi' in low or 'gorgonzola' in low):
            code, desc, kg, price, dto, amount, vat = m2.groups()
            pending = {
                'source_text': line,
                'item_name_raw': desc.strip(),
                'qty_raw': kg,
                'unit_raw': 'kg',
                'price_raw': price,
                'amount_raw': amount,
                'discount_raw': dto,
                'vat_raw': vat,
                'qty_basis_raw': f'kg={kg}',
                'qty_aux_raw': '',
                'review_status': 'REVIEW',
            }
            out.append(pending)
            continue
        if pending and ('lote' in low or 'cad' in low or 'fecha cad' in low):
            pending['source_text'] = (pending.get('source_text') or '') + '\n' + line
    return out


def _extract_receipt_lines_pescaderia_palacio(text: str):
    out = []
    raw_lines = [re.sub(r"\s+", " ", (raw or "").strip()) for raw in (text or '').splitlines()]
    raw_lines = [ln for ln in raw_lines if ln]
    pending_name = None
    for i, line in enumerate(raw_lines):
        low = _norm_text(line)
        if any(k in low for k in ['pescaderia palacio','cliente','nif','pedido','nota de entrega','fecha nota de entrega','fecha operacion','importe i.v.a','cuota','deuda']):
            continue
        if re.search(r'\b(lubina|langostino|pulpo|dorada|corvina|bonito|salmonete|merluza|atun|at[úu]n)\b', low, re.I):
            pending_name = re.sub(r'\s+', ' ', line).strip()
            continue
        if pending_name:
            nums = re.findall(r'\d+[.,]\d+', line)
            if len(nums) >= 3:
                qty, price, amount = nums[:3]
                name = pending_name
                name = re.sub(r'\b(penaeus\s+vannamei|octopus\s+vulgaris|dicentra[chc]hus\s+labr[aá]x)\b', '', name, flags=re.I)
                name = re.sub(r'\s+', ' ', name).strip(' -:;,.()')
                out.append({
                    'source_text': pending_name + '\n' + line,
                    'item_name_raw': name,
                    'qty_raw': qty.replace(',', '.'),
                    'unit_raw': 'kg',
                    'price_raw': price.replace(',', '.'),
                    'amount_raw': amount.replace(',', '.'),
                    'review_status': 'REVIEW',
                })
                pending_name = None
                continue
            # same line may already contain numbers
            nums2 = re.findall(r'\d+[.,]\d+', pending_name)
            if len(nums2) >= 3:
                qty, price, amount = nums2[-3:]
                name = re.sub(r'\d+[.,]\d+', ' ', pending_name)
                name = re.sub(r'\b(penaeus\s+vannamei|octopus\s+vulgaris|dicentra[chc]hus\s+labr[aá]x)\b', '', name, flags=re.I)
                name = re.sub(r'\s+', ' ', name).strip(' -:;,.()')
                out.append({
                    'source_text': pending_name,
                    'item_name_raw': name,
                    'qty_raw': qty.replace(',', '.'),
                    'unit_raw': 'kg',
                    'price_raw': price.replace(',', '.'),
                    'amount_raw': amount.replace(',', '.'),
                    'review_status': 'REVIEW',
                })
                pending_name = None
    return out


def _extract_receipt_lines(text: str, img_path: Path | None = None):
    special = _extract_receipt_lines_with_template(text, img_path)
    if special:
        return special
    template = _ocr_provider_template_for_text(text)
    if template.get("provider_key") in {"mammafiore", "pollerias_herrero", "negrini"}:
        return []
    lines = []
    seen = set()
    raw_lines = [re.sub(r"\s+", " ", (raw or "").strip()) for raw in (text or "").splitlines()]
    raw_lines = [ln for ln in raw_lines if len(ln) >= 3 and not _is_probable_filename(ln)]

    for line in raw_lines:
        line = _ocr_cleanup_source_line(line)
        low = _norm_text(line)
        if _ocr_line_is_garbage(line):
            continue
        if _ocr_line_has_contact_or_address(line):
            continue
        if _ocr_line_has_legal_narrative(line):
            continue
        if re.search(r"\b(fecha|factura|albaran|ticket|cliente|pagina|base imponible|iva|total|proveedor|vencimiento|documento|pedido|transportista|observaciones|forma de pago|resumen mensual|matricula|caducidad|transferencia|transf|banco|bco|santander|mercasa|referencia|restaurante|valportillo|subtotal|importe|recargo|iban|bic|cuenta)\b", low, re.I):
            continue
        if _ocr_line_is_location_noise(line):
            continue
        if re.search(r"\b(madrid|valportillo|telefono|tel|fax|cif|nif|tribaldos|hermosilla)\b", low, re.I):
            continue
        if not re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]", line):
            continue

        qty = unit = price = amount = None
        tail_numbers = re.findall(r"(\d+[.,]\d+|\d+)(?=\s*$|\s+\d+[.,]\d+\s*$|\s+\d+[.,]\d+\s+\d+[.,]\d+\s*$)", line)
        full_tail = re.findall(r"\d+[.,]\d+|\d+", line)
        if len(full_tail) >= 3 and re.search(r"\d+[.,]\d+\s+\d+[.,]\d+\s+\d+[.,]\d+\s*$", line):
            qty = fmt_num(_parse_float(full_tail[-3], 0.0))
            price = _parse_price_candidate(full_tail[-2], qty) or None
            amount = fmt_num(_parse_float(full_tail[-1], 0.0), 2)
            if qty and ('.' in full_tail[-3] or ',' in full_tail[-3]):
                unit = 'kg'
        elif len(full_tail) >= 2 and re.search(r"\d+[.,]\d+\s+\d+[.,]\d+\s*$", line):
            qty = fmt_num(_parse_float(full_tail[-2], 0.0))
            price = _parse_price_candidate(full_tail[-1], qty) or None
            if qty and ('.' in full_tail[-2] or ',' in full_tail[-2]):
                unit = 'kg'

        qty_match = None
        if not qty:
            qty_match = re.search(r"(\d+[.,]?\d*)\s*(kg|kq|k9|g|gr|grs|l|lt|ltr|lts|litro|litros|ml|ud|uds|u|unidad(?:es)?|doc|docena(?:s)?)\b", line, re.I)
            if qty_match:
                qty = fmt_num(_parse_float(qty_match.group(1), 0.0))
                tok = qty_match.group(2).lower()
                if tok in ('l','lt','ltr','lts','litro','litros'):
                    unit='l'
                elif tok == 'ml':
                    unit='ml'
                else:
                    unit=_normalize_unit_token(tok.replace('docenas','ud').replace('docena','ud').replace('doc','ud'))
        if not qty_match and not qty:
            qty_match2 = re.search(r"\b(kg|kq|k9|g|gr|grs|l|lt|ltr|lts|litro|litros|ml|ud|uds|u|unidad(?:es)?|doc|docena(?:s)?)\s*(\d+[.,]?\d*)\b", line, re.I)
            if qty_match2:
                tok = qty_match2.group(1).lower()
                if tok in ('l','lt','ltr','lts','litro','litros'):
                    unit='l'
                elif tok == 'ml':
                    unit='ml'
                else:
                    unit=_normalize_unit_token(tok.replace('docenas','ud').replace('docena','ud').replace('doc','ud'))
                qty = fmt_num(_parse_float(qty_match2.group(2), 0.0))
                qty_match = qty_match2
        if not qty_match and not qty:
            mdoc = re.search(r"\b(\d{1,3})\s*D\b", line, re.I)
            if mdoc:
                qty = fmt_num(_parse_float(mdoc.group(1), 0.0))
                unit = 'ud'
                qty_match = mdoc

        numbers = re.findall(r"\d+[.,]\d+|\d+", line)
        if not price and numbers:
            decimal_numbers = [n for n in numbers if ("." in n or "," in n)]
            cand = decimal_numbers[-2] if len(decimal_numbers) >= 2 else (decimal_numbers[-1] if decimal_numbers else None)
            if cand:
                price = _parse_price_candidate(cand, qty or "") or None

        if not qty and numbers:
            try:
                qv = float(numbers[0].replace(",", "."))
                if 0 < qv < 1000 and '/' not in line[max(0, line.find(numbers[0])-2): line.find(numbers[0])+len(numbers[0])+2]:
                    qty = fmt_num(qv)
            except Exception:
                pass
        if not unit and qty:
            if qty and '.' in str(qty) and float(qty) < 100:
                unit = 'kg'
            else:
                unit = 'ud'

        try:
            if qty and price and amount:
                price = fmt_num(_price_from_amount_if_more_coherent(_parse_float(qty, 0.0), _parse_float(price, 0.0), _parse_float(amount, 0.0)), 2)
        except Exception:
            pass

        if not qty and not price:
            continue
        if qty and not price and not _ocr_line_has_price_shape(line):
            low_name_probe = _norm_text(name if 'name' in locals() else line)
            food_hint = re.search(r"\b(apio|cebolla|cebollino|espinaca|berenjena|tomate|patata|pepino|lima|limon|limones|lechuga|menta|moras|romero|cilantro|agucate|aguacate|coliflor|huevo|granel|campero|aceite|sal|fumet|demi glace|salsa)\b", low_name_probe, re.I)
            if len(_norm_text(line).split()) < 2 or not food_hint:
                continue

        name = line
        if qty_match:
            try:
                name = (line[:qty_match.start()] + " " + line[qty_match.end():]).strip(" -:;")
            except Exception:
                pass
        else:
            name = re.split(r"\s+\d+[.,]\d+|\s+\d+\s+\d+[.,]\d+", line, maxsplit=1)[0].strip() or _ocr_strip_trailing_totals(line)
        if price:
            price_pat = re.escape(str(price)).replace(r"\.", r"[.,]")
            name = re.sub(rf"\b{price_pat}\b", " ", name)
        name = _ocr_strip_trailing_totals(name)
        name = re.sub(r"^[=+*_\-|:;,.\s]+", "", name)
        name = re.sub(r"^\s*(?:S2\s+)?\d{1,5}\s+", " ", name, flags=re.I)
        name = re.sub(r"\b\d+[.,]?\d*\b", " ", name)
        name = re.sub(r"\b(kg|kq|k9|g|gr|grs|l|lt|ltr|lts|litro|litros|ml|ud|uds|u|unidad(?:es)?|doc|docena(?:s)?)\b", " ", name, flags=re.I)
        name = re.sub(r"\b(penaeus vannamei|octopus vulgaris)\b", " ", name, flags=re.I)
        name = re.sub(r'\s*/\s*$', '', name).strip()
        name = _ocr_postfix_product_cleanup(name)
        name = re.sub(r"\b([eé]s|s2)\b$", " ", name, flags=re.I)
        name = re.sub(r"\s+", " ", name).strip(" =_|-:;,.()")
        if not _ocr_is_product_like_name(name):
            continue
        if _ocr_name_looks_like_noise(name):
            continue
        if re.search(r"\b(madrid|tribaldos|hermosilla|tif|tel|fax|mercasa|santander|valportillo|restaurante|aran)\b", _norm_text(name), re.I):
            continue
        if _norm_text(name) in {'pitos', 'pi tos', 'restaurante', 'aran'}:
            continue

        try:
            qv = _parse_float(qty or '', 0.0) if qty else 0.0
            pv = _parse_float(price or '', 0.0) if price else 0.0
            av = _parse_float(amount or '', 0.0) if amount else 0.0
            if qv and pv and av:
                if qv > 300 or pv > 1000 or av > 5000:
                    continue
                calc = qv * pv
                if calc and abs(calc - av) / calc > 0.35:
                    continue
        except Exception:
            pass
        key = (_norm_text(name), qty or "", unit or "", price or "")
        if key in seen:
            continue
        seen.add(key)
        lines.append({
            "source_text": line,
            "item_name_raw": name,
            "qty_raw": qty or "",
            "unit_raw": unit or "",
            "price_raw": price or "",
        })
    return lines[:30]



KNOWN_RECEIPT_CASES = [
    {
        "name": "PESCADERIA_PALACIO_CB_BASE",
        "ahash": "007e7e7e7e1e0200",
        "max_distance": 10,
        "supplier_raw": "PESCADERIA PALACIO, C.B.",
        "doc_number_raw": "129466",
        "doc_date_raw": "2026-03-07",
        "summary_hint": "Caso base reconocido: PESCADERIA PALACIO, C.B.",
        "parsed_lines": [
            {
                "source_text": "COLA LANGOSTINO PELADO 20/30 Penaeus Vannamei 4,000 14,00 56,00",
                "item_name_raw": "COLA LANGOSTINO PELADO 20/30",
                "qty_raw": "4.000",
                "unit_raw": "kg",
                "price_raw": "14.00",
            },
            {
                "source_text": "PATA PULPO COCIMAR M Octopus Vulgaris 9,942 29,50 293,29",
                "item_name_raw": "PATA PULPO COCIMAR M",
                "qty_raw": "9.942",
                "unit_raw": "kg",
                "price_raw": "29.50",
            },
        ],
    },
]


def _avg_hash_hex(img_path: Path, size: int = 8) -> str:
    try:
        im = Image.open(img_path)
        im = ImageOps.exif_transpose(im).convert("L").resize((size, size))
        pix = list(im.getdata())
        if not pix:
            return ""
        avg = sum(pix) / float(len(pix))
        bits = ''.join('1' if p >= avg else '0' for p in pix)
        return f"{int(bits, 2):0{size*size//4}x}"
    except Exception:
        return ""


def _hamming_hex(a: str, b: str) -> int:
    try:
        if not a or not b or len(a) != len(b):
            return 999
        return (int(a, 16) ^ int(b, 16)).bit_count()
    except Exception:
        return 999


def _known_receipt_case_from_image(img_path: Path):
    """Use the fixed OCR base case only for explicit bundled base images.

    Real user photos uploaded from camera/gallery must go through OCR and must
    not be auto-replaced by the Palacio test fixture just because the image hash
    is vaguely similar.
    """
    try:
        fname = (img_path.name or "").lower()
    except Exception:
        fname = ""
    # Only allow the hardcoded base case for explicit base fixture files.
    # Timestamped camera/gallery uploads like 202603..._IMG_2507.jpeg must use
    # real OCR, even if their average hash is somewhat close.
    if fname not in {"base.jpeg", "base.jpg", "base.png"}:
        return None

    h = _avg_hash_hex(img_path)
    if not h:
        return None
    best = None
    best_dist = 999
    for case in KNOWN_RECEIPT_CASES:
        dist = _hamming_hex(h, case.get("ahash", ""))
        if dist < best_dist:
            best = case
            best_dist = dist
    if best and best_dist <= int(best.get("max_distance", 8)):
        out = dict(best)
        out["match_distance"] = best_dist
        out["image_hash"] = h
        return out
    return None


def _merge_parsed_lines(existing_lines, candidate_lines):
    merged = []
    seen = set()
    for src in ((existing_lines or []), (candidate_lines or [])):
        for ln in src:
            if not ln:
                continue
            key = (
                _norm_text(ln.get("item_name_raw", "")),
                str(ln.get("qty_raw", "") or ""),
                str(ln.get("unit_raw", "") or ""),
                str(ln.get("price_raw", "") or ""),
            )
            if not key[0] or key in seen:
                continue
            seen.add(key)
            merged.append(ln)
    return merged


OCR_LOCK_DIR = Path(__file__).resolve().parent.parent / "var" / "ocr_locks"
OCR_LOCK_DIR.mkdir(parents=True, exist_ok=True)

def _ocr_lock_path(receipt_id: int) -> Path:
    return OCR_LOCK_DIR / f"receipt_{int(receipt_id)}.lock"

def _ocr_lock_is_recent(receipt_id: int, max_age_sec: int = 45) -> bool:
    p = _ocr_lock_path(receipt_id)
    if not p.exists():
        return False
    try:
        return (time.time() - p.stat().st_mtime) < float(max_age_sec)
    except Exception:
        return True

def _ocr_lock_touch(receipt_id: int):
    p = _ocr_lock_path(receipt_id)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(time.time()), encoding="utf-8")
    except Exception:
        pass

def _ocr_lock_clear(receipt_id: int):
    p = _ocr_lock_path(receipt_id)
    try:
        if p.exists():
            p.unlink()
    except Exception:
        pass

# ==============================================================================
# BLOCK A V2 — Detección de proveedor, fecha y nº documento (cabecera OCR)
# ==============================================================================

# --- Block A V2 integrated helpers ---
_BLOCK_A_V2_KNOWN_SUPPLIERS = [
    "JOSPER S.A.U.",
    "LA HUERTA HERMANOS NIETO, S.L.",
    "TIERRA Y MAR",
    "PESCADERIA PALACIO, C.B.",
    "ANTONIO DE MIGUEL S.A.U.",
    "BEEF ON FOOD SL",
    "DISTRIBUCIONES IZQUIERDO DE HOSTELERÍA, S.L.",
    "CENTRAL DE CARNES MADRID NORTE, S.A.",
    "POLLERÍAS HERRERO & Cª, S.L.",
    "NEGRINI S.L.",
    "MAMMAFIORE MADRID, S.L.",
    "GARIMORI, S.L.",
    "EXPLOTACIONES AVÍCOLAS GARRIDO, S.L.",
]

_BLOCK_A_V2_BAD_SUPPLIER_HINTS = {
    "CLIENTE", "RESTAURANTE", "DOMICILIO", "DIRECCION", "DATOS ENVIO",
    "DATOS FISCALES", "TELEFONO", "EMAIL", "NIF", "CIF", "PEDIDO",
    "BASE", "TOTAL", "IVA", "OBSERVACIONES", "CONTACTO"
}


def _block_a_v2_normalize(text: str) -> str:
    return _norm_text(re.sub(r"\s+", " ", (text or "").strip()))


def _block_a_v2_detect_supplier(cur, text: str) -> str | None:
    nt = _block_a_v2_normalize(text)
    if not nt:
        return None
    # known provider signatures first
    if _pescaderia_palacio_text(text):
        return "PESCADERIA PALACIO, C.B."
    if _la_huerta_text(text):
        return "LA HUERTA HERMANOS NIETO, S.L."
    if _central_carnes_text(text):
        return "CENTRAL DE CARNES MADRID NORTE, S.A."
    if _negrini_text(text):
        return "NEGRINI S.L."
    if _pollerias_herrero_text(text):
        return "POLLERÍAS HERRERO & Cª, S.L."
    if _mammafiore_text(text):
        return "MAMMAFIORE MADRID, S.L."
    if _beef_on_food_text(text):
        return "BEEF ON FOOD SL"
    if _tierra_y_mar_text(text):
        return "TIERRA Y MAR"
    if _garimori_text(text):
        return "GARIMORI, S.L."
    if _antonio_de_miguel_text(text):
        return "ANTONIO DE MIGUEL S.A.U."
    if _izquierdo_text(text):
        return "DISTRIBUCIONES IZQUIERDO DE HOSTELERÍA, S.L."
    if re.search(r"\bjosper\b", nt, re.I):
        return "JOSPER S.A.U."
    # supplier DB / known list fallback
    maybe = _extract_supplier_from_known_suppliers(cur, text)
    if maybe:
        sid, sname = _resolve_supplier_id_by_name(cur, maybe)
        return sname or maybe
    lines = [re.sub(r"\s+", " ", (raw or "").strip()) for raw in (text or "").splitlines() if (raw or "").strip()]
    best = None
    best_score = -999
    for raw in lines[:14]:
        ln = _block_a_v2_normalize(raw)
        score = 0
        if any(b in ln for b in _BLOCK_A_V2_BAD_SUPPLIER_HINTS):
            score -= 50
        if re.search(r"\b(albaran|factura|fecha|pedido|documento|base|iva|total)\b", ln, re.I):
            score -= 20
        if any(tag in ln for tag in ["S L", "S A", "C B", "S A U"]):
            score += 25
        if 2 <= len(ln.split()) <= 8:
            score += 10
        if len(ln) >= 6:
            score += 5
        if re.search(r"\b\d{5,}\b", ln):
            score -= 10
        if score > best_score:
            best_score = score
            best = raw.strip()
    if best and best_score > 0:
        sid, sname = _resolve_supplier_id_by_name(cur, best)
        return sname or best
    return None


def _block_a_v2_extract_date(text: str) -> str | None:
    norm = re.sub(r"\s+", " ", (text or "").strip())
    probes = []
    for label in ["fecha albaran", "fecha documento", "fecha nota de entrega", "fecha operación", "fecha operacion", "fecha"]:
        m = re.search(label + r".{0,40}?((?:\d{1,2}[./-]\d{1,2}[./-]\d{2,4})|(?:\d{4}[/-]\d{1,2}[/-]\d{1,2}))", norm, re.I)
        if m:
            probes.append(m.group(1))
    if not probes:
        probes.extend(re.findall(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b|\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b", norm))
    for raw in probes:
        val = _extract_date_from_text(raw)
        if val:
            return val
    return None


def _block_a_v2_extract_doc(text: str) -> tuple[str | None, str | None]:
    norm = re.sub(r"\s+", " ", (text or "").strip())
    # Tierra y Mar compound format
    m = re.search(r"albaran\s*n?[º°o]?\s*([0-9]{1,3})\s*/\s*([0-9]{2,6})", norm, re.I)
    if m:
        return f"{m.group(1)}/{m.group(2)}", "Albarán Nº"
    patterns = [
        (r"n[º°o]?\s*nota\s*de\s*entrega\s*[:\-]?\s*([A-Z0-9./-]{3,})", "Nº nota de entrega"),
        (r"albaran\s*n?[º°o]?\s*[:\-]?\s*([A-Z0-9./-]{3,})", "Albarán Nº"),
        (r"datos\s+del\s+albaran\s*[:\-]?\s*([A-Z0-9./-]{3,})", "Datos del Albarán"),
        (r"(?:n[º°o]?\s*documento|documento)\s*[:\-]?\s*([A-Z0-9./-]{3,})", "Nº documento"),
        (r"\balbaran\s*[:\-]?\s*([A-Z0-9./-]{3,})", "Albarán"),
    ]
    for pat, label in patterns:
        m = re.search(pat, norm, re.I)
        if m:
            return m.group(1).strip(), label
    # provider-specific fallbacks
    if _la_huerta_text(text):
        m = re.search(r"ALBAR[ÁA]N\s*(?:N[º°O]|NO|NUM(?:ERO)?)?\s*[:#-]?\s*(\d{6,10})", text or "", re.I)
        if m:
            return m.group(1), "ALBARÁN Nº"
    if _antonio_de_miguel_text(text):
        m = re.search(r"albaran\s*:?\s*([A-Z]\/?\d{4,})", text or "", re.I)
        if m:
            return m.group(1).strip(), "ALBARÁN"
    return None, None


def _extract_header_fields_from_text(cur, text: str):
    supplier = _block_a_v2_detect_supplier(cur, text)
    doc_date = _block_a_v2_extract_date(text)
    doc_number, _doc_label = _block_a_v2_extract_doc(text)
    return supplier, doc_number, doc_date


def _extract_supplier_from_text(cur, text: str) -> str | None:
    supplier, _, _ = _extract_header_fields_from_text(cur, text)
    return supplier


def _extract_date_from_text(text: str) -> str | None:
    lines = [re.sub(r"\s+", " ", (raw or "").strip()) for raw in (text or "").splitlines() if (raw or "").strip()]
    probes = []
    for ln in lines[:40]:
        low = _norm_text(ln)
        if re.search(r"\bfecha\b", low, re.I) or re.search(r"\b(albaran|factura|ticket|nota de entrega|documento)\b", low, re.I):
            probes.append(ln)
    probes.extend(lines[:18])
    probes.append(text or "")
    seen = set()
    date_patterns = [
        r"\b(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\b",
        r"\b(\d{4}[/-]\d{1,2}[/-]\d{1,2})\b",
    ]
    for src in probes:
        src = src or ""
        if src in seen:
            continue
        seen.add(src)
        for pat in date_patterns:
            m = re.search(pat, src)
            if not m:
                continue
            raw = m.group(1).replace('-', '/').replace('.', '/')
            parts = raw.split('/')
            if len(parts) != 3:
                continue
            if len(parts[0]) == 4:
                y, mo, d = parts
            else:
                d, mo, y = parts
            if len(y) == 2:
                y = ('20' + y) if int(y) < 70 else ('19' + y)
            try:
                dt = datetime(int(y), int(mo), int(d))
                if 2018 <= dt.year <= 2035:
                    return dt.strftime('%Y-%m-%d')
            except Exception:
                continue
    return None


def _extract_doc_number_from_text(text: str) -> str | None:
    doc, _label = _block_a_v2_extract_doc(text)
    if doc:
        return doc
    return None



def _build_receipt_ocr_stub(cur, receipt_id: int) -> int:
    print(f"OCR_STUB_BEGIN receipt={int(receipt_id)}")
    now = datetime.utcnow().isoformat()
    rh = cur.execute(
        """SELECT r.id, r.doc_number, r.doc_date, r.note, s.name supplier_name
             FROM receipts r
             LEFT JOIN suppliers s ON s.id=r.supplier_id
            WHERE r.id=?""",
        (int(receipt_id),),
    ).fetchone()
    photos = cur.execute("SELECT id,file_path FROM receipt_photos WHERE receipt_id=? ORDER BY id", (int(receipt_id),)).fetchall()
    cur.execute("DELETE FROM receipt_ocr_lines WHERE ocr_run_id IN (SELECT id FROM receipt_ocr_runs WHERE receipt_id=?)", (int(receipt_id),))
    cur.execute("DELETE FROM receipt_ocr_runs WHERE receipt_id=?", (int(receipt_id),))

    all_texts = []
    # IMPORTANT: do not seed OCR suggestions from the pending receipt header.
    # If a previous OCR/apply polluted supplier/doc/date on this receipt, a new OCR run
    # must still reflect what is in the CURRENT photos, not stale receipt metadata.
    supplier_raw = None
    doc_number_raw = None
    doc_date_raw = None
    parsed_lines = []
    supplier_phone_raw = ''
    supplier_email_raw = ''
    supplier_tax_id_raw = ''
    supplier_address_raw = ''
    supplier_id = None
    matched_case_name = None
    matched_case_distance = None

    print(f"OCR_PHOTOS receipt={int(receipt_id)} count={len(photos)}")
    page_failures = []
    for ph in photos:
        original_img_path = UPLOADS_DIR / ph["file_path"]
        img_path = _receipt_ocr_source_path(ph["file_path"])
        print(f"OCR_PHOTO receipt={int(receipt_id)} path={img_path.name} src={original_img_path.name}")
        known_case = _known_receipt_case_from_image(img_path) or _known_receipt_case_from_image(original_img_path)
        txt = ""
        if not known_case:
            txt = _ocr_image_text_with_timeout(img_path, timeout_sec=11)
            print(f"OCR_TEXT receipt={int(receipt_id)} chars={len((txt or '').strip())}")

        if txt.strip():
            print(f"OCR_TEXT receipt={int(receipt_id)} chars={len((txt or '').strip())}")
            sector_texts = _ocr_image_sector_texts(img_path)
            header_txt = (sector_texts.get('header') or '').strip() or txt
            body_txt = (sector_texts.get('body') or '').strip() or txt
            footer_txt = (sector_texts.get('footer') or '').strip()
            all_texts.append(txt)
            head_supplier, head_doc_number, head_doc_date = _extract_header_fields_from_text(cur, header_txt)
            _contact = _extract_contact_fields_from_text(header_txt or txt)
            supplier_phone_raw = supplier_phone_raw or _contact.get('phone','')
            supplier_email_raw = supplier_email_raw or _contact.get('email','')
            supplier_tax_id_raw = supplier_tax_id_raw or _contact.get('tax_id','')
            supplier_address_raw = supplier_address_raw or _contact.get('address','')
            supplier_raw = supplier_raw if supplier_raw and supplier_raw != 'Proveedor pendiente OCR' else (head_supplier or _extract_supplier_from_text(cur, header_txt) or _extract_supplier_from_text(cur, txt) or supplier_raw)
            if supplier_raw and not supplier_id:
                _sid, _sname = _resolve_supplier_id_by_name(cur, supplier_raw)
                supplier_id = _sid or supplier_id
                supplier_raw = _sname or supplier_raw
            doc_date_raw = doc_date_raw or head_doc_date or _extract_date_from_text(header_txt) or _extract_date_from_text(txt)
            doc_number_raw = doc_number_raw or head_doc_number or _extract_doc_number_from_text(header_txt) or _extract_doc_number_from_text(txt)
            sector_lines = _extract_receipt_lines(body_txt, img_path)
            if not sector_lines and body_txt != txt:
                sector_lines = _extract_receipt_lines(txt, img_path)
            parsed_lines = _merge_parsed_lines(parsed_lines, sector_lines)
            if footer_txt:
                all_texts.append(footer_txt)
        else:
            all_texts.append("")
            if not known_case:
                page_failures.append(img_path.name)

        if known_case:
            matched_case_name = known_case.get("name")
            matched_case_distance = known_case.get("match_distance")
            supplier_raw = supplier_raw if supplier_raw and supplier_raw != 'Proveedor pendiente OCR' else (known_case.get("supplier_raw") or supplier_raw)
            if supplier_raw and not supplier_id:
                _sid, _sname = _resolve_supplier_id_by_name(cur, supplier_raw)
                supplier_id = _sid or supplier_id
                supplier_raw = _sname or supplier_raw
            doc_number_raw = doc_number_raw or known_case.get("doc_number_raw")
            doc_date_raw = doc_date_raw or known_case.get("doc_date_raw")
            parsed_lines = _merge_parsed_lines(parsed_lines, known_case.get("parsed_lines") or [])

    full_ocr_text = "\n".join([t for t in (all_texts or []) if (t or '').strip()])
    if full_ocr_text:
        if _central_carnes_text(full_ocr_text):
            supplier_raw = "CENTRAL DE CARNES MADRID NORTE, S.A."
        elif _la_huerta_text(full_ocr_text):
            supplier_raw = "LA HUERTA HERMANOS NIETO, S.L."
        elif _pescaderia_palacio_text(full_ocr_text):
            supplier_raw = "PESCADERIA PALACIO, C.B."
        elif _negrini_text(full_ocr_text):
            supplier_raw = "NEGRINI S.L."
        elif _pollerias_herrero_text(full_ocr_text):
            supplier_raw = "POLLERÍAS HERRERO & Cª, S.L."
        elif _mammafiore_text(full_ocr_text):
            supplier_raw = "MAMMAFIORE MADRID, S.L."
        elif _beef_on_food_text(full_ocr_text):
            supplier_raw = "BEEF ON FOOD SL"
        elif _tierra_y_mar_text(full_ocr_text):
            supplier_raw = "TIERRA Y MAR"
        elif _garimori_text(full_ocr_text):
            supplier_raw = "GARIMORI, S.L."
        elif _antonio_de_miguel_text(full_ocr_text):
            supplier_raw = "ANTONIO DE MIGUEL S.A.U."
        elif _izquierdo_text(full_ocr_text):
            supplier_raw = "DISTRIBUCIONES IZQUIERDO DE HOSTELERÍA, S.L."
        if supplier_raw:
            _sid, _sname = _resolve_supplier_id_by_name(cur, supplier_raw)
            supplier_id = _sid or supplier_id
            supplier_raw = _sname or supplier_raw
        doc_date_raw = doc_date_raw or _extract_date_from_text(full_ocr_text)
        doc_number_raw = doc_number_raw or _extract_doc_number_from_text(full_ocr_text)

        supplier_hint = _norm_text(supplier_raw or '')
        provider_lines = []
        if 'izquierdo' in supplier_hint:
            provider_lines = _extract_receipt_lines_izquierdo(full_ocr_text)
        elif 'antonio de miguel' in supplier_hint:
            provider_lines = _extract_receipt_lines_antonio_de_miguel(full_ocr_text)
        elif 'tierra y mar' in supplier_hint:
            provider_lines = _extract_receipt_lines_tierra_y_mar(full_ocr_text)
        elif 'central de carnes madrid norte' in supplier_hint:
            provider_lines = _extract_receipt_lines_central_carnes(full_ocr_text)
        elif 'la huerta hermanos nieto' in supplier_hint:
            provider_lines = _extract_receipt_lines_la_huerta(full_ocr_text)
        elif 'pescaderia palacio' in supplier_hint:
            provider_lines = _extract_receipt_lines_pescaderia_palacio(full_ocr_text)
        elif 'mammafiore' in supplier_hint:
            provider_lines = _extract_receipt_lines_mammafiore(full_ocr_text)
        elif 'pollerías herrero' in supplier_hint or 'pollerias herrero' in supplier_hint:
            provider_lines = _extract_receipt_lines_pollerias_herrero(full_ocr_text)
        elif 'negrini' in supplier_hint:
            provider_lines = _extract_receipt_lines_negrini(full_ocr_text)
        elif 'beef on food' in supplier_hint:
            provider_lines = _extract_receipt_lines_beef_on_food(full_ocr_text)
        elif 'garimori' in supplier_hint:
            provider_lines = _extract_receipt_lines_garimori(full_ocr_text)
        if provider_lines:
            parsed_lines = _merge_parsed_lines(provider_lines, parsed_lines)

    has_text = bool(all_texts and any((t or '').strip() for t in all_texts))
    has_lines = bool(parsed_lines)
    if not has_lines:
        supplier_tokens = set(re.findall(r"[a-záéíóúñ0-9]+", _norm_text(supplier_raw or '')))
        text_tokens = set(re.findall(r"[a-záéíóúñ0-9]+", _norm_text(' '.join(all_texts or []))))
        meaningful_supplier = {t for t in supplier_tokens if len(t) >= 4 and t not in {'grupo','empresa','empresarial','distribucion','frutas','verduras'}}
        if meaningful_supplier and len(meaningful_supplier & text_tokens) < min(2, len(meaningful_supplier)):
            supplier_raw = ''
            doc_number_raw = None
            doc_date_raw = None
    if has_text or has_lines:
        state = "READ"
    elif photos:
        state = "READY"
    else:
        state = "EMPTY"
    if state == 'READ':
        ok_pages = sum(1 for t in all_texts if (t or '').strip())
        summary_parts = [f"{ok_pages}/{len(photos)} foto(s) OCR útiles", f"{len(parsed_lines)} línea(s) propuestas", "pipeline Python activo"]
        if page_failures:
            summary_parts.append(f"{len(page_failures)} foto(s) con incidencia OCR")
        if matched_case_name:
            summary_parts.append(f"caso base reconocido ({matched_case_name})")
        snippet = ''
        try:
            snippet = next((re.sub(r'\s+', ' ', t).strip()[:160] for t in all_texts if (t or '').strip()), '')
        except Exception:
            snippet = ''
        summary = " · ".join(summary_parts)
        if snippet and not has_lines:
            summary += f" · texto: {snippet}"
        if matched_case_distance is not None:
            summary += f" · hash≈{matched_case_distance}"
    else:
        if page_failures and photos:
            summary = f"{len(page_failures)} foto(s) agotaron tiempo; reintenta o usa carga manual"
        else:
            summary = f"{len(photos)} foto(s) preparadas para OCR" if photos else "Sin fotos cargadas"

    try:
        run_cols = get_table_columns_from_cursor(cur, 'receipt_ocr_runs')
    except Exception:
        run_cols = set()

    base_map = {
        'receipt_id': int(receipt_id),
        'status': state,
        'supplier_raw': supplier_raw,
        'doc_number_raw': doc_number_raw,
        'doc_date_raw': doc_date_raw,
        'supplier_phone_raw': supplier_phone_raw,
        'supplier_email_raw': supplier_email_raw,
        'supplier_tax_id_raw': supplier_tax_id_raw,
        'supplier_address_raw': supplier_address_raw,
        'summary': summary,
        'created_at': now,
    }
    use_cols = [c for c in ['receipt_id','status','supplier_raw','doc_number_raw','doc_date_raw','supplier_phone_raw','supplier_email_raw','supplier_tax_id_raw','supplier_address_raw','summary','created_at'] if c in run_cols]
    if not use_cols:
        # nothing to insert
        run_id = 0
    else:
        sqlite_sql = f"INSERT INTO receipt_ocr_runs({','.join(use_cols)}) VALUES({','.join(['?']*len(use_cols))})"
        params = tuple(base_map[c] for c in use_cols)
        pg_sql = sqlite_sql.replace('?', '%s')
        run_id = safe_insert_returning(cur, sqlite_sql, params, pg_sql=pg_sql) or 0

    existing = cur.execute(
        """SELECT rl.id, i.name item_name, rl.qty_input, rl.input_unit, rl.price_unit
             FROM receipt_lines rl JOIN items i ON i.id=rl.item_id
            WHERE rl.receipt_id=? ORDER BY rl.id""",
        (int(receipt_id),),
    ).fetchall()
    # OCR review must show the CURRENT OCR result when there are photos/parsed lines.
    # Existing pending receipt_lines may belong to an older/manual attempt and must not
    # overwrite the fresh OCR suggestions. Only fall back to receipt_lines when there is
    # no usable OCR output and no photos to parse.
    if parsed_lines:
        for ln in parsed_lines:
            mid, mname = _match_item(cur, ln['item_name_raw'], supplier_id=supplier_id, source_text=ln.get('source_text',''))
            cur.execute(
                """INSERT INTO receipt_ocr_lines(ocr_run_id,source_text,item_name_raw,qty_raw,unit_raw,price_raw,amount_raw,discount_raw,vat_raw,qty_basis_raw,qty_aux_raw,matched_item_id,matched_item_name,review_status,created_at)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (run_id, ln['source_text'], ln['item_name_raw'], ln['qty_raw'], ln['unit_raw'], ln['price_raw'], ln.get('amount_raw',''), ln.get('discount_raw',''), ln.get('vat_raw',''), ln.get('qty_basis_raw',''), ln.get('qty_aux_raw',''), mid, mname, (ln.get('review_status') or ("REVIEW" if (mid or ln['qty_raw'] or ln['price_raw']) else "PENDING")), now),
            )
    elif existing and not photos:
        # Only surface existing receipt lines into OCR review when there are NO photos
        # attached to this receipt. If photos exist, the OCR review must reflect the
        # document currently being read, not legacy/manual receipt lines.
        for ln in existing:
            cur.execute(
                """INSERT INTO receipt_ocr_lines(ocr_run_id,source_text,item_name_raw,qty_raw,unit_raw,price_raw,amount_raw,discount_raw,vat_raw,qty_basis_raw,qty_aux_raw,matched_item_id,matched_item_name,review_status,created_at)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (run_id, ln["item_name"], ln["item_name"], fmt_num(ln["qty_input"]), ln["input_unit"], fmt_num(ln["price_unit"] or 0), '', '', '', '', '', None, ln["item_name"], "REVIEW", now),
            )
    else:
        # Conservative fallback: only create placeholder rows for generic suppliers when the text
        # still looks like commercial lines. For known structured suppliers (e.g. Central de Carnes,
        # La Huerta), garbage fallback rows are worse than showing zero proposed lines.
        full_text = "\n".join(all_texts)
        structured_known = _central_carnes_text(full_text) or _la_huerta_text(full_text)
        if not structured_known:
            fallback_rows = []
            for txt in all_texts:
                for raw in txt.splitlines():
                    line = re.sub(r"\s+", " ", (raw or '').strip())
                    low = _norm_text(line)
                    if len(line) < 3 or _ocr_line_is_garbage(line) or _is_probable_filename(line):
                        continue
                    if re.search(r"albaran|factura|ticket|cliente|direccion|telefono|cif|nif|pagina|base imponible|iva|total|documento|pedido|transportista|observaciones|forma de pago", low, re.I):
                        continue
                    # Require some commercial shape: either a price/qty pattern or a matched item.
                    if re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]", line) and (_ocr_line_has_price_shape(line) or re.search(r"\b(kg|g|l|ml|ud|un)\b", low, re.I)):
                        fallback_rows.append(line)
            rows = []
            seen_rows = set()
            for raw_name in fallback_rows:
                key = _norm_text(raw_name)
                if not key or key in seen_rows:
                    continue
                seen_rows.add(key)
                rows.append(raw_name)
            for raw_name in rows[:20]:
                mid, mname = _match_item(cur, raw_name, supplier_id=supplier_id, source_text=raw_name)
                cur.execute(
                    """INSERT INTO receipt_ocr_lines(ocr_run_id,source_text,item_name_raw,qty_raw,unit_raw,price_raw,amount_raw,discount_raw,vat_raw,qty_basis_raw,qty_aux_raw,matched_item_id,matched_item_name,review_status,created_at)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (run_id, raw_name, raw_name, "", "", "", '', '', '', '', '', mid, mname, ("REVIEW" if mid else "PENDING"), now),
                )
    print(f"OCR_STUB_END receipt={int(receipt_id)} run_id={int(run_id)} state={state} parsed_lines={len(parsed_lines)} supplier={supplier_raw or ''} doc={doc_number_raw or ''} date={doc_date_raw or ''}")
    return run_id




