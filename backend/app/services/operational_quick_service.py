from __future__ import annotations

import json
import os
import re
import sqlite3
import unicodedata
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core import db



def _load_operativa_env_files(override: bool = False) -> None:
    """Carga .env sin dependencia externa. Prioriza variables ya existentes del sistema.
    Busca .env en la carpeta backend, carpeta del paquete y ruta de ejecución.
    """
    here = Path(__file__).resolve()
    candidates = []
    for parent in [Path.cwd(), *here.parents[:8]]:
        candidates.append(parent / ".env")
        candidates.append(parent / "backend" / ".env")
    seen = set()
    for envp in candidates:
        if envp in seen or not envp.exists():
            continue
        seen.add(envp)
        try:
            for line in envp.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and (override or key not in os.environ):
                    os.environ[key] = val
        except Exception:
            pass

_load_operativa_env_files()

PENDING_STATUSES = {"REVIEW", "DRAFT"}

_NUM_WORDS = {
    "cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4,
    "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
    "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20,
    "veintiuno": 21, "veintidos": 22, "veintitres": 23, "veinticuatro": 24, "veinticinco": 25,
    "treinta": 30, "cuarenta": 40, "cincuenta": 50,
    "medio": 0.5, "media": 0.5,
    # Blindaje ante STT sesgado al inglés aunque el usuario hable español.
    "one": 1, "a": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "half": 0.5,
}

_UNIT_ALIASES = {
    "kg": "kg", "kilo": "kg", "kilos": "kg", "kilogramo": "kg", "kilogramos": "kg",
    "g": "g", "gr": "g", "gramo": "g", "gramos": "g",
    "ud": "ud", "unidad": "ud", "unidades": "ud",
    "racion": "racion", "raciones": "racion", "porciones": "racion", "porcion": "racion",
    "caja": "caja", "cajas": "caja", "bandeja": "bandeja", "bandejas": "bandeja",
    "paquete": "paquete", "paquetes": "paquete", "bolsa": "bolsa", "bolsas": "bolsa", "docena": "docena", "docenas": "docena",
    "litro": "l", "litros": "l", "l": "l",
    "kiloes": "kg", "kilogram": "kg", "kilograms": "kg", "gram": "g", "grams": "g",
    "unit": "ud", "units": "ud", "portion": "racion", "portions": "racion",
    "box": "caja", "boxes": "caja", "tray": "bandeja", "trays": "bandeja", "bag": "bolsa", "bags": "bolsa",
}

_TASK_LABELS = {"ORDER": "Pedido", "PRODUCTION": "Producción", "WASTE": "Merma", "UNKNOWN": "Duda"}


def _preclean_speech_text(txt: str) -> str:
    """Normalización previa robusta para dictado en cocina.

    Corrige errores frecuentes de iPhone/Safari y frases incompletas antes de
    clasificar intención. Es deliberadamente conservadora: no confirma datos;
    solo convierte variantes obvias a un texto operativo más limpio.
    """
    t = str(txt or "").lower().strip()
    if not t:
        return ""
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = re.sub(r"[¿?¡!]+", " ", t)
    t = re.sub(r"\btom\.\s*", "tomate ", t)
    t = re.sub(r"\b(?:un|uno|una)?\s*kilo\s+y\s+medio\b", " 1.5 kg", t)
    t = re.sub(r"\b(?:un|uno|una)?\s*litro\s+y\s+medio\b", " 1.5 l", t)
    t = re.sub(r"\bmedio\s+kilo\b", "0.5 kg", t)
    t = re.sub(r"^\s*(saint|sain|san|so|yo)\s+([a-zñ]+)\b", r"soy \2", t, flags=re.I)
    replacements = {
        # fugas/errores de STT inglés-español frecuentes
        "production": "produccion", "productions": "produccion", "producer": "producir",
        "waste": "merma", "loss": "perdida", "order": "pedido", "orders": "pedido",
        "supplier": "proveedor", "suppliers": "proveedor", "bad condition": "mal estado",
        "make": "hacer", "prepare": "preparar", "tomatoes": "tomate", "tomato": "tomate",
        "green onion": "cebolleta", "fish stock": "fumet de pescado",
        # verbos operativos
        "hace una produccion": "hacer una produccion", "hacer produccion": "hacer produccion",
        "acer produccion": "hacer produccion", "aser produccion": "hacer produccion",
        "prepara": "preparar", "preparame": "preparar", "elabora": "elaborar",
        "produce": "producir", "produceme": "producir",
        "arega": "agrega", "arrega": "agrega", "agrea": "agrega", "agregar": "agrega",
        "encarga": "encargar", "solicita": "solicitar",
        # merma
        "mima": "merma", "mimar": "merma", "merna": "merma", "mermas": "merma",
        "perdidas": "perdida", "perdida de": "merma de", "tirar": "merma", "tira": "merma",
        "mal estado": "mal estado", "en mal estado": "mal estado",
        # artículos/recetas calientes
        "tom ": "tomate ", "tomates": "tomate", "tomato": "tomate", "tomatoes": "tomate",

        "piko de gallo": "pico de gallo", "pico de gayo": "pico de gallo", "pico de gallo": "pico de gallo",
        "pico gallo": "pico de gallo", "pico del gallo": "pico de gallo",
        "pico degallo": "pico de gallo", "pico de galio": "pico de gallo", "pico de gallos": "pico de gallo",
        "pico gallo": "pico de gallo", "pico del gallo": "pico de gallo",
        "hacer pico de gallo": "hacer produccion de pico de gallo",
        "preparar pico de gallo": "hacer produccion de pico de gallo",
        "san auria": "zanahoria", "sanahoria": "zanahoria", "sanauria": "zanahoria",
        "zan auria": "zanahoria", "zan oria": "zanahoria",
        "calabasa": "calabaza", "calabassa": "calabaza", "calabacin": "calabacin",
        "pimenton rojo": "pimiento rojo", "pimento rojo": "pimiento rojo",
        "pescado roca": "pescado de roca", "pescao roca": "pescado de roca",
        # basura típica de STT
        "for mastrado": "", "mastrado": "", "are you in": "", "you in": "",
        "sans": "", "ds que": "", "edo": "",
    }
    for a, b in sorted(replacements.items(), key=lambda kv: len(kv[0]), reverse=True):
        t = re.sub(rf"\b{re.escape(a)}\b", b, t, flags=re.I)
    t = re.sub(r"\bproduccion\s+de\s+pico(?!\s+de\s+gallo)\b", "produccion de pico de gallo", t, flags=re.I)
    t = re.sub(r"\bpreparar\s+pico(?!\s+de\s+gallo)\b", "hacer produccion de pico de gallo", t, flags=re.I)
    t = re.sub(r"\b(haz|hazme|hacer|preparar|preparame|preparame|elaborar)\s+(pico de gallo)\b", r"hacer produccion de \2", t, flags=re.I)
    t = re.sub(r"\b(merma|mima|perdida|tirar|tira|desechar)\s+(tomate|tomates)\b", r"merma de tomate", t, flags=re.I)
    t = re.sub(r"\b(cuatro|4)\s+huevo(s)?\s+(roto|rotos|mal estado)\b", r"merma de 4 ud huevos por rotos", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def normalize_operational_text(txt: str) -> str:
    """Texto limpio reutilizable para UI, orquestador y pruebas."""
    return _preclean_speech_text(txt)


def force_spanish_operational_text(txt: str) -> str:
    """Blindaje final: corrige sesgos frecuentes de STT/LLM al inglés antes de clasificar.

    No inventa datos; solo sustituye vocabulario operativo obvio por español.
    """
    t = _preclean_speech_text(txt)
    swaps = {
        r"\bi want to\b": "quiero", r"\bwant to\b": "quiero", r"\bof\b": "de",
        r"\bone\b": "uno", r"\btwo\b": "dos", r"\bthree\b": "tres", r"\bfour\b": "cuatro", r"\bfive\b": "cinco", r"\bsix\b": "seis", r"\bseven\b": "siete", r"\beight\b": "ocho", r"\bnine\b": "nueve", r"\bten\b": "diez", r"\bhalf\b": "medio",
        r"\bkilograms\b": "kg", r"\bkilogram\b": "kg", r"\bgrams\b": "g", r"\bgram\b": "g",
        r"\bproduction\b": "produccion", r"\bproduce\b": "producir", r"\bprepare\b": "preparar", r"\bmake\b": "hacer",
        r"\bwaste\b": "merma", r"\bloss\b": "perdida", r"\bthrow away\b": "merma", r"\bbad condition\b": "mal estado",
        r"\border\b": "pedido", r"\brequest\b": "solicitar", r"\bsupplier\b": "proveedor", r"\bstock\b": "stock",
        r"\btomato\b": "tomate", r"\btomatoes\b": "tomate", r"\bgreen onion\b": "cebolleta",
        r"\bpico de gallo\b": "pico de gallo", r"\bpico gallo\b": "pico de gallo",
    }
    for pat, repl in swaps.items():
        t = re.sub(pat, repl, t, flags=re.I)
    return _preclean_speech_text(t)


def _norm(value: str) -> str:
    txt = _preclean_speech_text(str(value or "").strip().lower())
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    txt = re.sub(r"[^a-z0-9,\.\s]", " ", txt)
    return re.sub(r"\s+", " ", txt).strip()

def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def _multipart_form_data(fields: Dict[str, str], files: Dict[str, tuple[str, bytes, str]]) -> tuple[bytes, str]:
    boundary = "----systemmac" + uuid.uuid4().hex
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")
    for name, (filename, data, content_type) in files.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode())
        chunks.append(f"Content-Type: {content_type}\r\n\r\n".encode())
        chunks.append(data)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _stt_language() -> str:
    lang = (os.environ.get("STT_LANGUAGE") or os.environ.get("OPERATIVA_LANGUAGE") or os.environ.get("OIDO_ALFI_LANGUAGE") or "es").strip()
    aliases = {"es-es": "es", "es_es": "es", "spanish": "es", "fr-fr": "fr", "it-it": "it", "pt-pt": "pt", "en-us": "en"}
    return aliases.get(lang.lower(), lang or "es")


def _transcribe_deepgram(audio: bytes, filename: str, content_type: str) -> Dict[str, Any]:
    key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
    if not key:
        return {"ok": False, "configured": False, "error": "Falta DEEPGRAM_API_KEY."}
    model = os.environ.get("DEEPGRAM_MODEL", os.environ.get("OPERATIVA_STT_MODEL", "nova-3")).strip() or "nova-3"
    lang = _stt_language()
    query = {
        "model": model,
        "language": lang,
        "smart_format": "true",
        "punctuate": "true",
        "numerals": "true",
        "filler_words": "false",
        "keywords": "pico de gallo:4,tomate:3,puerro:3,merma:4,producción:4,pedido:4,albarán:4,proveedor:3",
    }
    url = "https://api.deepgram.com/v1/listen?" + urllib.parse.urlencode(query)
    try:
        req = urllib.request.Request(
            url,
            data=audio,
            headers={"Authorization": f"Token {key}", "Content-Type": content_type or "audio/webm"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=float(os.environ.get("OPERATIVA_STT_TIMEOUT", "25"))) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        txt = ""
        try:
            txt = data["results"]["channels"][0]["alternatives"][0].get("transcript") or ""
        except Exception:
            txt = ""
        clean = force_spanish_operational_text(txt)
        return {
            "ok": bool(clean),
            "configured": True,
            "text": clean,
            "raw_text": txt,
            "raw": data,
            "source": "deepgram_audio",
            "model": model,
            "language": lang,
        }
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8")[:1000]
        except Exception:
            body = ""
        return {"ok": False, "configured": True, "error": f"Deepgram HTTP {exc.code}: {body}", "source": "deepgram_audio"}
    except Exception as exc:
        return {"ok": False, "configured": True, "error": f"No se pudo transcribir con Deepgram: {exc}", "source": "deepgram_audio"}


def _transcribe_openai(audio: bytes, filename: str, content_type: str) -> Dict[str, Any]:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        return {"ok": False, "configured": False, "error": "Falta OPENAI_API_KEY."}
    model = os.environ.get("OPENAI_STT_MODEL", os.environ.get("OPERATIVA_STT_MODEL", "gpt-4o-mini-transcribe"))
    try:
        spanish_prompt = (
            "IDIOMA OBLIGATORIO: español de España. Transcribe literalmente órdenes de cocina/restaurante. "
            "No traduzcas al inglés. Contexto: producción, merma, pedido, stock, proveedor, albarán, receta, pico de gallo, tomate, puerro. "
            "No inventes cantidades, unidades ni responsables."
        )
        body, ctype = _multipart_form_data(
            {"model": model, "language": _stt_language(), "prompt": spanish_prompt},
            {"file": (filename or "audio.webm", audio, content_type or "audio/webm")},
        )
        req = urllib.request.Request(
            "https://api.openai.com/v1/audio/transcriptions",
            data=body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": ctype},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=float(os.environ.get("OPERATIVA_STT_TIMEOUT", "25"))) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        txt = str(data.get("text") or "").strip()
        clean = force_spanish_operational_text(txt)
        return {"ok": bool(clean), "configured": True, "text": clean, "raw_text": txt, "raw": data, "source": "openai_audio", "model": model, "language": _stt_language()}
    except Exception as exc:
        return {"ok": False, "configured": True, "error": f"No se pudo transcribir con OpenAI: {exc}", "source": "openai_audio"}


def transcribe_audio_bytes(audio: bytes, filename: str = "audio.webm", content_type: str = "audio/webm") -> Dict[str, Any]:
    """Transcripción real opcional con selector de proveedor.

    Prioridad actual recomendada: Deepgram para STT y OpenAI como fallback/IA de comprensión.
    No inventa texto si no hay proveedor configurado o si falla la transcripción.
    """
    _load_operativa_env_files(override=True)
    if not audio:
        return {"ok": False, "configured": True, "error": "Audio vacío."}
    provider = (os.environ.get("STT_PROVIDER") or os.environ.get("OPERATIVA_STT_MODE") or "local").lower().strip()
    if provider in {"deepgram", "dg"}:
        primary = _transcribe_deepgram(audio, filename, content_type)
        if primary.get("ok"):
            return primary
        # Fallback controlado a OpenAI si existe, sin ocultar el fallo de Deepgram.
        if os.environ.get("OPENAI_API_KEY", "").strip():
            fallback = _transcribe_openai(audio, filename, content_type)
            if fallback.get("ok"):
                fallback["fallback_from"] = primary.get("source") or "deepgram_audio"
                fallback["warning"] = primary.get("error") or "Deepgram falló y se usó OpenAI."
                return fallback
        return primary
    if provider == "openai":
        return _transcribe_openai(audio, filename, content_type)
    # Auto: Deepgram si hay key; si no, OpenAI; si no, fallback de teclado.
    if provider == "auto":
        if os.environ.get("DEEPGRAM_API_KEY", "").strip():
            return transcribe_audio_bytes(audio, filename, content_type) if os.environ.setdefault("STT_PROVIDER", "deepgram") == "__never__" else _transcribe_deepgram(audio, filename, content_type)
        if os.environ.get("OPENAI_API_KEY", "").strip():
            return _transcribe_openai(audio, filename, content_type)
    return {"ok": False, "configured": False, "error": "STT no configurado. Pega Deepgram API Key en Admin > IA o usa el micrófono del teclado y Ejecutar.", "source": "local_fallback"}


def _dict_from_row(row) -> Dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def _ensure_col(cur: sqlite3.Cursor, table: str, col: str, ddl: str) -> None:
    try:
        cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
        if col not in cols:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
    except Exception:
        pass


def ensure_operational_schema(cur: sqlite3.Cursor) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS operational_queue_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            center_id INTEGER NOT NULL DEFAULT 0,
            task_type TEXT NOT NULL,
            item_name TEXT NOT NULL,
            item_name_norm TEXT NOT NULL,
            item_ref_id INTEGER NOT NULL DEFAULT 0,
            qty_total REAL NOT NULL DEFAULT 0,
            unit TEXT NOT NULL DEFAULT 'ud',
            status TEXT NOT NULL DEFAULT 'REVIEW',
            requested_by TEXT DEFAULT '',
            source TEXT DEFAULT 'voice',
            voice_text TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            decision_note TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS operational_queue_contributions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            line_id INTEGER NOT NULL,
            requested_by TEXT DEFAULT '',
            qty_requested REAL NOT NULL DEFAULT 0,
            unit TEXT NOT NULL DEFAULT 'ud',
            voice_text TEXT DEFAULT '',
            source TEXT DEFAULT 'voice',
            decision TEXT DEFAULT 'ADDED',
            created_at TEXT DEFAULT '',
            FOREIGN KEY(line_id) REFERENCES operational_queue_items(id)
        )
        """
    )
    _ensure_col(cur, "operational_queue_items", "confidence", "REAL DEFAULT 0")
    _ensure_col(cur, "operational_queue_items", "intent_source", "TEXT DEFAULT 'rules'")
    _ensure_col(cur, "operational_queue_items", "raw_json", "TEXT DEFAULT ''")
    _ensure_col(cur, "operational_queue_contributions", "raw_json", "TEXT DEFAULT ''")
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_operational_queue_lookup ON operational_queue_items(center_id, task_type, status, item_name_norm, unit)")
    except Exception:
        pass


def extract_responsible(raw_text: str) -> str:
    c = _norm(raw_text)
    patterns = [
        r"\bsoy\s+([a-z]+(?:\s+[a-z]+){0,2})",
        r"\bresponsable\s+([a-z]+(?:\s+[a-z]+){0,2})",
        r"\blo\s+dicta\s+([a-z]+(?:\s+[a-z]+){0,2})",
        r"\bregistrado\s+por\s+([a-z]+(?:\s+[a-z]+){0,2})",
    ]
    stops = {"pedido", "pide", "agrega", "anade", "produccion", "produce", "producir", "hacer", "preparar", "elaborar", "merma", "hay", "quiero", "necesito", "de", "por", "al", "medio", "media", "un", "uno", "una", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez"}
    for pat in patterns:
        m = re.search(pat, c)
        if m:
            words = [w for w in m.group(1).split() if w not in stops]
            if words:
                return " ".join(w.capitalize() for w in words[:2])
    return ""


def detect_task_type(raw_text: str, forced: str = "AUTO") -> tuple[str, float, str]:
    forced = str(forced or "AUTO").upper().strip()
    if forced in {"ORDER", "PRODUCTION", "WASTE"}:
        return forced, 0.99, "manual"
    c = _norm(raw_text)
    scores = {"ORDER": 0, "PRODUCTION": 0, "WASTE": 0}
    for k in ["pedido", "pedir", "pide", "comprar", "compra", "encargar", "encarga", "solicitar", "solicita", "agrega", "anade", "añade", "carrito", "necesito", "falta", "faltan", "apunta compra", "anota compra"]:
        if k in c: scores["ORDER"] += 2
    for k in ["produc", "produccion", "producción", "hacer produccion", "hacer producción", "preparar", "prepara", "preparame", "prepárame", "elaborar", "cocinar", "raciones", "receta", "mise", "partida", "lote"]:
        if k in c: scores["PRODUCTION"] += 2
    for k in ["merma", "mima", "desperdicio", "perdida", "pérdida", "tirar", "tira", "desechar", "mal estado", "caduc", "podrido", "ferment", "roto", "quemado"]:
        if k in c: scores["WASTE"] += 2
    # Patrones fuertes: evitan que "quiero hacer una producción de X" empate con pedido por "quiero".
    if re.search(r"\b(quiero\s+)?hacer\s+(una\s+)?produccion\b", c) or re.search(r"\bproduccion\s+de\b", c):
        scores["PRODUCTION"] += 5
    if re.search(r"\b(hacer|preparar|preparame|elaborar)\s+pico\b", c):
        scores["PRODUCTION"] += 5
    if re.search(r"\b(merma|mima|merna|tirar|tira|perdida|mal estado|roto|rotos|caduc|podrido)\s+(de\s+)?", c):
        scores["WASTE"] += 4
    if re.search(r"\b(pedir|pedido|encargar|solicitar)\b", c):
        scores["ORDER"] += 3
    best = max(scores, key=scores.get)
    if scores[best] <= 0:
        return "UNKNOWN", 0.25, "rules"
    total = sum(scores.values()) or 1
    confidence = max(0.45, min(0.98, scores[best] / total))
    if sorted(scores.values(), reverse=True)[0] == sorted(scores.values(), reverse=True)[1]:
        confidence = 0.55
    return best, confidence, "rules"


def _parse_qty_token(tok: str) -> Optional[float]:
    raw = tok.replace(",", ".")
    if re.fullmatch(r"\d+(?:\.\d+)?", raw):
        return float(raw)
    if tok in _NUM_WORDS:
        return float(_NUM_WORDS[tok])
    return None


def _qty_unit_matches(c: str):
    tokens = c.split()
    hits = []
    for i, tok in enumerate(tokens):
        qty = _parse_qty_token(tok)
        if qty is None:
            continue
        unit_tok = tokens[i + 1] if i + 1 < len(tokens) else ""
        unit_key = unit_tok.strip(".,;:")
        has_unit = unit_key in _UNIT_ALIASES
        # Evita falsos positivos tipo “una merma”, “un pedido”.
        if tok in {"un", "una", "uno", "medio", "media"} and not has_unit:
            continue
        # Para números sin unidad se permite, pero se interpreta como unidad.
        unit = _UNIT_ALIASES.get(unit_key, "ud")
        end = i + 2 if has_unit else i + 1
        hits.append({"i": i, "end": end, "qty": qty, "unit": unit, "fragment": " ".join(tokens[i:end])})
    return tokens, hits


def _clean_item_text(txt: str, task_type: str = "ORDER") -> str:
    item = _norm(txt)
    if item in {"pico", "pico gallo", "pico de gallo"} or "produccion de pico" in item:
        return "pico de gallo"
    if item in {"tom", "tom.", "tomates"}:
        return "tomate"
    canonical_hits = [
        "pico de gallo", "pico gallo", "salsa de tomate", "salsa tomate", "lasaña de verduras", "lasana de verduras",
        "tomate rama", "tomate pera", "tomate cherry", "pimiento rojo", "pimiento verde", "zanahoria", "calabaza", "calabacin", "cebolla", "tomate",
        "puerro", "patata", "patatas", "lechuga", "salmon", "salmón", "lubina", "dorada", "merluza", "pescado de roca", "pescado roca", "pollo", "ternera", "huevos", "huevo",
    ]
    for canon in sorted(canonical_hits, key=len, reverse=True):
        cn = _norm(canon)
        if cn and cn in item:
            return cn
    remove_phrases = [
        "agrega", "anade", "añade", "poner", "pon", "pide", "pedir", "pedido", "al pedido", "al carrito",
        "comprar", "compra", "necesito", "quiero", "hacer", "preparar", "producir", "produccion", "producción",
        "elaborar", "cocinar", "hay", "existe", "registrar", "registra", "apunta", "anota", "una", "un", "merma", "de", "del", "la", "el", "los", "las", "por favor",
        "are", "you", "in", "i", "want", "to", "of", "mima", "edo", "emilio", "ds", "que",
    ]
    for phrase in sorted(remove_phrases, key=len, reverse=True):
        item = re.sub(rf"\b{re.escape(_norm(phrase))}\b", " ", item)
    item = re.split(r"\bal pedido\b|\bpedido\b|\bal carrito\b|\bpor\b|\bresponsable\b|\bpara\b|\bmanana\b|\bhoy\b|\bsoy\b", item)[0]
    item = re.sub(r"\b(y|e|con|mas)\b", " ", item)
    item = re.sub(r"\s+", " ", item).strip(" ,.-")
    return item

def _extract_reason(raw_text: str) -> str:
    c = _norm(raw_text)
    m = re.search(r"\bpor\s+(.+)$", c)
    if m:
        reason = re.split(r"\bresponsable\b|\bsoy\b", m.group(1))[0].strip()
        return reason[:80]
    for reason in ["mal estado", "caducado", "caducidad", "rotura", "quemado", "fermentada", "fermentado", "sobrante"]:
        if reason in c:
            return reason
    return ""


def _local_parse_items(raw_text: str, forced_task_type: str = "AUTO") -> Dict[str, Any]:
    original = str(raw_text or "").strip()
    c = _norm(original)
    task_type, confidence, source = detect_task_type(c, forced_task_type)
    responsible = extract_responsible(original)
    reason = _extract_reason(original)
    tokens, hits = _qty_unit_matches(c)
    items = []
    if hits:
        for idx, h in enumerate(hits):
            start = h["end"]
            end = hits[idx + 1]["i"] if idx + 1 < len(hits) else len(tokens)
            item_txt = " ".join(tokens[start:end])
            item = _clean_item_text(item_txt, task_type)
            reason_only = _norm(item) in {"mal estado", "estado", "roto", "rotos", "podrido", "podrida", "caducado", "caducada", "quemado", "quemada", "fermentado", "fermentada"}
            if (not item or reason_only) and idx == 0:
                before = " ".join(tokens[:h["i"]])
                before_item = _clean_item_text(before, task_type)
                if before_item:
                    item = before_item
            if item and _norm(item) not in {"mal estado", "estado", "roto", "rotos", "podrido", "podrida", "caducado", "caducada", "quemado", "quemada", "fermentado", "fermentada"}:
                items.append({"name": item.upper(), "name_norm": _norm(item), "qty": h["qty"], "unit": h["unit"]})
    if not items:
        item = _clean_item_text(c, task_type)
        canonical = _norm(item) in {"pico de gallo", "tomate", "tomate rama", "tomate pera", "tomate cherry", "zanahoria", "cebolla", "pimiento rojo", "pimiento verde"}
        default_unit = "kg" if task_type in {"WASTE", "ORDER"} else "ud"
        items.append({"name": (item or "Sin identificar").upper(), "name_norm": _norm(item), "qty": 0.0, "unit": default_unit})
        confidence = min(confidence, 0.65 if canonical else 0.45)
    if any(not it.get("name_norm") or it.get("name") == "SIN IDENTIFICAR" for it in items):
        confidence = min(confidence, 0.55)
    if any(float(it.get("qty") or 0) <= 0 for it in items):
        # Faltar cantidad no debe impedir borradores seguros de producción/merma; sí baja la confianza operativa.
        floor = 0.65 if task_type in {"PRODUCTION", "WASTE"} else 0.60
        confidence = min(confidence, floor)
    return {
        "task_type": task_type if task_type != "UNKNOWN" else "ORDER",
        "task_label": _TASK_LABELS.get(task_type, "Duda"),
        "confidence": round(float(confidence), 2),
        "intent_source": source,
        "responsible": responsible,
        "reason": reason,
        "items": items,
        "voice_text": original,
        "needs_clarification": task_type == "UNKNOWN" or confidence < 0.65,
    }




def _name_similarity(a: str, b: str) -> float:
    aa = set(_norm(a).split())
    bb = set(_norm(b).split())
    if not aa or not bb:
        return 0.0
    inter = len(aa & bb)
    union = len(aa | bb) or 1
    base = inter / union
    an = _norm(a); bn = _norm(b)
    if an and bn and (an in bn or bn in an):
        base = max(base, 0.78)
    return round(float(base), 3)


def _candidate_seed_terms(raw_text: str) -> list[str]:
    c = _norm(raw_text)
    stop = {
        "soy","responsable","pedido","pedir","pide","agrega","anade","añade","compra","comprar","necesito","carrito",
        "quiero","hacer","preparar","producir","produccion","producción","elaborar","raciones","racion",
        "merma","tirar","tira","desechar","mal","estado","caducado","fermentado","fermentada","por","para","de","del","la","el","los","las","un","una","uno",
        "dos","tres","cuatro","cinco","seis","siete","ocho","nueve","diez","medio","media","kilo","kilos","kg","gramos","g","ud","unidad","unidades"
    }
    words = [w for w in c.split() if w and w not in stop and len(w) > 1]
    out = []
    if words:
        out.append(" ".join(words[:5]))
        for i in range(len(words)):
            out.append(words[i])
            if i + 1 < len(words): out.append(words[i] + " " + words[i+1])
            if i + 2 < len(words): out.append(words[i] + " " + words[i+1] + " " + words[i+2])
    # También agrega nombres canónicos frecuentes corregidos por _preclean_speech_text.
    for hot in ["pico de gallo", "pico gallo", "zanahoria", "calabaza", "tomate", "tomates", "tomate rama", "salsa de tomate", "lasaña de verduras", "cebolla", "pimiento rojo", "huevos", "huevo", "pescado de roca", "pescado roca", "puerro", "lubina", "patata", "patatas"]:
        if _norm(hot) in c:
            out.insert(0, _norm(hot))
    return list(dict.fromkeys([x.strip() for x in out if x.strip()]))[:18]


def _fetch_context_candidates(cur: sqlite3.Cursor, raw_text: str, forced_task_type: str = "AUTO", limit: int = 25) -> Dict[str, Any]:
    seeds = _candidate_seed_terms(raw_text)
    candidates: dict[str, list[dict[str, Any]]] = {"items": [], "recipes": [], "suppliers": [], "productions": []}

    def add(kind: str, row: dict[str, Any], score: float):
        row = dict(row)
        row["score"] = max(float(row.get("score") or 0), float(score or 0))
        key = f"{kind}:{row.get('id')}:{_norm(row.get('name',''))}"
        existing = candidates.setdefault(kind, [])
        for e in existing:
            if f"{kind}:{e.get('id')}:{_norm(e.get('name',''))}" == key:
                e["score"] = max(float(e.get("score") or 0), row["score"])
                return
        existing.append(row)

    for seed in seeds or [_norm(raw_text)]:
        if not seed:
            continue
        like = f"%{seed}%"
        try:
            for r in cur.execute("SELECT id,name,unit,current_price,order_category,stock_area FROM items WHERE lower(name) LIKE lower(?) ORDER BY LENGTH(name) LIMIT 8", (like,)).fetchall():
                add("items", _dict_from_row(r), _name_similarity(seed, r["name"]))
        except Exception:
            pass
        try:
            for r in cur.execute("SELECT id,name,category,subcategory,is_subrecipe,yield_final_qty,yield_final_unit FROM recipes WHERE COALESCE(is_active,1)=1 AND lower(name) LIKE lower(?) ORDER BY LENGTH(name) LIMIT 8", (like,)).fetchall():
                add("recipes", _dict_from_row(r), _name_similarity(seed, r["name"]))
        except Exception:
            pass
        try:
            for r in cur.execute("SELECT id,name FROM suppliers WHERE COALESCE(is_active,1)=1 AND lower(name) LIKE lower(?) ORDER BY LENGTH(name) LIMIT 5", (like,)).fetchall():
                add("suppliers", _dict_from_row(r), _name_similarity(seed, r["name"]))
        except Exception:
            pass
        try:
            cols = [x[1] for x in cur.execute("PRAGMA table_info(productions)").fetchall()]
            name_cols = [c for c in ["recipe_name", "item_name", "name", "title"] if c in cols]
            if name_cols:
                nc = name_cols[0]
                for r in cur.execute(f"SELECT id,{nc} as name FROM productions WHERE lower({nc}) LIKE lower(?) ORDER BY id DESC LIMIT 6", (like,)).fetchall():
                    add("productions", _dict_from_row(r), _name_similarity(seed, r["name"]))
        except Exception:
            pass

    for seed in seeds[:8]:
        try:
            iid, iname = _token_like_match(cur, "items", seed, "1=1")
            if iid: add("items", {"id": iid, "name": iname}, _name_similarity(seed, iname))
        except Exception:
            pass
        try:
            rid, rname = _token_like_match(cur, "recipes", seed, "COALESCE(is_active,1)=1")
            if rid: add("recipes", {"id": rid, "name": rname}, _name_similarity(seed, rname))
        except Exception:
            pass

    for k in candidates:
        candidates[k] = sorted(candidates[k], key=lambda x: float(x.get("score") or 0), reverse=True)[:limit]
    return {"seeds": seeds[:10], "candidates": candidates}


def _candidate_prompt_block(ctx: Dict[str, Any]) -> str:
    lines = []
    for kind, label in [("items","ARTICULOS_STOCK"),("recipes","RECETAS_SUBRECETAS"),("productions","PRODUCCIONES"),("suppliers","PROVEEDORES")]:
        rows = (ctx.get("candidates") or {}).get(kind) or []
        if not rows:
            continue
        lines.append(label + ":")
        for r in rows[:18]:
            extra = []
            for f in ["unit","order_category","stock_area","category","subcategory","is_subrecipe"]:
                if r.get(f) not in (None, ""):
                    extra.append(f"{f}={r.get(f)}")
            lines.append(f"- id={r.get('id')} name={r.get('name')}" + (" (" + ", ".join(extra) + ")" if extra else ""))
    return "\n".join(lines)[:7000]


def _apply_candidate_resolution(parsed: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    task_type = str(parsed.get("task_type") or "ORDER").upper()
    items = parsed.get("items") or []
    if task_type == "PRODUCTION":
        candidate_groups = ["recipes", "productions", "items"]
    elif task_type == "WASTE":
        candidate_groups = ["productions", "recipes", "items"]
    else:
        # Pedidos solo pueden entrar como artículos reales de catálogo/stock.
        # Las recetas pueden servir como contexto, pero no deben convertirse en líneas normales de pedido.
        candidate_groups = ["items"]
    all_candidates = []
    for g in candidate_groups:
        all_candidates.extend([(g, c) for c in (ctx.get("candidates") or {}).get(g) or []])
    resolved = []
    needs_review = bool(parsed.get("needs_clarification"))
    for it in items:
        raw_name = str(it.get("name") or "").strip()
        raw_norm = _norm(raw_name)
        scored = []
        for kind, cand in all_candidates:
            score = _name_similarity(raw_norm, cand.get("name") or "")
            if score > 0:
                scored.append((score, kind, cand))
        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0] if scored else None
        best_score = float(best[0]) if best else 0.0
        ambiguous = False
        if len(scored) > 1:
            second = float(scored[1][0])
            ambiguous = best_score < 0.96 and (best_score - second) <= 0.06
        out = dict(it)
        out["raw_name"] = raw_name
        out["match_confidence"] = round(best_score, 2)
        out["alternatives"] = [{"kind": k, "id": c.get("id"), "name": c.get("name"), "score": round(float(s),2)} for s,k,c in scored[:5]]
        if best and best_score >= 0.58:
            _, kind, cand = best
            out["name"] = str(cand.get("name") or raw_name).upper()
            out["name_norm"] = _norm(cand.get("name") or raw_name)
            out["matched_id"] = int(cand.get("id") or 0)
            out["matched_kind"] = kind
            if kind == "items" and cand.get("unit") and (not out.get("unit") or out.get("unit") == "ud"):
                out["unit"] = str(cand.get("unit") or out.get("unit") or "ud")
            if ambiguous:
                needs_review = True
                out["ambiguous_match"] = True
                if task_type == "WASTE" and raw_norm in {"tomate", "pico de gallo"}:
                    out["name"] = raw_name.upper()
                    out["name_norm"] = raw_norm
                    out["matched_id"] = 0
                    out["matched_kind"] = "none"
        else:
            out["name"] = raw_name.upper() if raw_name else "SIN IDENTIFICAR"
            out["name_norm"] = raw_norm
            out["matched_id"] = 0
            out["matched_kind"] = "none"
            needs_review = True
        if float(out.get("qty") or 0) <= 0:
            needs_review = True
        resolved.append(out)
    parsed["items"] = resolved
    parsed["context_candidates"] = ctx.get("candidates") or {}
    parsed["needs_clarification"] = needs_review
    if any((it.get("matched_kind") == "none") for it in resolved):
        parsed["confidence"] = min(float(parsed.get("confidence") or 0.5), 0.68)
    elif resolved:
        parsed["confidence"] = max(float(parsed.get("confidence") or 0.0), min(0.96, max(float(it.get("match_confidence") or 0) for it in resolved)))
    return parsed

def _try_ai_parse(raw_text: str, forced_task_type: str = "AUTO", ctx: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """IA externa opcional: si está configurada, es el motor principal de interpretación.
    Recibe candidatos reales del sistema para no inventar artículos/recetas/proveedores.
    """
    if os.environ.get("OPERATIVA_AI_MODE", "").lower() != "openai":
        return None
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        return None
    model = os.environ.get("OPERATIVA_AI_MODEL", "gpt-4o-mini")
    ctx = ctx or {"candidates": {}}
    candidates_txt = _candidate_prompt_block(ctx)
    prompt = (
        "IDIOMA OBLIGATORIO: español. Eres el intérprete operativo de un sistema F&B profesional en España. "
        "Toda salida textual debe estar en español: corrected_text, reason, nombres normalizados y cualquier explicación interna. "
        "PROHIBIDO razonar, traducir o clasificar en inglés. No uses production/waste/order como salida visible; usa solo task_type técnico ORDER/PRODUCTION/WASTE en JSON y nombres en español. "
        "Corrige errores de dictado español de cocina y devuelve JSON estricto. Prioriza seguridad operativa: si faltan cantidad, responsable o vínculo exacto, marca revisión; nunca confirmes stock. "
        "Si la transcripción llega sesgada al inglés, traduce al equivalente operativo español antes de interpretar: production=producción, prepare=preparar, make=hacer, waste=merma, loss=pérdida, order=pedido, tomato=tomate. "
        "Primero decide task_type: ORDER pedido/compra/carrito, PRODUCTION producción/receta/elaboración, WASTE merma/pérdida. "
        "Equivalencias obligatorias: pico gallo=pico de gallo; tomate/tomates/tom./tomato/tomatoes=tomate; hacer/preparar/producir/make/prepare=PRODUCTION; tirar/pérdida/merma/mal estado/waste/loss=WASTE; pedir/encargar/solicitar/order=ORDER. "
        "Usa SOLO candidatos reales cuando haya coincidencias. No inventes artículo, receta ni cantidad. "
        "Si hay varias coincidencias posibles o no estás seguro, marca needs_clarification=true. "
        "Campos obligatorios: task_type, confidence, responsible, reason, corrected_text, needs_clarification, "
        "items[{name, qty, unit, matched_kind, matched_id, match_confidence}]. "
        "Unidades preferidas: kg, g, ud, racion, caja, bandeja, paquete, bolsa, docena. "
        "Si dicen 'cuatro huevos' o 'merma de cuatro huevos', interpreta qty=4 unit=ud name=huevos. "
        "Si dicen 'mima', probablemente es 'merma'. Si dicen 'producción de pico', probablemente es producción de PICO DE GALLO si existe candidato. Si dicen 'pescado roca', normaliza como 'pescado de roca'. "
        "Si no hay cantidad, qty=0. Si no hay responsable, responsible=''. "
        f"Modo forzado: {forced_task_type}.\n"
        f"Texto dictado bruto: {raw_text!r}\n\n"
        f"CANDIDATOS_REALES_DEL_SISTEMA:\n{candidates_txt or 'Sin candidatos encontrados.'}"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Devuelve solo JSON válido, sin markdown ni comentarios. Idioma obligatorio de los campos de texto: español. No traduzcas productos a inglés."},
            {"role": "user", "content": prompt},
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
        with urllib.request.urlopen(req, timeout=float(os.environ.get("OPERATIVA_AI_TIMEOUT", "12"))) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        items = parsed.get("items") or []
        clean_items = []
        for it in items:
            name = str(it.get("name") or "").strip()
            if name:
                unit_raw = _norm(str(it.get("unit") or "ud"))
                clean_items.append({
                    "name": name.upper(),
                    "name_norm": _norm(name),
                    "qty": float(it.get("qty") or 0),
                    "unit": _UNIT_ALIASES.get(unit_raw, unit_raw or "ud"),
                    "matched_kind": str(it.get("matched_kind") or "").strip(),
                    "matched_id": int(it.get("matched_id") or 0),
                    "match_confidence": float(it.get("match_confidence") or 0),
                })
        if not clean_items:
            return None
        tt = str(parsed.get("task_type") or "UNKNOWN").upper()
        forced = str(forced_task_type or "AUTO").upper()
        if forced in {"ORDER", "PRODUCTION", "WASTE"}:
            tt = forced
        conf = max(0, min(1, float(parsed.get("confidence") or 0.75)))
        return {
            "task_type": tt if tt in {"ORDER", "PRODUCTION", "WASTE"} else "UNKNOWN",
            "task_label": _TASK_LABELS.get(tt, "Duda"),
            "confidence": conf,
            "intent_source": "ai",
            "responsible": str(parsed.get("responsible") or "").strip(),
            "reason": str(parsed.get("reason") or "").strip(),
            "corrected_text": str(parsed.get("corrected_text") or raw_text).strip(),
            "items": clean_items,
            "voice_text": raw_text,
            "needs_clarification": bool(parsed.get("needs_clarification")) or tt == "UNKNOWN" or conf < 0.72,
        }
    except Exception:
        return None


def get_ai_status() -> Dict[str, Any]:
    """Estado visible de la IA. Recarga .env para evitar que el usuario tenga que mirar consola."""
    _load_operativa_env_files(override=True)
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    deepgram_key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
    ai_mode = os.environ.get("OPERATIVA_AI_MODE", "local").strip().lower() or "local"
    stt_mode = (os.environ.get("STT_PROVIDER") or os.environ.get("OPERATIVA_STT_MODE") or "local").strip().lower() or "local"
    ai_model = os.environ.get("OPERATIVA_AI_MODEL", "gpt-4o-mini").strip() if ai_mode == "openai" else "local"
    if stt_mode == "deepgram":
        stt_model = os.environ.get("DEEPGRAM_MODEL", "nova-3").strip()
        stt_configured = bool(deepgram_key)
    elif stt_mode == "openai":
        stt_model = os.environ.get("OPENAI_STT_MODEL", os.environ.get("OPERATIVA_STT_MODEL", "gpt-4o-mini-transcribe")).strip()
        stt_configured = bool(openai_key)
    else:
        stt_model = "local"
        stt_configured = False
    configured = bool(openai_key) and ai_mode == "openai"
    label_parts = []
    if configured:
        label_parts.append("OPENAI IA")
    if stt_configured:
        label_parts.append(("DEEPGRAM VOZ" if stt_mode == "deepgram" else "OPENAI VOZ"))
    return {
        "ai_mode": ai_mode,
        "stt_mode": stt_mode,
        "stt_provider": stt_mode,
        "ai_model": ai_model,
        "stt_model": stt_model,
        "stt_language": _stt_language(),
        "has_key": bool(openai_key),
        "openai_key_loaded": bool(openai_key),
        "deepgram_key_loaded": bool(deepgram_key),
        "key_hint": ("••••" + openai_key[-4:]) if openai_key else "",
        "deepgram_key_hint": ("••••" + deepgram_key[-4:]) if deepgram_key else "",
        "configured": configured,
        "stt_configured": stt_configured,
        "status_label": " + ".join(label_parts) if label_parts else "LOCAL / SIN IA EXTERNA",
        "warning": "OpenAI interpreta; Deepgram transcribe voz." if configured and stt_mode == "deepgram" and stt_configured else ("OpenAI está configurada para interpretar la operativa." if configured else "OpenAI no está configurada o no se ha cargado la clave. La comprensión usa reglas locales."),
    }


def test_openai_connection() -> Dict[str, Any]:
    """Prueba mínima de OpenAI para Admin. No muestra ni devuelve la clave."""
    status = get_ai_status()
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        return {"ok": False, "status": status, "code": "NO_KEY", "message": "No hay OPENAI_API_KEY cargada. Ejecuta CONFIGURAR_IA_OPENAI.command y reinicia."}
    if status.get("ai_mode") != "openai":
        return {"ok": False, "status": status, "code": "MODE_LOCAL", "message": "La clave existe, pero OPERATIVA_AI_MODE no está en openai."}
    model = os.environ.get("OPERATIVA_AI_MODEL", "gpt-4o-mini")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Responde solo JSON válido."},
            {"role": "user", "content": "Devuelve {\"ok\":true} si recibes este mensaje."},
        ],
        "temperature": 0,
        "max_tokens": 20,
        "response_format": {"type": "json_object"},
    }
    try:
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=float(os.environ.get("OPERATIVA_AI_TIMEOUT", "12"))) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
        return {"ok": True, "status": get_ai_status(), "code": "OK", "message": "OpenAI conectada correctamente.", "model": model, "usage": data.get("usage") or {}}
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8")[:1000]
        except Exception:
            body = ""
        code = "HTTP_" + str(exc.code)
        msg = "Error de OpenAI."
        if exc.code == 401:
            msg = "Clave inválida, revocada o mal pegada. Crea otra clave y vuelve a configurar."
        elif exc.code == 429:
            msg = "Sin cuota/saldo, límite alcanzado o facturación no activa. Revisa billing en OpenAI Platform."
        elif exc.code == 404:
            msg = f"Modelo no disponible para esta clave: {model}."
        return {"ok": False, "status": get_ai_status(), "code": code, "message": msg, "detail": body}
    except Exception as exc:
        return {"ok": False, "status": get_ai_status(), "code": "CONNECTION_ERROR", "message": f"No se pudo conectar con OpenAI: {exc}"}


def test_deepgram_connection() -> Dict[str, Any]:
    """Prueba mínima de Deepgram para Admin. No transcribe ni muestra la clave."""
    status = get_ai_status()
    key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
    if not key:
        return {"ok": False, "provider": "deepgram", "status": status, "code": "NO_KEY", "message": "No hay DEEPGRAM_API_KEY cargada. Pega la clave en Admin > IA > Deepgram API Key."}
    model = os.environ.get("DEEPGRAM_MODEL", os.environ.get("OPERATIVA_STT_MODEL", "nova-3")).strip() or "nova-3"
    try:
        req = urllib.request.Request(
            "https://api.deepgram.com/v1/projects",
            headers={"Authorization": f"Token {key}"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=float(os.environ.get("OPERATIVA_STT_TIMEOUT", "12"))) as resp:
            raw = resp.read().decode("utf-8")[:1000]
        return {"ok": True, "provider": "deepgram", "status": get_ai_status(), "code": "OK", "message": "Deepgram conectado correctamente para voz.", "model": model, "language": _stt_language(), "detail": raw}
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8")[:1000]
        except Exception:
            body = ""
        code = "HTTP_" + str(exc.code)
        msg = "Error de Deepgram."
        if exc.code in {401, 403}:
            msg = "Clave Deepgram inválida, revocada o sin permisos. Crea otra clave y vuelve a pegarla."
        elif exc.code == 429:
            msg = "Límite/cuota de Deepgram alcanzado."
        return {"ok": False, "provider": "deepgram", "status": get_ai_status(), "code": code, "message": msg, "detail": body}
    except Exception as exc:
        return {"ok": False, "provider": "deepgram", "status": get_ai_status(), "code": "CONNECTION_ERROR", "message": f"No se pudo conectar con Deepgram: {exc}"}


def _infer_missing_article_defaults(name: str, unit: str = "kg") -> Dict[str, str]:
    n = _norm(name)
    if any(w in n for w in ["pescado", "salmon", "merluza", "atun", "lubina", "dorada", "bacalao", "roca"]):
        return {"stock_area": "camara", "order_category": "PESCADOS", "unit": unit or "kg"}
    if any(w in n for w in ["zanahoria", "tomate", "cebolla", "pimiento", "calabaza", "calabacin", "lechuga", "verdura"]):
        return {"stock_area": "camara", "order_category": "VERDURAS", "unit": unit or "kg"}
    if any(w in n for w in ["pollo", "ternera", "cerdo", "carne"]):
        return {"stock_area": "camara", "order_category": "CARNES", "unit": unit or "kg"}
    return {"stock_area": "cocina", "order_category": "SIN_CLASIFICAR", "unit": unit or "kg"}


def create_missing_article_and_add_to_order(*, center_id: int, item_name: str, qty: float, unit: str = "kg", requested_by: str = "", voice_text: str = "") -> Dict[str, Any]:
    """Alta rápida segura: crea artículo si no existe y lo añade al carrito de pedidos como REVIEW."""
    clean_name = str(item_name or "").strip().upper()
    if not clean_name or clean_name in {"SIN IDENTIFICAR", "NONE"}:
        return {"ok": False, "error": "Falta nombre de artículo para crear."}
    try:
        qty = float(qty or 0)
    except Exception:
        qty = 0.0
    if qty <= 0:
        return {"ok": False, "error": "Falta cantidad válida para añadir al carrito."}
    unit = _UNIT_ALIASES.get(_norm(unit), unit or "kg")
    defaults = _infer_missing_article_defaults(clean_name, unit)
    conn = db(); cur = conn.cursor(); ensure_operational_schema(cur)
    _ensure_col(cur, "items", "order_category", "TEXT NOT NULL DEFAULT ''")
    _ensure_col(cur, "items", "stock_area", "TEXT NOT NULL DEFAULT ''")
    _ensure_col(cur, "items", "waste_default_pct", "REAL NOT NULL DEFAULT 0")
    try:
        row = cur.execute("SELECT id,name,unit FROM items WHERE lower(name)=lower(?) LIMIT 1", (clean_name,)).fetchone()
        if row:
            item_id = int(row["id"]); item_real_name = str(row["name"] or clean_name); real_unit = str(row["unit"] or unit)
        else:
            cur.execute(
                "INSERT INTO items(name,unit,min_qty,max_qty,current_price,waste_default_pct,stock_area,order_category) VALUES(?,?,?,?,?,?,?,?)",
                (clean_name, defaults["unit"], 0, 0, 0, 0, defaults["stock_area"], defaults["order_category"]),
            )
            item_id = int(cur.lastrowid); item_real_name = clean_name; real_unit = defaults["unit"]
        parsed = {"task_type": "ORDER", "task_label": "Pedido", "confidence": 1.0, "intent_source": "manual_alta_articulo", "responsible": requested_by, "items": [{"name": item_real_name, "name_norm": _norm(item_real_name), "qty": qty, "unit": unit or real_unit, "matched_kind": "items", "matched_id": item_id, "match_confidence": 1.0}], "voice_text": voice_text, "needs_clarification": True, "created_missing_article": True}
        parsed_json = json.dumps(parsed, ensure_ascii=False)
        res = _add_one(cur, center_id=center_id, task_type="ORDER", item_name=item_real_name, item_norm=_norm(item_real_name), qty=qty, unit=unit or real_unit, requested_by=requested_by, source="operativa_alta_articulo", voice_text=voice_text, parsed_json=parsed_json, confidence=1.0, intent_source="manual_alta_articulo")
        cur.execute("UPDATE operational_queue_items SET decision_note=? WHERE id=?", ("Artículo creado desde Operativa y añadido al carrito como propuesta pendiente. Revisar proveedor/precio en Catálogo.", int(res.get("line_id") or 0)))
        conn.commit(); conn.close()
        return {"ok": True, "item_id": item_id, "item_name": item_real_name, "line_id": res.get("line_id"), "task_type": "ORDER", "message": "Artículo creado y añadido al carrito."}
    except Exception as exc:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"ok": False, "error": f"No se pudo crear artículo: {exc}"}


def interpret_operational_command(raw_text: str, forced_task_type: str = "AUTO") -> Dict[str, Any]:
    forced_task_type = str(forced_task_type or "AUTO").upper()
    raw_text = force_spanish_operational_text(raw_text)
    conn = db(); cur = conn.cursor(); ensure_operational_schema(cur)
    ctx = _fetch_context_candidates(cur, raw_text, forced_task_type)
    conn.close()
    ai = _try_ai_parse(raw_text, forced_task_type, ctx)
    parsed = ai or _local_parse_items(raw_text, forced_task_type)
    parsed = _apply_candidate_resolution(parsed, ctx)
    if forced_task_type in {"ORDER", "PRODUCTION", "WASTE"}:
        parsed["task_type"] = forced_task_type
        parsed["task_label"] = _TASK_LABELS.get(forced_task_type, forced_task_type)
    parsed["ai_configured"] = bool(os.environ.get("OPERATIVA_AI_MODE", "").lower() == "openai" and os.environ.get("OPENAI_API_KEY", "").strip())
    return parsed

def _token_like_match(cur: sqlite3.Cursor, table: str, item_name_norm: str, active_clause: str = "") -> tuple[int, str]:
    tokens = [t for t in _norm(item_name_norm).split() if len(t) > 1 and t not in {"de", "del", "la", "el", "los", "las"}]
    if not tokens:
        return 0, ""
    where = active_clause or "1=1"
    params: list[Any] = []
    for t in tokens[:5]:
        where += " AND lower(name) LIKE lower(?)"
        params.append(f"%{t}%")
    try:
        row = cur.execute(f"SELECT id,name FROM {table} WHERE {where} ORDER BY LENGTH(name) LIMIT 1", tuple(params)).fetchone()
        if row:
            return int(row["id"]), str(row["name"] or "")
    except Exception:
        pass
    return 0, ""


def _find_match(cur: sqlite3.Cursor, task_type: str, item_name_norm: str) -> tuple[int, str]:
    if not item_name_norm:
        return 0, ""
    like = f"%{item_name_norm}%"
    if task_type in {"PRODUCTION", "WASTE"}:
        try:
            row = cur.execute(
                "SELECT id,name FROM recipes WHERE COALESCE(is_active,1)=1 AND lower(name) LIKE lower(?) ORDER BY LENGTH(name) LIMIT 1",
                (like,),
            ).fetchone()
            if row:
                return int(row["id"]), str(row["name"] or "")
        except Exception:
            pass
        rid, rname = _token_like_match(cur, "recipes", item_name_norm, "COALESCE(is_active,1)=1")
        if rid:
            return rid, rname
    try:
        row = cur.execute(
            "SELECT id,name FROM items WHERE lower(name) LIKE lower(?) ORDER BY LENGTH(name) LIMIT 1",
            (like,),
        ).fetchone()
        if row:
            return int(row["id"]), str(row["name"] or "")
    except Exception:
        pass
    return _token_like_match(cur, "items", item_name_norm, "1=1")


def _add_one(cur: sqlite3.Cursor, *, center_id: int, task_type: str, item_name: str, item_norm: str, qty: float, unit: str,
             requested_by: str, source: str, voice_text: str, parsed_json: str, confidence: float, intent_source: str) -> Dict[str, Any]:
    ref_id, matched_name = _find_match(cur, task_type, item_norm)
    display_name = matched_name or item_name or "Sin identificar"
    display_norm = _norm(display_name)
    now = _now()
    existing = cur.execute(
        """
        SELECT * FROM operational_queue_items
         WHERE center_id=? AND task_type=? AND status IN ('REVIEW','DRAFT')
           AND item_name_norm=? AND unit=?
         ORDER BY id DESC LIMIT 1
        """,
        (int(center_id or 0), task_type, display_norm, unit),
    ).fetchone()
    if existing:
        line_id = int(existing["id"])
        old_qty = float(existing["qty_total"] or 0.0)
        new_qty = old_qty + float(qty or 0.0)
        decision_note = f"Ya existía en cola: {old_qty:g} {unit}. Nueva aportación: +{float(qty or 0):g} {unit}. Total propuesto: {new_qty:g} {unit}."
        cur.execute(
            "UPDATE operational_queue_items SET qty_total=?, updated_at=?, voice_text=COALESCE(voice_text,'') || ?, decision_note=?, confidence=?, intent_source=?, raw_json=? WHERE id=?",
            (new_qty, now, "\n" + str(voice_text or ""), decision_note, float(confidence or 0), intent_source, parsed_json, line_id),
        )
        merged = True
    else:
        cur.execute(
            """
            INSERT INTO operational_queue_items(center_id,task_type,item_name,item_name_norm,item_ref_id,qty_total,unit,status,requested_by,source,voice_text,notes,decision_note,created_at,updated_at,confidence,intent_source,raw_json)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (int(center_id or 0), task_type, display_name, display_norm, int(ref_id or 0), float(qty or 0.0), unit, "REVIEW", requested_by, source, voice_text, "", "Propuesta pendiente de validación humana.", now, now, float(confidence or 0), intent_source, parsed_json),
        )
        line_id = int(cur.lastrowid)
        merged = False
    cur.execute(
        """
        INSERT INTO operational_queue_contributions(line_id,requested_by,qty_requested,unit,voice_text,source,decision,created_at,raw_json)
        VALUES(?,?,?,?,?,?,?,?,?)
        """,
        (line_id, requested_by, float(qty or 0.0), unit, voice_text, source, "ADDED", now, parsed_json),
    )
    return {"line_id": line_id, "merged": merged, "task_type": task_type}


def add_operational_command(*, center_id: int, voice_text: str, requested_by: str = "", source: str = "voice", forced_task_type: str = "AUTO") -> Dict[str, Any]:
    parsed = interpret_operational_command(voice_text, forced_task_type)
    if not requested_by:
        requested_by = parsed.get("responsible") or ""
    if not str(requested_by or "").strip():
        return {"ok": False, "error": "Falta responsable. Di o escribe: Soy + nombre.", "parsed": parsed}
    task_type = parsed.get("task_type") or "ORDER"
    items = parsed.get("items") or []
    if not items:
        return {"ok": False, "error": "No detecté ningún artículo, receta o merma.", "parsed": parsed}
    # Para pedidos no guardamos coincidencias ambiguas, inexistentes ni sin cantidad.
    # Para producciones sí permitimos qty=0 como borrador pendiente: el usuario puede completar kg/raciones/lote después.
    if task_type in {"ORDER", "PRODUCTION"}:
        for it in items:
            if task_type == "ORDER":
                if it.get("matched_kind") == "none":
                    raw_missing = str(it.get("raw_name") or it.get("name") or "").strip().upper()
                    return {
                        "ok": False,
                        "error_code": "ARTICLE_NOT_FOUND",
                        "error": f"No encuentro ‘{raw_missing or 'este artículo'}’ en catálogo/stock. Para pedirlo primero debe existir como artículo.",
                        "missing_item": {"name": raw_missing, "qty": float(it.get("qty") or 0), "unit": str(it.get("unit") or "kg")},
                        "parsed": parsed,
                    }
                if it.get("ambiguous_match"):
                    return {"ok": False, "error_code": "AMBIGUOUS_MATCH", "error": "Hay coincidencias ambiguas. Selecciona o especifica mejor el producto o receta.", "parsed": parsed}
                if it.get("matched_kind") != "items":
                    return {"ok": False, "error_code": "ARTICLE_NOT_FOUND", "error": "Esto no está creado como artículo de stock/catálogo. No se puede pedir como línea normal hasta crearlo.", "missing_item": {"name": str(it.get("raw_name") or it.get("name") or "").strip().upper(), "qty": float(it.get("qty") or 0), "unit": str(it.get("unit") or "kg")}, "parsed": parsed}
                if float(it.get("qty") or 0) <= 0:
                    return {"ok": False, "error_code": "MISSING_QTY", "error": "Falta cantidad. Dicta o escribe cantidad y unidad.", "parsed": parsed}
            elif task_type == "PRODUCTION":
                # La producción puede quedar como borrador pendiente aunque falte cantidad o vínculo exacto;
                # no confirma stock y permite revisión humana dentro del módulo operativo.
                if it.get("matched_kind") == "none" or it.get("ambiguous_match"):
                    parsed["needs_clarification"] = True
    conn = db(); cur = conn.cursor(); ensure_operational_schema(cur)
    parsed_json = json.dumps(parsed, ensure_ascii=False)
    results = []
    for it in items:
        name = str(it.get("name") or "SIN IDENTIFICAR").strip().upper()
        norm = str(it.get("name_norm") or _norm(name))
        qty = float(it.get("qty") or 0.0)
        unit = str(it.get("unit") or "ud")
        results.append(_add_one(
            cur, center_id=center_id, task_type=task_type, item_name=name, item_norm=norm,
            qty=qty, unit=unit, requested_by=requested_by, source=source, voice_text=voice_text,
            parsed_json=parsed_json, confidence=float(parsed.get("confidence") or 0), intent_source=str(parsed.get("intent_source") or "rules")
        ))
    conn.commit(); conn.close()
    first = results[0] if results else {"line_id": 0, "merged": False, "task_type": task_type}
    return {"ok": True, "line_id": first.get("line_id"), "merged": any(r.get("merged") for r in results), "task_type": first.get("task_type"), "count": len(results), "parsed": parsed}


def list_operational_queue(center_id: int = 0, task_type: str = "") -> Dict[str, List[Dict[str, Any]]]:
    conn = db(); cur = conn.cursor(); ensure_operational_schema(cur)
    params: list[Any] = []
    where = "WHERE status IN ('REVIEW','DRAFT')"
    if int(center_id or 0) > 0:
        where += " AND center_id=?"; params.append(int(center_id or 0))
    if task_type:
        where += " AND task_type=?"; params.append(task_type)
    rows = cur.execute(
        f"SELECT * FROM operational_queue_items {where} ORDER BY updated_at DESC, id DESC LIMIT 200",
        tuple(params),
    ).fetchall()
    out = {"ORDER": [], "PRODUCTION": [], "WASTE": []}
    for r in rows:
        d = _dict_from_row(r)
        crows = cur.execute("SELECT * FROM operational_queue_contributions WHERE line_id=? ORDER BY id", (int(d["id"]),)).fetchall()
        d["contributions"] = [_dict_from_row(c) for c in crows]
        out.setdefault(str(d.get("task_type") or "ORDER"), []).append(d)
    conn.close()
    return out


def update_operational_line(line_id: int, action: str, qty_total: Optional[float] = None) -> None:
    conn = db(); cur = conn.cursor(); ensure_operational_schema(cur)
    action = (action or "").upper()
    if action == "CANCEL":
        cur.execute("UPDATE operational_queue_items SET status='CANCELLED', updated_at=? WHERE id=?", (_now(), int(line_id)))
    elif action == "VALIDATE":
        cur.execute("UPDATE operational_queue_items SET status='VALIDATED', updated_at=? WHERE id=?", (_now(), int(line_id)))
    elif action == "QTY" and qty_total is not None:
        cur.execute("UPDATE operational_queue_items SET qty_total=?, updated_at=? WHERE id=?", (float(qty_total or 0), _now(), int(line_id)))
    conn.commit(); conn.close()
