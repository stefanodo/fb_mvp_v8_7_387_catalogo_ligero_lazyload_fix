# ==============================================================================
# BLOQUE CORE · DB, utilidades compartidas y helpers globales
# ==============================================================================
import re
import sqlite3
import contextvars
import unicodedata
import os
import shutil
import csv
import time
import calendar
from pathlib import Path
import tempfile
from typing import Optional
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from difflib import SequenceMatcher

try:
    from PIL import Image, ImageOps
except Exception:
    Image = None
    ImageOps = None

try:
    from paddleocr import PaddleOCR  # type: ignore
except Exception:
    PaddleOCR = None

_PADDLE_OCR = None
APP_TZ = ZoneInfo("Europe/Madrid")

# ContextVar for per-request DB connection metrics: count and cumulative connect time
_DB_METRICS = contextvars.ContextVar('db_metrics', default={'count': 0, 'time': 0.0})

# --- Rutas de la aplicación ---
APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
USER_HOME = Path.home()
BUNDLED_RUNTIME_DIR = ROOT_DIR / "runtime"
_DEFAULT_SHARED_RUNTIME = USER_HOME / "Documents" / "F&B_MAC_RUNTIME"
_RUNTIME_ENV = os.getenv("FB_MVP_RUNTIME_DIR", "").strip()

# Resolve runtime directory with sensible fallbacks for read-only environments
if _RUNTIME_ENV:
    RUNTIME_DIR = Path(_RUNTIME_ENV).expanduser()
else:
    RUNTIME_DIR = _DEFAULT_SHARED_RUNTIME

try:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    # Fallback to the system temp directory when the default location is not writable
    try:
        tmp_base = Path(os.getenv("TMPDIR") or tempfile.gettempdir())
        tmp_runtime = tmp_base / "fb_mvp_runtime"
        tmp_runtime.mkdir(parents=True, exist_ok=True)
        RUNTIME_DIR = tmp_runtime
    except Exception:
        # As a last resort, use the bundled runtime location inside the repo
        RUNTIME_DIR = BUNDLED_RUNTIME_DIR
BUNDLED_DB_PATH = BUNDLED_RUNTIME_DIR / "fb_mvp_v8.db"
DB_PATH = RUNTIME_DIR / "fb_mvp_v8.db"
try:
    if not DB_PATH.exists() and BUNDLED_DB_PATH.exists():
        try:
            shutil.copy2(BUNDLED_DB_PATH, DB_PATH)
        except Exception:
            pass
except Exception:
    pass

UPLOADS_DIR = RUNTIME_DIR / "uploads"
try:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass
SEED_DIR = APP_DIR / "data"
SEED_ITEMS_CSV = SEED_DIR / "seed_items_152.csv"
SEED_PRICES_CSV = SEED_DIR / "seed_prices_35.csv"

BUILD_ID = "v8_7_387_catalogo_ligero_lazyload_fix"

# --- Constantes de negocio ---
CATEGORY_CODES = {
    "Entrantes": "ENT", "Principales": "PRI", "Postres": "POS",
    "Ensaladas": "ENS", "Guarniciones": "GUA", "Salsas": "SAL",
    "Bases": "BAS", "Preelaborados": "PRE", "Bebidas": "BEB", "Otros": "OTR",
}
SUBCATEGORIES = ["Sin definir", "Frío", "Caliente", "Salsas", "Guarniciones",
                 "Postres", "Otros", "Carne", "Pescado", "Vegetariano",
                 "Cocina Central", "Barra"]
ALLERGENS_UE = [
    ("gluten", "🌾", "Gluten"), ("crustaceos", "🦐", "Crustáceos"),
    ("huevo", "🥚", "Huevo"), ("pescado", "🐟", "Pescado"),
    ("cacahuete", "🥜", "Cacahuete"), ("soja", "🫘", "Soja"),
    ("leche", "🥛", "Leche"), ("frutos_cascara", "🌰", "Frutos de cáscara"),
    ("apio", "🥬", "Apio"), ("mostaza", "🟡", "Mostaza"),
    ("sesamo", "⚪", "Sésamo"), ("sulfitos", "🍷", "Sulfitos"),
    ("altramuces", "🌼", "Altramuces"), ("moluscos", "🦪", "Moluscos"),
]


# ==============================================================================
# BASE DE DATOS
# ==============================================================================

def db():
    try:
        # Prefer centralized connection factory which selects PostgreSQL
        # when `DATABASE_URL` is present, otherwise returns a configured
        # sqlite3 connection. This avoids duplicate pragma/connection logic
        # spread across the codebase.
        from app.db_config import get_db_connection
        # Track per-request DB connection metrics using a ContextVar so the
        # home() handler can report aggregated connect times without relying
        # on external logging.
        _db_metrics = _DB_METRICS
        t0 = time.time()
        conn = get_db_connection()
        elapsed = time.time() - t0
        try:
            m = _db_metrics.get()
            m2 = {'count': int(m.get('count', 0)) + 1, 'time': float(m.get('time', 0.0)) + elapsed}
            _db_metrics.set(m2)
        except Exception:
            pass
        return conn
    except Exception:
        # Fallback: local sqlite connection (keeps previous behavior when
        # `app.db_config` is not available for any reason).
        conn = sqlite3.connect(DB_PATH, timeout=240, isolation_level="DEFERRED", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # Apply centralized sqlite pragmas when available (keeps PRAGMA usage in one place)
        try:
            try:
                from app.db_config import ensure_sqlite_pragmas as _ensure_pragmas
            except Exception:
                _ensure_pragmas = None
            if _ensure_pragmas:
                try:
                    _ensure_pragmas(conn)
                except Exception:
                    pass
            else:
                for pragma in ["PRAGMA journal_mode=WAL", "PRAGMA synchronous=NORMAL", "PRAGMA busy_timeout=240000"]:
                    try:
                        conn.execute(pragma)
                    except Exception:
                        pass
        except Exception:
            pass
        return conn


def _is_db_locked_error(exc: Exception) -> bool:
    try:
        return "locked" in str(exc).lower()
    except Exception:
        return False


def _retry_db_write(write_fn, attempts: int = 10, delay: float = 0.45):
    last_exc = None
    for attempt in range(attempts):
        conn = db()
        try:
            cur = conn.cursor()
            try:
                cur.execute("BEGIN IMMEDIATE")
            except Exception:
                pass
            result = write_fn(conn, cur)
            conn.commit()
            conn.close()
            return result
        except sqlite3.OperationalError as exc:
            last_exc = exc
            try:
                conn.rollback()
            except Exception:
                pass
            conn.close()
            if (not _is_db_locked_error(exc)) or attempt >= attempts - 1:
                raise
            time.sleep(delay * (attempt + 1))
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            conn.close()
            raise
    if last_exc:
        raise last_exc


# ==============================================================================
# DB-AGNOSTIC HELPERS
# ==============================================================================

def get_last_insert_id(cur) -> int:
    """Return the last inserted id in a DB-agnostic way.

    Tries, in order:
    - `cur.lastrowid` (sqlite3 cursor or PG adapter)
    - `SELECT LASTVAL()` on a new cursor connected to the same connection
    Raises RuntimeError if unable to determine an id.
    """
    try:
        lr = getattr(cur, "lastrowid", None)
        if lr is not None:
            return int(lr)
    except Exception:
        pass
    try:
        # Try to derive connection object for auxiliary query
        conn = None
        if hasattr(cur, "connection"):
            conn = cur.connection
        elif hasattr(cur, "_cursor") and hasattr(cur._cursor, "connection"):
            conn = cur._cursor.connection
        elif hasattr(cur, "_conn"):
            conn = cur._conn
        if conn is not None:
            aux = conn.cursor()
            try:
                aux.execute('SELECT LASTVAL()')
                last = aux.fetchone()
                if last:
                    if isinstance(last, dict):
                        for v in last.values():
                            try:
                                return int(v)
                            except Exception:
                                continue
                    elif isinstance(last, (list, tuple)):
                        return int(last[0])
                    else:
                        return int(last)
            finally:
                try:
                    aux.close()
                except Exception:
                    pass
    except Exception:
        pass
    raise RuntimeError("Could not determine last insert id")


def get_table_columns_from_cursor(cur_or_conn, table_name: str):
    """Return a set of column names for `table_name` using the provided
    sqlite3 cursor/connection or the Postgres adapter cursor/connection.
    """
    try:
        cur = cur_or_conn.cursor() if hasattr(cur_or_conn, "cursor") and callable(getattr(cur_or_conn, "cursor")) else cur_or_conn
        # Postgres path
        if getattr(cur, "_is_postgres", False):
            try:
                cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s", (table_name,))
                rows = cur.fetchall()
                cols = set()
                for r in rows:
                    try:
                        if isinstance(r, dict):
                            cols.add(r.get("column_name") or list(r.values())[0])
                        else:
                            cols.add(r[0])
                    except Exception:
                        continue
                return cols
            except Exception:
                return set()
        # SQLite path
        try:
            cur.execute(f"PRAGMA table_info({table_name})")
            rows = cur.fetchall()
            cols = set()
            for r in rows:
                try:
                    # sqlite Row: name at key 'name'
                    cols.add(r["name"])
                except Exception:
                    try:
                        # fallback sequence access: name at index 1
                        cols.add(r[1])
                    except Exception:
                        continue
            return cols
        except Exception:
            return set()
    except Exception:
        return set()


def table_exists(cur_or_conn, table_name: str) -> bool:
    """Return True if `table_name` exists in the connected database (Postgres or SQLite)."""
    try:
        cur = cur_or_conn.cursor() if hasattr(cur_or_conn, "cursor") and callable(getattr(cur_or_conn, "cursor")) else cur_or_conn
        if getattr(cur, "_is_postgres", False):
            try:
                cur.execute("SELECT 1 FROM information_schema.tables WHERE table_name=%s", (table_name,))
                return cur.fetchone() is not None
            except Exception:
                return False
        try:
            cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
            return cur.fetchone() is not None
        except Exception:
            return False
    except Exception:
        return False


def db_truthy_sql(column: str, cur_or_conn=None) -> str:
    """Return a DB-agnostic SQL expression that evaluates truthiness for `column`.

    - For Postgres (boolean columns) returns: `(column IS NULL OR column = TRUE)`
    - For SQLite (integer 0/1 or NULL) returns: `COALESCE(column,1)=1`

    The optional `cur_or_conn` argument may be a cursor/connection with the
    `_is_postgres` attribute set by the PG adapter. If omitted, a SQLite-style
    expression is returned for maximum compatibility.
    """
    try:
        # Use a resilient text-based check that works for boolean or integer
        # columns across Postgres and SQLite. Treat NULL as truthy to preserve
        # the original semantics (NULL => show/enable).
        return f"COALESCE(LOWER(CAST({column} AS TEXT)),'1') IN ('1','t','true')"
    except Exception:
        return f"COALESCE({column},1)=1"


def db_coalesce_text(*columns: str, cur_or_conn=None) -> str:
    """Return a COALESCE expression that casts operands to text on Postgres.

    Usage: db_coalesce_text('r.doc_date', 'r.validated_at', cur)
    """
    try:
        cur = None
        if cur_or_conn is not None:
            cur = cur_or_conn.cursor() if hasattr(cur_or_conn, "cursor") and callable(getattr(cur_or_conn, "cursor")) else cur_or_conn
        if cur is not None and getattr(cur, "_is_postgres", False):
            parts = [f"CAST({c} AS TEXT)" for c in columns]
            return "COALESCE(" + ", ".join(parts) + ")"
    except Exception:
        pass
    return "COALESCE(" + ", ".join(columns) + ")"


def safe_insert_returning(cur, sqlite_sql: str, params: tuple = (), pg_sql: Optional[str] = None):
    """Execute an INSERT in a DB-agnostic way and return the inserted id when available.

    - On Postgres: uses `pg_sql` if provided, otherwise converts qmark-style `sqlite_sql` to
      `%s` placeholders, ensures a `RETURNING id` clause and attempts to return the id.
    - On SQLite: executes `sqlite_sql` and returns `get_last_insert_id(cur)`.

    Returns `int` id on success or `None` when it cannot be determined.
    """
    try:
        # Postgres path
        if getattr(cur, "_is_postgres", False):
            sql = pg_sql or sqlite_sql.replace("?", "%s")
            if "RETURNING" not in sql.upper():
                sql = sql + " RETURNING id"
            try:
                cur.execute(sql, params)
                row = cur.fetchone()
                if row:
                    if isinstance(row, dict):
                        val = row.get("id") or (list(row.values())[0] if row else None)
                    else:
                        val = row[0] if isinstance(row, (list, tuple)) else row
                    return int(val) if val is not None else None
            except Exception:
                # Fallback: try a non-returning insert then derive the id
                try:
                    sql_no_returning = sql
                    if " RETURNING " in sql_no_returning.upper():
                        sql_no_returning = sql_no_returning.rsplit(" RETURNING ", 1)[0]
                    cur.execute(sql_no_returning, params)
                except Exception:
                    pass
                try:
                    return get_last_insert_id(cur)
                except Exception:
                    return None

        # SQLite path
        cur.execute(sqlite_sql, params)
        try:
            return get_last_insert_id(cur)
        except Exception:
            return None
    except Exception:
        try:
            cur.execute(sqlite_sql, params)
            return get_last_insert_id(cur)
        except Exception:
            return None


# ==============================================================================
# UTILIDADES DE FORMATO
# ==============================================================================

def _parse_float(v, default: float = 0.0) -> float:
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return default


def fmt_num(v: float, decimals: int = 3) -> str:
    try:
        f = float(v)
    except Exception:
        return str(v or "")
    s = f"{f:.{decimals}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def fmt_price(v: float, decimals: int = 2) -> str:
    return fmt_num(v, decimals)


def _cache_bust_token() -> str:
    return str(int(time.time() * 1000))


def _norm_text(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _norm_name(s: str) -> str:
    return _norm_text(s)


def _item_key(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip()).lower()


def upper_name(value: str) -> str:
    return (value or "").strip().upper()


def fmt_dt(value: str) -> str:
    s = (value or "").strip()
    if not s:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        try:
            return datetime.strptime(s, "%Y-%m-%d").strftime("%d/%m/%Y")
        except Exception:
            return s
    try:
        raw = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(APP_TZ).strftime("%d/%m/%Y %H:%M")
    except Exception:
        try:
            dt = datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
            return dt.replace(tzinfo=timezone.utc).astimezone(APP_TZ).strftime("%d/%m/%Y %H:%M")
        except Exception:
            return s


def status_label(status: str) -> str:
    return {"DRAFT": "BORRADOR", "CONFIRMED": "CONFIRMADO", "PENDING": "BORRADOR",
            "CANCELED": "CANCELADO", "ARCHIVED": "ARCHIVADO"}.get(
        (status or "").strip(), (status or "").strip())


def _ocr_state_label(state: str) -> str:
    return {"READY": "Listo para revisar", "PENDING": "Pendiente", "EMPTY": "Sin fotos",
            "ERROR": "Con incidencias", "READ": "Leído para revisar"}.get(
        (state or "").strip(), state or "-")


# ==============================================================================
# UNIDADES Y PRECIOS
# ==============================================================================

def normalize_price_to_base(price: float, base_unit: str, input_unit: str) -> float:
    """Normaliza precio por unidad de compra a precio por unidad base.
    Directriz operativa: los líquidos se gestionan también por peso (g/kg),
    usando equivalencia 1 l = 1 kg y 1 ml = 1 g.
    """
    base_unit = (base_unit or "").strip().lower()
    input_unit = (input_unit or base_unit or "").strip().lower()
    price = float(price or 0)
    if base_unit in ("g", "kg"):
        if input_unit in ("kg", "l"):
            return price / 1000.0 if base_unit == "g" else price
        if input_unit in ("g", "ml"):
            return price * 1000.0 if base_unit == "kg" else price
    if base_unit == "ud":
        return price
    return price


def preferred_price_unit(base_unit: str) -> str:
    return {"g": "kg", "kg": "kg", "ud": "ud"}.get((base_unit or "").strip().lower(), (base_unit or "").strip().lower())


def display_price_from_base(current_price: float, base_unit: str) -> float:
    base_unit = (base_unit or "").strip().lower()
    p = float(current_price or 0)
    if base_unit == "g":
        return p * 1000.0
    return p


def _unit_factor(input_unit: str, base_unit: str) -> float:
    iu = (input_unit or base_unit or "").lower().strip()
    bu = (base_unit or "").lower().strip()
    if not iu or not bu:
        return 1.0
    if iu == bu:
        return 1.0
    # Política operativa del sistema: líquidos también por peso.
    # Equivalencias aceptadas: 1 ml = 1 g, 1 l = 1 kg.
    aliases_to_g = {"g", "gr", "gramo", "gramos", "ml"}
    aliases_to_kg = {"kg", "kilo", "kilos", "l", "lt", "lts", "litro", "litros"}
    if bu in {"g", "kg"}:
        if iu in aliases_to_g:
            return 1.0 if bu == "g" else 0.001
        if iu in aliases_to_kg:
            return 1000.0 if bu == "g" else 1.0
    if bu in {"manojo", "manojos"}:
        return 1.0 if iu in {"manojo", "manojos"} else 1.0
    if bu == "ud":
        return 1.0 if iu == "ud" else 1.0
    return 1.0




def normalize_minmax_qty_for_base(value, base_unit: str):
    """Corrige min/max antiguos guardados en gramos después de migrar el artículo a kg.
    Si el artículo opera en kg y el min/max es absurdamente alto para un restaurante,
    se interpreta como gramos heredados y se divide por 1000.
    Ej.: 20000 en artículo kg => 20 kg.
    """
    try:
        v = float(value or 0.0)
    except Exception:
        return 0.0
    bu = (base_unit or '').strip().lower()
    if bu == 'kg' and abs(v) >= 1000.0:
        return v / 1000.0
    return v


def normalize_minmax_pair_for_base(min_qty, max_qty, base_unit: str):
    return (
        normalize_minmax_qty_for_base(min_qty, base_unit),
        normalize_minmax_qty_for_base(max_qty, base_unit),
    )

def _factor_for_units(input_unit: str, base_unit: str) -> float:
    return _unit_factor(input_unit, base_unit)


def get_unit_factor(input_unit: str, base_unit: str) -> float:
    return _unit_factor(input_unit, base_unit)


def _canonical_unit(unit: str) -> str:
    u = (unit or "").strip().lower()
    if u in ("g", "kg", "gr", "gramo", "gramos", "ml", "l", "lt", "lts", "litro", "litros"):
        return "g"
    if u in ("ud", "u", "unidad", "unidades"):
        return "ud"
    if u in ("manojo", "manojos", "atado", "atados"):
        return "manojo"
    if u in {"racion", "raciones"}:
        return "raciones"
    if u in {"porcion", "porciones"}:
        return "porciones"
    return u or "ud"


def _guess_unit_family(unit: str) -> str:
    u = (unit or "").strip().lower()
    if u in ("g", "kg", "gr", "gramo", "gramos", "ml", "l", "lt", "lts", "litro", "litros"):
        return "peso"
    return "unidad"


def preferred_display_qty(qty: float, unit: str) -> tuple:
    try:
        q = float(qty or 0)
    except Exception:
        return qty, (unit or "").strip()
    u = (unit or "").strip().lower()
    if u == "g" and abs(q) >= 1000:
        return q / 1000.0, "kg"
    return q, "g" if u in {"ml", "l"} else (u or (unit or ""))


def human_qty(qty: float, unit: str) -> str:
    try:
        q = float(qty or 0)
    except Exception:
        return f"{qty} {unit}".strip()
    u = (unit or "").strip().lower()
    if u in {"ml", "l"}:
        u = "g"
        if unit == "l":
            q *= 1000.0
    sign = -1 if q < 0 else 1
    q = abs(q)
    if u == "g" and q >= 1000:
        return f"{fmt_num(sign*q/1000.0, 2)} kg"
    if u == "g":
        if q >= 10:
            rounded = round(sign * q, 1)
            return f"{fmt_num(rounded, 1)} g"
        rounded = round(sign * q, 2)
        return f"{fmt_num(rounded, 2)} g"
    return f"{fmt_num(sign*q, 2)} {u}".strip()


def _movement_signed_qty(movement_type: str, qty: float) -> float:
    mt = (movement_type or "").upper().strip()
    if mt in {"ENTRADA", "IN"}:
        return float(qty)
    return -float(qty)


def _convert_qty(qty: float, from_unit: str, to_unit: str) -> float:
    try:
        return float(qty or 0.0) * float(_unit_factor(from_unit, to_unit))
    except Exception:
        return float(qty or 0.0)


# ==============================================================================
# ARTÍCULOS Y MERMAS
# ==============================================================================

def suggest_item_waste_pct(name: str, unit: str = "") -> float:
    nm = upper_name(name or "")
    u = (unit or "").strip().lower()
    if not nm:
        return 0.0
    if u == "ud" and any(k in nm for k in ["HUEVO", "LIMON", "LIMA", "AGUACATE", "MANZANA", "NARANJA"]):
        return 0.0
    zero_kw = ["SAL", "AZUCAR", "AZÚCAR", "PIMIENTA", "ESPECIA", "VINAGRE", "ACEITE",
               "AGUA", "HARINA", "ARROZ", "PASTA SECA", "TOMATE LATA", "CONCENTRADO",
               "PURE", "PURÉ", "CALDO", "QUESO", "MANTEQUILLA", "NATA", "LECHE", "YOGUR"]
    if any(k in nm for k in zero_kw):
        return 0.0
    if any(k in nm for k in ["FILETE", "LOMO LIMPIO", "PELADO", "LIMPIO", "DESHUESADO"]):
        return 0.0
    if any(k in nm for k in ["PESCADO ENTERO", "DORADA", "LUBINA", "MERLUZA ENTERA", "RAPE"]):
        return 45.0
    if any(k in nm for k in ["POLLO ENTERO", "COSTILLAR", "PALETILLA", "CARRILLERA"]):
        return 18.0
    if any(k in nm for k in ["CEBOLLA", "PUERRO", "APIO", "ZANAHORIA", "AJO", "PIMIENTO", "PATATA"]):
        return 12.0
    if any(k in nm for k in ["GAMBA ENTERA", "LANGOSTINO ENTERO", "MARISCO ENTERO"]):
        return 35.0
    return 0.0


def _resolve_item_id(cur, item_id, item_query: str):
    if item_id is not None and str(item_id).strip() != "":
        try:
            return int(item_id)
        except Exception:
            pass
    q = (item_query or "").strip()
    if not q:
        return None
    m = re.search(r"\[#(\d+)\]", q)
    if m:
        return int(m.group(1))
    name = re.sub(r"\s*\[.*\]\s*$", "", q).strip()
    if not name:
        return None
    row = cur.execute("SELECT id FROM items WHERE lower(name)=lower(?)", (name,)).fetchone()
    if row:
        return int(row["id"])
    row = cur.execute("SELECT id FROM items WHERE lower(name) LIKE lower(?) ORDER BY name LIMIT 1",
                      (name + "%",)).fetchone()
    if row:
        return int(row["id"])
    return None


def _resolve_item_id_strict(cur, item_id, item_query: str):
    if item_id is not None and str(item_id).strip() != "":
        try:
            return int(item_id)
        except Exception:
            return None
    q = (item_query or "").strip()
    if not q:
        return None
    m = re.search(r"\[#(\d+)\]", q)
    if m:
        return int(m.group(1))
    name = re.sub(r"\s*\[.*\]\s*$", "", q).strip()
    if not name:
        return None
    row = cur.execute("SELECT id FROM items WHERE lower(name)=lower(?)", (name,)).fetchone()
    if row:
        return int(row["id"])
    return None


# ==============================================================================
# PROVEEDORES
# ==============================================================================

def _supplier_columns(cur) -> set:
    return set(get_table_columns_from_cursor(cur, "suppliers"))


def _ensure_pending_supplier(cur) -> int:
    row = cur.execute(
        "SELECT id FROM suppliers WHERE lower(name)=lower(?) ORDER BY id LIMIT 1",
        ("Proveedor pendiente OCR",)).fetchone()
    if row:
        return int(row["id"])
    cols = _supplier_columns(cur)
    if "tax_id" in cols and "address" in cols:
        cur.execute(
            "INSERT INTO suppliers(name,phone,email,tax_id,address,is_active) VALUES(?,?,?,?,?,1)",
            ("Proveedor pendiente OCR", None, None, None, None))
    else:
        cur.execute("INSERT INTO suppliers(name,is_active) VALUES(?,1)", ("Proveedor pendiente OCR",))
    return get_last_insert_id(cur)


def _cleanup_pending_supplier(cur) -> None:
    row = cur.execute(
        "SELECT id FROM suppliers WHERE lower(name)=lower(?) ORDER BY id LIMIT 1",
        ("Proveedor pendiente OCR",)).fetchone()
    if not row:
        return
    pending_id = int(row["id"])
    cur.execute("UPDATE suppliers SET is_active=0 WHERE id=?", (pending_id,))


def _insert_supplier_compatible(cur, name: str, is_active: int = 1, phone=None, email=None,
                                 tax_id=None, address=None) -> int:
    cols = _supplier_columns(cur)
    now = datetime.utcnow().isoformat()
    payload = {"name": (name or "").strip()[:120], "phone": phone, "email": email,
               "tax_id": tax_id, "address": address, "is_active": int(is_active), "created_at": now}
    ordered_cols = [c for c in ["name", "phone", "email", "tax_id", "address", "is_active", "created_at"]
                    if c in cols]
    placeholders = ",".join(["?"] * len(ordered_cols))
    cur.execute(f"INSERT INTO suppliers({','.join(ordered_cols)}) VALUES({placeholders})",
                tuple(payload[c] for c in ordered_cols))
    return get_last_insert_id(cur)


def _resolve_supplier_id_by_name(cur, supplier_name: str):
    name = (supplier_name or "").strip()
    if not name:
        return None, None
    row = cur.execute("SELECT id,name FROM suppliers WHERE lower(name)=lower(?) AND is_active=1 ORDER BY id LIMIT 1",
                      (name,)).fetchone()
    if row:
        return int(row["id"]), row["name"]
    row = cur.execute(
        "SELECT id,name FROM suppliers WHERE lower(name) LIKE lower(?) AND is_active=1 ORDER BY id LIMIT 1",
        (f"%{name}%",)).fetchone()
    if row:
        return int(row["id"]), row["name"]
    return None, None


def _provider_has_links(cur, provider_id: int) -> bool:
    for table in ("receipts", "order_lines", "supplier_item_prices"):
        row = cur.execute(f"SELECT 1 FROM {table} WHERE supplier_id=? LIMIT 1", (provider_id,)).fetchone()
        if row:
            return True
    return False


def _provider_archive_name(name: str) -> str:
    base = (name or "").strip()
    suffix = " [ARCHIVADO]"
    if base.endswith(suffix):
        return base
    return (base + suffix)[:120]


def _suggest_supplier_id(cur, center_id: int, item_id: int):
    try:
        row = cur.execute(
            """SELECT supplier_id FROM supplier_item_prices
               WHERE item_id=? AND is_preferred=1 AND (center_id IS NULL OR center_id=?)
               ORDER BY CASE WHEN center_id=? THEN 0 ELSE 1 END, updated_at DESC LIMIT 1""",
            (int(item_id), int(center_id), int(center_id))).fetchone()
        if row and row["supplier_id"]:
            return int(row["supplier_id"])
        row = cur.execute(
            """SELECT supplier_id FROM supplier_item_prices
               WHERE item_id=? AND (center_id IS NULL OR center_id=?)
               ORDER BY CASE WHEN center_id=? THEN 0 ELSE 1 END, price_per_purchase ASC, updated_at DESC LIMIT 1""",
            (int(item_id), int(center_id), int(center_id))).fetchone()
        if row and row["supplier_id"]:
            return int(row["supplier_id"])
    except Exception:
        return None
    return None


def _supplier_options_for_item(cur, center_id: int, item_id: int):
    rows = cur.execute(
        """SELECT sp.supplier_id, s.name supplier_name, sp.price_per_purchase,
                  sp.purchase_unit, sp.purchase_to_base_factor, sp.is_preferred,
                  sp.updated_at, sp.center_id
             FROM supplier_item_prices sp
             JOIN suppliers s ON s.id=sp.supplier_id
            WHERE sp.item_id=? AND (sp.center_id IS NULL OR sp.center_id=?)
            ORDER BY CASE WHEN sp.center_id=? THEN 0 ELSE 1 END, sp.is_preferred DESC, sp.updated_at DESC""",
        (int(item_id), int(center_id), int(center_id))).fetchall()
    best = {}
    for r in rows:
        sid = int(r["supplier_id"])
        if sid not in best:
            best[sid] = {k: r[k] for k in r.keys()}
    opts = list(best.values())

    def norm_price(o):
        try:
            fac = float(o.get("purchase_to_base_factor") or 1.0)
            return float(o.get("price_per_purchase") or 0.0) / max(fac, 0.0001)
        except Exception:
            return 0.0

    opts.sort(key=lambda o: (0 if int(o.get("is_preferred") or 0) == 1 else 1,
                              norm_price(o), (o.get("supplier_name") or "").lower()))
    return opts


def _supplier_factor_for_item(cur, center_id: int, supplier_id: int, item_id: int,
                               input_unit: str, base_unit: str) -> float:
    try:
        row = cur.execute(
            """SELECT purchase_unit, purchase_to_base_factor FROM supplier_item_prices
               WHERE supplier_id=? AND item_id=? AND (center_id=? OR center_id IS NULL)
               ORDER BY CASE WHEN center_id=? THEN 0 ELSE 1 END, updated_at DESC LIMIT 1""",
            (int(supplier_id), int(item_id), int(center_id), int(center_id))).fetchone()
        if row:
            fac = float(row["purchase_to_base_factor"] or 0)
            pu = (row["purchase_unit"] or "").lower().strip()
            iu = (input_unit or "").lower().strip()
            if fac > 0 and (not pu or pu == iu):
                return fac
    except Exception:
        pass
    return _unit_factor(input_unit, base_unit)


# ==============================================================================
# RECETAS
# ==============================================================================

def _parse_scope(scope_global_raw, scope_centers_raw):
    scope_global = 1 if str(scope_global_raw or "").lower() in {"1", "on", "true", "yes"} else 0
    center_ids = []
    for v in (scope_centers_raw or []):
        sv = str(v).strip()
        if sv.isdigit():
            center_ids.append(int(sv))
    center_ids = sorted(set(center_ids))
    if scope_global:
        return 1, ""
    return 0, ",".join(str(x) for x in center_ids)


def recipe_visible_in_center(rec, center_id):
    if not rec:
        return False
    if not center_id:
        return True
    try:
        if int(rec["scope_global"] or 0) == 1:
            return True
    except Exception:
        return True
    scope_centers = str(rec["scope_centers"] or "")
    parts = {int(x) for x in scope_centers.split(",") if str(x).strip().isdigit()}
    return int(center_id) in parts


def next_recipe_code(cur, category: str):
    prefix = CATEGORY_CODES.get(category, "REC")
    row = cur.execute("SELECT COUNT(*) c FROM recipes WHERE category=?", (category,)).fetchone()
    seq = (row["c"] or 0) + 1
    return f"REC-{prefix}-{seq:04d}"


def recipe_with_calc(cur, recipe_id: int):
    rec = cur.execute("SELECT * FROM recipes WHERE id=?", (recipe_id,)).fetchone()
    if not rec:
        return None
    ing_rows = cur.execute("SELECT * FROM recipe_ingredients WHERE recipe_id=? ORDER BY id",
                           (recipe_id,)).fetchall()
    cost_supplier_id = int(rec["cost_supplier_id"] or 0)
    cost_base = 0.0
    ingredients = []

    def _is_weight_family(unit: str) -> bool:
        return _canonical_unit(unit or "") == "g"

    for r in ing_rows:
        item_id = int(r["item_id"] or 0)
        subrecipe_id = int(r["subrecipe_id"] or 0)
        unit_cost = 0.0
        unit_cost_source = ""
        stored_unit = (r["unit"] or "ud").strip() or "ud"
        input_unit = (r["input_unit"] or stored_unit).strip() or stored_unit
        effective_base_unit = _canonical_unit(stored_unit)

        item_row = None
        sub = None
        if subrecipe_id:
            sub = cur.execute("SELECT * FROM recipes WHERE id=?", (subrecipe_id,)).fetchone()
            if sub:
                raw_sub_unit = (sub["yield_final_unit"] if "yield_final_unit" in sub.keys() else None) or stored_unit or "g"
                effective_base_unit = _canonical_unit(raw_sub_unit)
                sub_calc = recipe_with_calc(cur, subrecipe_id)
                sub_payload = sub_calc or {}
                sub_calc_map = sub_payload.get("calc", {}) or {}
                sub_base_cost = float(sub_calc_map.get("cost_base", 0.0) or 0.0)
                sub_yield_qty = float(sub_payload.get("yield_final_qty", 0.0) or 0.0)
                if sub_yield_qty > 0:
                    if raw_sub_unit and effective_base_unit and raw_sub_unit != effective_base_unit:
                        try:
                            sub_yield_qty = float(_convert_qty(sub_yield_qty, raw_sub_unit, effective_base_unit))
                        except Exception:
                            pass
                    unit_cost = sub_base_cost / sub_yield_qty
                    unit_cost_source = "coste_subreceta"
                else:
                    sub_portions = float(sub_calc_map.get("yield_portions", 0.0) or 0.0)
                    unit_cost = (sub_base_cost / sub_portions) if sub_portions > 0 else 0.0
                    unit_cost_source = "coste_subreceta"
        elif item_id:
            item_row = cur.execute("SELECT id,unit,current_price FROM items WHERE id=?", (item_id,)).fetchone()
            raw_item_unit = (item_row["unit"] if item_row and item_row["unit"] else stored_unit) or stored_unit
            effective_base_unit = _canonical_unit(raw_item_unit)
            if cost_supplier_id:
                sp = cur.execute(
                    """SELECT price_per_purchase, purchase_to_base_factor FROM supplier_item_prices
                       WHERE supplier_id=? AND item_id=? ORDER BY updated_at DESC LIMIT 1""",
                    (cost_supplier_id, item_id)).fetchone()
                if sp:
                    fac = float(sp["purchase_to_base_factor"] or 1.0)
                    unit_cost = float(sp["price_per_purchase"] or 0.0) / max(fac, 0.0001)
                    unit_cost_source = "proveedor"
                else:
                    unit_cost = float(item_row["current_price"] or 0.0) if item_row else 0.0
                    unit_cost_source = "precio_actual"
            else:
                unit_cost = float(item_row["current_price"] or 0.0) if item_row else 0.0
                unit_cost_source = "precio_actual"
            if raw_item_unit and effective_base_unit and raw_item_unit != effective_base_unit:
                try:
                    unit_cost = float(normalize_price_to_base(unit_cost, effective_base_unit, raw_item_unit))
                except Exception:
                    pass

        qty_gross = float(r["qty_gross"] or 0.0)
        qty_net = float(r["qty_net"] or 0.0)
        if stored_unit and effective_base_unit and stored_unit != effective_base_unit:
            try:
                qty_gross = float(_convert_qty(qty_gross, stored_unit, effective_base_unit))
                qty_net = float(_convert_qty(qty_net, stored_unit, effective_base_unit))
            except Exception:
                pass
        cost_qty = qty_net if subrecipe_id else qty_gross
        line_cost = cost_qty * unit_cost
        cost_base += line_cost
        display_unit = input_unit or effective_base_unit
        display_qty = qty_net
        gross_disp = qty_gross
        net_disp = qty_net
        if effective_base_unit and display_unit and effective_base_unit != display_unit:
            try:
                display_qty = float(_convert_qty(qty_net, effective_base_unit, display_unit))
                gross_disp = float(_convert_qty(qty_gross, effective_base_unit, display_unit))
                net_disp = float(_convert_qty(qty_net, effective_base_unit, display_unit))
            except Exception:
                display_unit = effective_base_unit
                display_qty = qty_net
                gross_disp = qty_gross
                net_disp = qty_net
        if _is_weight_family(effective_base_unit) and _is_weight_family(display_unit):
            display_unit = (display_unit or "").strip().lower() or (input_unit or effective_base_unit)
        ing_d = {k: r[k] for k in r.keys()}
        ing_d["unit"] = effective_base_unit
        ing_d["input_unit"] = display_unit
        ing_d["unit_cost"] = unit_cost
        ing_d["unit_cost_source"] = unit_cost_source
        ing_d["line_cost"] = line_cost
        ing_d["display_qty"] = display_qty
        ing_d["display_gross"] = gross_disp
        ing_d["display_net"] = net_disp
        ingredients.append(ing_d)

    waste_pct = float(rec["waste_pct"] or 0.0)
    contingency_pct = float(rec["contingency_pct"] or 0.0)
    yield_portions = max(float(rec["yield_portions"] or 1.0), 0.0001)
    target_food_cost_pct = float(rec["target_food_cost_pct"] or 30.0)
    target_margin_pct = float(rec["target_margin_pct"] or 70.0)
    manual_price = float(rec["manual_price"] or 0.0)
    cost_adjusted = cost_base * (1 + contingency_pct / 100.0)
    cost_per_portion = cost_adjusted / yield_portions
    price_ex_vat = (cost_per_portion / (target_food_cost_pct / 100.0)) if target_food_cost_pct > 0 else 0.0
    price_vat = price_ex_vat * 0.10
    price_inc_vat = price_ex_vat * 1.10
    suggested_ex_vat = manual_price if manual_price > 0 else price_ex_vat
    suggested_inc_vat = suggested_ex_vat * 1.10
    food_cost_real_pct = (cost_per_portion / suggested_ex_vat * 100.0) if suggested_ex_vat > 0 else 0.0

    # Mano de obra: cálculo operativo separado. NO modifica food cost ni materia prima.
    prep_time_min = float(rec["prep_time_min"] or 0.0) if "prep_time_min" in rec.keys() else 0.0
    cook_time_min = float(rec["cook_time_min"] or 0.0) if "cook_time_min" in rec.keys() else 0.0
    rest_time_min = float(rec["rest_time_min"] or 0.0) if "rest_time_min" in rec.keys() else 0.0
    labor_people = float(rec["labor_people"] or 0.0) if "labor_people" in rec.keys() else 0.0
    labor_hourly_cost = float(rec["labor_hourly_cost"] or 0.0) if "labor_hourly_cost" in rec.keys() else 0.0
    production_time_total_min = max(0.0, prep_time_min + cook_time_min + rest_time_min)
    labor_cost_total = (production_time_total_min / 60.0) * labor_people * labor_hourly_cost
    labor_cost_per_portion = labor_cost_total / yield_portions if yield_portions > 0 else 0.0

    # Costes indirectos: el usuario puede escribir importes con/sin IVA.
    # Para la receta se traducen a porcentaje sobre una base de ventas netas;
    # no se guardan como coste directo de materia prima. Salarios no llevan IVA.
    def _rec_float(key: str, default: float = 0.0) -> float:
        try:
            return float(rec[key] or default) if key in rec.keys() else default
        except Exception:
            return default

    def _rec_text(key: str, default: str = "ex_vat") -> str:
        try:
            val = str(rec[key] or default).strip().lower() if key in rec.keys() else default
        except Exception:
            val = default
        return val if val in ("ex_vat", "inc_vat") else default

    INDIRECT_VAT_RATE = 0.21
    indirect_sales_base = max(0.0, _rec_float("indirect_sales_base", 0.0))

    def _net_indirect_amount(amount_key: str, mode_key: str) -> float:
        amount = max(0.0, _rec_float(amount_key, 0.0))
        mode = _rec_text(mode_key, "ex_vat")
        if mode == "inc_vat":
            return amount / (1.0 + INDIRECT_VAT_RATE)
        return amount

    indirect_rent_net = _net_indirect_amount("indirect_rent_amount", "indirect_rent_tax_mode")
    indirect_services_net = _net_indirect_amount("indirect_services_amount", "indirect_services_tax_mode")
    indirect_admin_net = _net_indirect_amount("indirect_admin_amount", "indirect_admin_tax_mode")
    indirect_marketing_net = _net_indirect_amount("indirect_marketing_amount", "indirect_marketing_tax_mode")
    indirect_other_net = _net_indirect_amount("indirect_other_amount", "indirect_other_tax_mode")
    salary_cost_net = max(0.0, _rec_float("salary_cost_amount", 0.0))
    indirect_structure_net = indirect_rent_net + indirect_services_net + indirect_admin_net + indirect_marketing_net + indirect_other_net
    indirect_total_net = indirect_structure_net + salary_cost_net

    def _pct_of_sales(amount: float) -> float:
        return (amount / indirect_sales_base * 100.0) if indirect_sales_base > 0 else 0.0

    indirect_rent_pct = _pct_of_sales(indirect_rent_net)
    indirect_services_pct = _pct_of_sales(indirect_services_net)
    indirect_admin_pct = _pct_of_sales(indirect_admin_net)
    indirect_marketing_pct = _pct_of_sales(indirect_marketing_net)
    indirect_other_pct = _pct_of_sales(indirect_other_net)
    salary_cost_pct = _pct_of_sales(salary_cost_net)
    indirect_structure_pct = _pct_of_sales(indirect_structure_net)
    indirect_total_pct = _pct_of_sales(indirect_total_net)

    suggested_ex_for_load = suggested_ex_vat if suggested_ex_vat > 0 else price_ex_vat
    indirect_load_per_portion = suggested_ex_for_load * (indirect_total_pct / 100.0) if suggested_ex_for_load > 0 else 0.0

    operating_cost_total = cost_adjusted + labor_cost_total
    operating_cost_per_portion = operating_cost_total / yield_portions if yield_portions > 0 else 0.0

    payload = {k: rec[k] for k in rec.keys()}
    payload["ingredients"] = ingredients
    payload["calc"] = {
        "cost_base": cost_base, "cost_adjusted": cost_adjusted,
        "yield_portions": yield_portions, "cost_per_portion": cost_per_portion,
        "price_ex_vat": price_ex_vat, "price_vat": price_vat,
        "price_inc_vat": price_inc_vat, "suggested_ex_vat": suggested_ex_vat,
        "suggested_inc_vat": suggested_inc_vat, "food_cost_real_pct": food_cost_real_pct,
        "prep_time_min": prep_time_min, "cook_time_min": cook_time_min, "rest_time_min": rest_time_min,
        "production_time_total_min": production_time_total_min, "labor_people": labor_people,
        "labor_hourly_cost": labor_hourly_cost, "labor_cost_total": labor_cost_total,
        "labor_cost_per_portion": labor_cost_per_portion, "operating_cost_total": operating_cost_total,
        "operating_cost_per_portion": operating_cost_per_portion,
        "indirect_vat_rate": INDIRECT_VAT_RATE,
        "indirect_sales_base": indirect_sales_base,
        "indirect_rent_pct": indirect_rent_pct, "indirect_services_pct": indirect_services_pct,
        "indirect_admin_pct": indirect_admin_pct, "indirect_marketing_pct": indirect_marketing_pct,
        "indirect_other_pct": indirect_other_pct, "salary_cost_pct": salary_cost_pct,
        "indirect_structure_pct": indirect_structure_pct, "indirect_total_pct": indirect_total_pct,
        "indirect_load_per_portion": indirect_load_per_portion,
    }
    return payload


# ==============================================================================
# PRODUCCIONES
# ==============================================================================

def production_with_lines(cur, production_id: int):
    p = cur.execute(
        """SELECT p.*, c.name center_name, w.name warehouse_name
             FROM productions p
             JOIN centers c ON c.id=p.center_id
             JOIN warehouses w ON w.id=p.warehouse_id
            WHERE p.id=?""", (production_id,)).fetchone()
    if not p:
        return None
    lines = cur.execute(
        """SELECT pl.*, i.name item_name, i.unit base_unit
             FROM production_lines pl
             JOIN items i ON i.id=pl.item_id
            WHERE pl.production_id=? ORDER BY pl.id""", (production_id,)).fetchall()
    payload = {k: p[k] for k in p.keys()}
    payload["lines"] = [{k: r[k] for k in r.keys()} for r in lines]
    return payload


def _production_required_gross(cur, recipe_row) -> float:
    gross = float(recipe_row["qty_gross"] or 0.0)
    if gross > 0:
        return gross
    net = float(recipe_row["qty_net"] or 0.0)
    waste = float(recipe_row["waste_pct_ing"] or 0.0)
    if waste <= 0 and int(recipe_row["item_id"] or 0) > 0:
        ir = cur.execute("SELECT waste_default_pct FROM items WHERE id=?",
                         (int(recipe_row["item_id"]),)).fetchone()
        if ir:
            waste = float(ir[0] or 0.0)
    if waste >= 100:
        waste = 99.0
    if net <= 0:
        return 0.0
    if waste > 0:
        return net / max(0.000001, (1.0 - (waste / 100.0)))
    return net


def _merge_or_insert_production_line(cur, production_id: int, line_type: str, item_id: int,
                                      qty_base: float, input_unit: str, qty_input: float):
    existing = cur.execute(
        "SELECT id, qty_base, qty_input FROM production_lines WHERE production_id=? AND line_type=? AND item_id=? AND input_unit=? ORDER BY id LIMIT 1",
        (production_id, line_type, int(item_id), (input_unit or "").strip())).fetchone()
    if existing:
        cur.execute(
            "UPDATE production_lines SET qty_base=?, qty_input=? WHERE id=?",
            (float(existing["qty_base"] or 0.0) + float(qty_base or 0.0),
             float(existing["qty_input"] or 0.0) + float(qty_input or 0.0),
             int(existing["id"])))
        return False
    cur.execute(
        "INSERT INTO production_lines(production_id,line_type,item_id,qty_base,input_unit,qty_input) VALUES(?,?,?,?,?,?)",
        (production_id, line_type, int(item_id), float(qty_base), (input_unit or "").strip() or "ud", float(qty_input)))
    return True


# ==============================================================================
# PEDIDOS
# ==============================================================================

def order_with_lines(cur, order_id: int):
    o = cur.execute(
        """SELECT o.*, c.name center_name FROM orders o
             JOIN centers c ON c.id=o.center_id WHERE o.id=?""", (order_id,)).fetchone()
    if not o:
        return None
    lines = cur.execute(
        """SELECT ol.*, i.name item_name, i.unit base_unit,
                  w.name warehouse_name, s.name supplier_name,
                  COALESCE(lp.max_qty, i.max_qty) target_max_qty,
                  COALESCE((
                    SELECT SUM(CASE WHEN m.movement_type IN ('ENTRADA','IN') THEN m.qty
                                    WHEN m.movement_type IN ('SALIDA','OUT') THEN -m.qty ELSE -m.qty END)
                      FROM movements m
                     WHERE m.center_id=o.center_id AND m.warehouse_id=ol.warehouse_id AND m.item_id=ol.item_id
                  ),0) current_stock_qty
             FROM order_lines ol
             JOIN orders o ON o.id=ol.order_id
             JOIN items i ON i.id=ol.item_id
             JOIN warehouses w ON w.id=ol.warehouse_id
             LEFT JOIN item_location_prefs lp ON lp.center_id=o.center_id AND lp.warehouse_id=ol.warehouse_id AND lp.item_id=ol.item_id
             LEFT JOIN suppliers s ON s.id=ol.supplier_id
            WHERE ol.order_id=? ORDER BY ol.id""", (order_id,)).fetchall()
    payload = {k: o[k] for k in o.keys()}
    out_lines = []
    for r in lines:
        d = {k: r[k] for k in r.keys()}
        d["target_max_qty"] = normalize_minmax_qty_for_base(d.get("target_max_qty"), d.get("base_unit") or d.get("input_unit") or "")
        dv, du = preferred_display_qty(d.get("qty_input"), d.get("input_unit"))
        d["display_qty_value"] = dv
        d["display_qty_unit"] = du
        d["display_price_unit"] = preferred_price_unit(d.get("base_unit") or d.get("input_unit") or "")
        out_lines.append(d)
    payload["lines"] = out_lines
    return payload


# ==============================================================================
# DASHBOARD / DATOS GLOBALES
# ==============================================================================

def get_dashboard_data(center_id: Optional[int] = None):
    conn = db()
    cur = conn.cursor()
    ensure_columns(cur)
    centers = cur.execute("SELECT * FROM centers ORDER BY id").fetchall()
    center_filter = ""
    params = []
    if center_id:
        center_filter = "WHERE c.id=?"
        params.append(center_id)
    stock_sql = f"""
    SELECT c.id center_id,c.name center_name,w.id warehouse_id,w.name warehouse_name,
           i.id item_id,i.name item_name,i.unit,i.stock_area,
           COALESCE(lp.min_qty, i.min_qty) min_qty,
           COALESCE(lp.max_qty, i.max_qty) max_qty,
           CASE WHEN lp.item_id IS NOT NULL THEN 1 ELSE 0 END has_pref,
           COALESCE(SUM(CASE WHEN m.movement_type IN ('ENTRADA','IN') THEN m.qty
                             WHEN m.movement_type IN ('SALIDA','OUT') THEN -m.qty ELSE -m.qty END),0) stock_qty,
           (SELECT mm.qty FROM movements mm WHERE mm.center_id=c.id AND mm.warehouse_id=w.id AND mm.item_id=i.id ORDER BY mm.id DESC LIMIT 1) last_move_qty,
           (SELECT mm.note FROM movements mm WHERE mm.center_id=c.id AND mm.warehouse_id=w.id AND mm.item_id=i.id ORDER BY mm.id DESC LIMIT 1) last_move_note,
           (SELECT mm.created_at FROM movements mm WHERE mm.center_id=c.id AND mm.warehouse_id=w.id AND mm.item_id=i.id ORDER BY mm.id DESC LIMIT 1) last_move_at
    FROM centers c
    JOIN warehouses w ON w.center_id=c.id
    CROSS JOIN items i
    LEFT JOIN item_location_prefs lp ON lp.center_id=c.id AND lp.warehouse_id=w.id AND lp.item_id=i.id
    LEFT JOIN movements m ON m.center_id=c.id AND m.warehouse_id=w.id AND m.item_id=i.id
    {center_filter}
    GROUP BY c.id,c.name,w.id,w.name,i.id,i.name,i.unit,i.stock_area,
             COALESCE(lp.min_qty, i.min_qty),COALESCE(lp.max_qty, i.max_qty), CASE WHEN lp.item_id IS NOT NULL THEN 1 ELSE 0 END
    ORDER BY c.name, w.name, i.name
    """
    stocks = cur.execute(stock_sql, params).fetchall()
    summary = {
        "centers": len({s["center_id"] for s in stocks}),
        "positions": len(stocks),
        "below_min": sum(1 for s in stocks if s["stock_qty"] < s["min_qty"]),
    }
    warehouses = cur.execute(
        "SELECT w.id,w.name,w.center_id,c.name center_name FROM warehouses w JOIN centers c ON c.id=w.center_id ORDER BY c.id,w.id").fetchall()
    items = cur.execute("SELECT *, COALESCE(stock_area,'') stock_area FROM items ORDER BY LOWER(name)").fetchall()
    if center_id:
        recipes = cur.execute(
            """SELECT * FROM recipes WHERE is_active=1
               AND (COALESCE(scope_global,1)=1 OR (',' || COALESCE(scope_centers,'') || ',') LIKE ('%,' || ? || ',%'))
               ORDER BY id""", (int(center_id),)).fetchall()
    else:
        recipes = cur.execute("SELECT * FROM recipes WHERE is_active=1 ORDER BY id").fetchall()
    conn.close()
    stocks = [dict(s) if not hasattr(s, 'keys') else {k: s[k] for k in s.keys()} for s in stocks]
    for s in stocks:
        s['stock_area'] = normalize_stock_area(s.get('stock_area') or '')
        # Blindaje min/max: corrige valores heredados en gramos tras migrar artículos a kg.
        base_unit = s.get('unit') or ''
        s['min_qty'] = normalize_minmax_qty_for_base(s.get('min_qty'), base_unit)
        s['max_qty'] = normalize_minmax_qty_for_base(s.get('max_qty'), base_unit)
    summary = {
        'centers': len({s['center_id'] for s in stocks}),
        'positions': len(stocks),
        'below_min': sum(1 for s in stocks if float(s.get('stock_qty') or 0) < float(s.get('min_qty') or 0)),
    }
    return centers, warehouses, items, stocks, summary, recipes


# ==============================================================================
# ALBARANES / FOTOS / RETENCIÓN
# ==============================================================================

def _parse_dt_any(s: str):
    if not s:
        return None
    ss = str(s).strip().replace("Z", "")
    try:
        return datetime.fromisoformat(ss)
    except Exception:
        pass
    try:
        return datetime.strptime(ss[:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _expiry_end_of_month_plus_2(dt: datetime) -> datetime:
    y, m = dt.year, dt.month
    m2 = m + 2
    y2 = y + (m2 - 1) // 12
    m2 = ((m2 - 1) % 12) + 1
    last_day = calendar.monthrange(y2, m2)[1]
    return datetime(y2, m2, last_day, 23, 59, 59)


def cleanup_receipt_photos(cur, center_id: Optional[int] = None) -> dict:
    now = datetime.now()
    q = """SELECT rp.id, rp.file_path, rp.created_at, r.center_id
             FROM receipt_photos rp JOIN receipts r ON r.id = rp.receipt_id"""
    params = []
    if center_id:
        q += " WHERE r.center_id=?"
        params.append(int(center_id))
    rows = cur.execute(q, tuple(params)).fetchall()
    deleted_files = 0
    deleted_rows = 0
    for r in rows:
        dt = _parse_dt_any(r["created_at"])
        if not dt:
            continue
        if now <= _expiry_end_of_month_plus_2(dt):
            continue
        fp = (r["file_path"] or "").strip()
        try:
            if fp:
                p = Path(fp)
                if not p.is_absolute():
                    p = (RUNTIME_DIR / fp).resolve()
                if p.exists():
                    p.unlink(missing_ok=True)
                    deleted_files += 1
        except Exception:
            pass
        try:
            cur.execute("DELETE FROM receipt_photos WHERE id=?", (int(r["id"]),))
            deleted_rows += 1
        except Exception:
            pass
    return {"deleted_files": deleted_files, "deleted_rows": deleted_rows}


def _refresh_ocr_summary(cur, receipt_id: int):
    run = cur.execute(
        "SELECT id FROM receipt_ocr_runs WHERE receipt_id=? ORDER BY id DESC LIMIT 1",
        (int(receipt_id),)).fetchone()
    if not run:
        return
    rows = cur.execute("SELECT review_status FROM receipt_ocr_lines WHERE ocr_run_id=? ORDER BY id",
                       (int(run["id"]),)).fetchall()
    total = len(rows)
    accepted = sum(1 for r in rows if (r["review_status"] or "").upper() == "ACCEPTED")
    pending = sum(1 for r in rows if (r["review_status"] or "").upper() in ("PENDING", "REVIEW"))
    summary = f"{total} línea(s) OCR · {accepted} aceptada(s) · {pending} pendiente(s)"
    status = "READ" if total else "EMPTY"
    cur.execute("UPDATE receipt_ocr_runs SET summary=?, status=? WHERE id=?",
                (summary, status, int(run["id"])))


def _resolve_receipt_warehouse(cur, center_id: int, warehouse_id: int) -> int:
    row = cur.execute("SELECT id FROM warehouses WHERE id=? AND center_id=?",
                      (int(warehouse_id or 0), int(center_id or 0))).fetchone()
    if row:
        return int(row["id"])
    row = cur.execute("SELECT id FROM warehouses WHERE center_id=? ORDER BY id LIMIT 1",
                      (int(center_id or 0),)).fetchone()
    if row:
        return int(row["id"])
    raise ValueError("No hay almacén disponible para el centro")


def _collect_uploads_from_form(form, *field_names) -> list:
    files = []
    for name in field_names:
        try:
            vals = form.getlist(name)
        except Exception:
            vals = []
        for v in vals:
            if getattr(v, "filename", None):
                files.append(v)
    seen = set()
    uniq = []
    for f in files:
        key = (getattr(f, "filename", None), id(f))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(f)
    return uniq


# ==============================================================================
# OCR - LOCKS
# ==============================================================================

def _ocr_lock_path(receipt_id: int) -> Path:
    lock_dir = APP_DIR.parent / "var" / "ocr_locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    return lock_dir / f"receipt_{int(receipt_id)}.lock"


def _ocr_lock_is_recent(receipt_id: int, max_age_sec: int = 45) -> bool:
    p = _ocr_lock_path(receipt_id)
    if not p.exists():
        return False
    try:
        age = time.time() - p.stat().st_mtime
        return age < max_age_sec
    except Exception:
        return False


def _ocr_lock_touch(receipt_id: int):
    try:
        _ocr_lock_path(receipt_id).write_text(str(int(time.time())))
    except Exception:
        pass


def _ocr_lock_clear(receipt_id: int):
    try:
        p = _ocr_lock_path(receipt_id)
        if p.exists():
            p.unlink()
    except Exception:
        pass


# ==============================================================================
# OCR HELPERS COMPARTIDOS (usados por main.py para display)
# ==============================================================================

def _ocr_cleanup_product_tokens(name: str) -> str:
    s = re.sub(r"\b(E[S5]|S2)\b", " ", (name or ""), flags=re.I)
    s = re.sub(r"\b(cod|codigo|ref|articulo|art)\b[\s.:]+\w+", " ", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" -:;,.()")
    return s


def _ocr_postfix_product_cleanup(name: str) -> str:
    s = _ocr_cleanup_product_tokens(name or "")
    s = re.sub(r"\bPITOS?\b", " ", s, flags=re.I)
    s = re.sub(r"\bM[I1J]L\b", "M/L", s, flags=re.I)
    s = re.sub(r"\bM\s*/?\s*L\b", "M/L", s, flags=re.I)
    s = re.sub(r"\b(PT|MA|ES|E[S5]|S2)\b$", " ", s, flags=re.I)
    s = re.sub(r"\b(BR)\b$", " ", s, flags=re.I)
    s = re.sub(r"\b(RESTAURANTE|REFERENCIA|MERCASA)\b$", " ", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" -:;,.()")
    return s


# ==============================================================================
# UTILIDADES DE IMAGEN
# ==============================================================================

def _normalize_uploaded_image_bytes_to_jpeg(filename: str, content: bytes, *, quality: int = 92, max_side: int = 2200):
    import io as _io
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", (filename or "upload").strip()) or "upload"
    base = re.sub(r"\.[A-Za-z0-9]+$", "", safe) or "upload"

    def _finalize(im):
        im.load()
        try:
            im = ImageOps.exif_transpose(im)
        except Exception:
            pass
        if getattr(im, "mode", "RGB") != "RGB":
            im = im.convert("RGB")
        try:
            w, h = im.size
            if max(w, h) > max_side and max(w, h) > 0:
                scale = float(max_side) / float(max(w, h))
                im = im.resize((max(1, int(round(w * scale))), max(1, int(round(h * scale)))))
        except Exception:
            pass
        out = _io.BytesIO()
        try:
            im.save(out, format="JPEG", quality=quality, optimize=True)
        except Exception:
            out = _io.BytesIO()
            im.save(out, format="JPEG", quality=quality)
        data = out.getvalue()
        chk = Image.open(_io.BytesIO(data))
        chk.load()
        return f"{base}.jpg", data

    try:
        im = Image.open(_io.BytesIO(content))
        return _finalize(im)
    except Exception:
        pass
    if safe.lower().endswith((".heic", ".heif")):
        try:
            import subprocess, tempfile
            with tempfile.NamedTemporaryFile(suffix=Path(safe).suffix or ".heic", delete=False) as tin:
                tin.write(content)
                tmp_in = Path(tin.name)
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tout:
                tmp_out = Path(tout.name)
            subprocess.run(["sips", "-s", "format", "jpeg", str(tmp_in), "--out", str(tmp_out)],
                           check=True, capture_output=True)
            data = tmp_out.read_bytes()
            im = Image.open(_io.BytesIO(data))
            return _finalize(im)
        except Exception:
            pass
    return f"{base}.jpg", b""


def _normalize_receipt_upload_to_jpg(filename: str, content: bytes):
    jpg_name, jpg_bytes = _normalize_uploaded_image_bytes_to_jpeg(filename, content, quality=92, max_side=2400)
    if jpg_bytes:
        return jpg_name, jpg_bytes
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", (filename or "upload").strip()) or "upload"
    return safe, content


def _build_receipt_ocr_work_jpg(filename: str, content: bytes):
    import io as _io
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", (filename or "upload").strip()) or "upload"
    base = re.sub(r"\.[A-Za-z0-9]+$", "", safe) or "upload"
    norm_name, norm_bytes = _normalize_uploaded_image_bytes_to_jpeg(filename, content, quality=94, max_side=2400)
    if norm_bytes:
        try:
            im = Image.open(_io.BytesIO(norm_bytes))
            im.load()
            try:
                im = ImageOps.exif_transpose(im)
            except Exception:
                pass
            if im.mode != "RGB":
                im = im.convert("RGB")
            try:
                w, h = im.size
                target = 1900
                if max(w, h) < target and max(w, h) > 0:
                    scale = max(1, int(target / max(w, h)) + 1)
                    im = im.resize((w * scale, h * scale))
            except Exception:
                pass
            gray = ImageOps.autocontrast(im.convert("L")).convert("RGB")
            out = _io.BytesIO()
            gray.save(out, format="JPEG", quality=94, optimize=True)
            data = out.getvalue()
            base2 = re.sub(r"\.[A-Za-z0-9]+$", "", norm_name) or base
            return f"{base2}.ocr.jpg", data
        except Exception:
            return f"{base}.ocr.jpg", norm_bytes
    return f"{base}.ocr.jpg", b""


# ==============================================================================
# MIGRACIONES DE BD
# ==============================================================================

STOCK_AREAS = [
    ('', 'Sin ubicar'),
    ('SIN_CLASIFICACION', 'Sin clasificación'),
    ('SECOS', 'Secos'),
    ('CONGELADOS', 'Congelados'),
    ('FRESCOS', 'Frescos'),
    ('LIMPIEZA', 'Limpieza'),
    ('PREPARACIONES', 'Preparaciones'),
]


def normalize_stock_area(value: str) -> str:
    v = (value or '').strip().upper()
    allowed = {k for k, _ in STOCK_AREAS if k}
    return v if v in allowed else ''


def stock_area_label(value: str) -> str:
    key = normalize_stock_area(value)
    labels = dict(STOCK_AREAS)
    return labels.get(key, labels.get('', 'Sin ubicar'))


def ensure_columns(cur):
    # In production (Postgres) the schema is provisioned by backend/migrate.py.
    # Guard runtime DDL here to avoid executing SQLite-specific CREATE/ALTER statements
    # against a Postgres adapter connection.
    try:
        if getattr(cur, "_is_postgres", False):
            return
    except Exception:
        pass

    # Ensure SQLite schema exists (centralized in backend/migrate.py)
    try:
        try:
            import migrate as _migrate
        except Exception:
            try:
                from backend import migrate as _migrate
            except Exception:
                _migrate = None
        if _migrate and hasattr(_migrate, "ensure_sqlite_schema"):
            try:
                _migrate.ensure_sqlite_schema(cur)
            except Exception:
                pass
    except Exception:
        pass

    # CREATE TABLE `users` moved to backend/migrate.py (ensure_sqlite_schema)
    try:
        cur.execute("ALTER TABLE inventory_sessions ADD COLUMN responsible_user_id INTEGER NOT NULL DEFAULT 0")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE inventory_sessions ADD COLUMN responsible_name TEXT DEFAULT ''")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE orders ADD COLUMN responsible_user_id INTEGER NOT NULL DEFAULT 0")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE orders ADD COLUMN responsible_name TEXT DEFAULT ''")
    except Exception:
        pass
    cols_order_lines = set(get_table_columns_from_cursor(cur, "order_lines"))
    if 'is_checked' not in cols_order_lines:
        try:
            cur.execute("ALTER TABLE order_lines ADD COLUMN is_checked INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass
    try:
        count_users = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    except Exception:
        count_users = 0
    if not count_users:
        cur.execute("INSERT INTO users(name,role,center_id,is_active) VALUES('ADMIN GENERAL','ADMIN',0,1)")
    cols_items = set(get_table_columns_from_cursor(cur, "items"))
    for col, defn in [("max_qty", "REAL NOT NULL DEFAULT 0"),
                      ("current_price", "REAL NOT NULL DEFAULT 0"),
                      ("waste_default_pct", "REAL NOT NULL DEFAULT 0"),
                      ("stock_area", "TEXT NOT NULL DEFAULT ''"),
                      ("order_category", "TEXT NOT NULL DEFAULT ''"),
                      ("item_type", "TEXT NOT NULL DEFAULT 'INSUMO'"),
                      ("price_status", "TEXT NOT NULL DEFAULT ''"),
                      ("price_source", "TEXT NOT NULL DEFAULT ''"),
                      ("price_confidence", "TEXT NOT NULL DEFAULT ''"),
                      ("price_reference_year", "TEXT NOT NULL DEFAULT ''"),
                      ("price_operational_unit", "TEXT NOT NULL DEFAULT ''"),
                      ("price_operational_value", "REAL NOT NULL DEFAULT 0"),
                      ("price_notes", "TEXT NOT NULL DEFAULT ''")]:
        if col not in cols_items:
            try:
                cur.execute(f"ALTER TABLE items ADD COLUMN {col} {defn}")
            except Exception:
                pass
    # TPV / ventas normalizadas: tablas neutrales para cualquier proveedor de TPV y tipo de negocio.
    # No conectan ningún TPV todavía; solo preparan el terreno para cargar ventas verificables.
        # CREATE TABLE `pos_integrations` moved to backend/migrate.py
        # CREATE TABLE `pos_sales_daily` moved to backend/migrate.py
        # CREATE TABLE `pos_sales_item_daily` moved to backend/migrate.py
    # TPV / modificadores: capa neutral para consumo realista por venta.
    # No modifica recetas maestras ni descuenta stock; prepara reglas y auditoría.
        # CREATE TABLE `recipe_modifiers` moved to backend/migrate.py
        # CREATE TABLE `pos_modifier_map` moved to backend/migrate.py
        # CREATE TABLE `pos_sales_modifier_daily` moved to backend/migrate.py
        # CREATE TABLE `pos_modifier_consumption_audit` moved to backend/migrate.py
    # Index creation moved to backend/migrate.py

    cols_sup = set(get_table_columns_from_cursor(cur, "suppliers"))
    for col, defn in [("tax_id", "TEXT"), ("address", "TEXT"),
                      ("is_active", "INTEGER NOT NULL DEFAULT 1"),
                      ("created_at", "TEXT"),
                      ("delivery_days", "TEXT NOT NULL DEFAULT ''"),
                      ("delivery_min_order_amount", "REAL NOT NULL DEFAULT 0"),
                      ("delivery_min_tax_mode", "TEXT NOT NULL DEFAULT 'ex_vat'"),
                      ("delivery_lead_time_days", "INTEGER NOT NULL DEFAULT 0"),
                      ("delivery_notes", "TEXT NOT NULL DEFAULT ''")]:
        if col not in cols_sup:
            try:
                cur.execute(f"ALTER TABLE suppliers ADD COLUMN {col} {defn}")
            except Exception:
                pass
    cols_rec = set(get_table_columns_from_cursor(cur, "recipes"))
    for col, defn in [("is_subrecipe", "INTEGER NOT NULL DEFAULT 0"),
                      ("is_producible", "INTEGER NOT NULL DEFAULT 0"),
                      ("produced_item_id", "INTEGER NOT NULL DEFAULT 0"),
                      ("cost_supplier_id", "INTEGER"),
                      ("scope_global", "INTEGER NOT NULL DEFAULT 1"),
                      ("scope_centers", "TEXT NOT NULL DEFAULT ''"),
                      ("yield_portions", "REAL NOT NULL DEFAULT 1"),
                      ("yield_final_qty", "REAL NOT NULL DEFAULT 0"),
                      ("yield_final_unit", "TEXT NOT NULL DEFAULT 'g'"),
                      ("is_active", "INTEGER NOT NULL DEFAULT 1"),
                      ("recipe_photo_path", "TEXT"),
                      ("prep_time_min", "REAL NOT NULL DEFAULT 0"),
                      ("cook_time_min", "REAL NOT NULL DEFAULT 0"),
                      ("rest_time_min", "REAL NOT NULL DEFAULT 0"),
                      ("labor_people", "REAL NOT NULL DEFAULT 0"),
                      ("labor_hourly_cost", "REAL NOT NULL DEFAULT 0"),
                      ("indirect_sales_base", "REAL NOT NULL DEFAULT 0"),
                      ("indirect_rent_amount", "REAL NOT NULL DEFAULT 0"),
                      ("indirect_rent_tax_mode", "TEXT NOT NULL DEFAULT 'ex_vat'"),
                      ("indirect_services_amount", "REAL NOT NULL DEFAULT 0"),
                      ("indirect_services_tax_mode", "TEXT NOT NULL DEFAULT 'ex_vat'"),
                      ("indirect_admin_amount", "REAL NOT NULL DEFAULT 0"),
                      ("indirect_admin_tax_mode", "TEXT NOT NULL DEFAULT 'ex_vat'"),
                      ("indirect_marketing_amount", "REAL NOT NULL DEFAULT 0"),
                      ("indirect_marketing_tax_mode", "TEXT NOT NULL DEFAULT 'ex_vat'"),
                      ("indirect_other_amount", "REAL NOT NULL DEFAULT 0"),
                      ("indirect_other_tax_mode", "TEXT NOT NULL DEFAULT 'ex_vat'"),
                      ("salary_cost_amount", "REAL NOT NULL DEFAULT 0"),
                      ("created_at", "TEXT"),
                      ("updated_at", "TEXT")]:
        if col not in cols_rec:
            try:
                cur.execute(f"ALTER TABLE recipes ADD COLUMN {col} {defn}")
            except Exception:
                pass
    cols_ocr = set(get_table_columns_from_cursor(cur, "receipt_ocr_runs"))
    for col, defn in [("supplier_name", "TEXT"), ("date_text", "TEXT"), ("line_count", "INTEGER DEFAULT 0"),
                      ("supplier_phone_raw", "TEXT"), ("supplier_email_raw", "TEXT"),
                      ("supplier_tax_id_raw", "TEXT"), ("supplier_address_raw", "TEXT")]:
        if col not in cols_ocr:
            try:
                cur.execute(f"ALTER TABLE receipt_ocr_runs ADD COLUMN {col} {defn}")
            except Exception:
                pass
    try:
        cur.execute("UPDATE recipes SET created_at=COALESCE(created_at, CURRENT_TIMESTAMP) WHERE created_at IS NULL OR created_at=''")
        cur.execute("UPDATE recipes SET updated_at=COALESCE(updated_at, created_at, CURRENT_TIMESTAMP) WHERE updated_at IS NULL OR updated_at=''")
    except Exception:
        pass
    cols_ing = set(get_table_columns_from_cursor(cur, "recipe_ingredients"))
    for col, defn in [("input_unit", "TEXT"), ("waste_pct_ing", "REAL NOT NULL DEFAULT 0"),
                      ("subrecipe_id", "INTEGER")]:
        if col not in cols_ing:
            try:
                cur.execute(f"ALTER TABLE recipe_ingredients ADD COLUMN {col} {defn}")
            except Exception:
                pass

        # CREATE TABLE `inventory_sessions` moved to backend/migrate.py
        # CREATE TABLE `inventory_counts` moved to backend/migrate.py


        # CREATE TABLE `waste_records` moved to backend/migrate.py

    # productions.production_group (v8.7.198)
    cols_prod = set(get_table_columns_from_cursor(cur, "productions")) if table_exists(cur, "productions") else set()
    if "production_group" not in cols_prod:
        try:
            cur.execute("ALTER TABLE productions ADD COLUMN production_group TEXT NOT NULL DEFAULT 'Otros'")
        except Exception:
            pass



    # Documentos proveedor / conciliación / pagos futuros (preparación segura, sin pagos reales).
    for col, ddl in {
        "tax_id": "TEXT NOT NULL DEFAULT ''",
        "address": "TEXT NOT NULL DEFAULT ''",
        "postal_code": "TEXT NOT NULL DEFAULT ''",
        "city": "TEXT NOT NULL DEFAULT ''",
        "health_registry_code": "TEXT NOT NULL DEFAULT ''",
        "payment_terms": "TEXT NOT NULL DEFAULT ''",
        "payment_frequency": "TEXT NOT NULL DEFAULT ''",
        "payment_day_rule": "TEXT NOT NULL DEFAULT ''",
        "payment_method": "TEXT NOT NULL DEFAULT ''",
        "iban": "TEXT NOT NULL DEFAULT ''",
        "accounting_email": "TEXT NOT NULL DEFAULT ''",
        "requires_payment_approval": "INTEGER NOT NULL DEFAULT 1",
    }.items():
        try:
            cols_suppliers = set(get_table_columns_from_cursor(cur, "suppliers"))
            if col not in cols_suppliers:
                cur.execute(f"ALTER TABLE suppliers ADD COLUMN {col} {ddl}")
        except Exception:
            pass
        # CREATE TABLE `supplier_documents` moved to backend/migrate.py
        # CREATE TABLE `supplier_document_reconciliations` moved to backend/migrate.py
        # CREATE TABLE `supplier_payment_proposals` moved to backend/migrate.py
        # CREATE TABLE `accounting_export_batches` moved to backend/migrate.py

def ensure_items_columns(cur):
    cols = set(get_table_columns_from_cursor(cur, "items"))
    for col, defn in [("waste_default_pct", "REAL NOT NULL DEFAULT 0"),
                      ("current_price", "REAL NOT NULL DEFAULT 0"),
                      ("stock_area", "TEXT NOT NULL DEFAULT ''")]:
        if col not in cols:
            try:
                cur.execute(f"ALTER TABLE items ADD COLUMN {col} {defn}")
            except Exception:
                pass


def merge_duplicate_items(cur):
    rows = cur.execute("SELECT id,name,unit,min_qty,max_qty,current_price FROM items ORDER BY id").fetchall()
    groups = {}
    for r in rows:
        key = (_item_key(r["name"]), (r["unit"] or "").strip())
        groups.setdefault(key, []).append(r)
    for key, grp in groups.items():
        if len(grp) <= 1:
            continue
        canon = grp[0]
        canon_id = int(canon["id"])
        dup_ids = [int(r["id"]) for r in grp[1:]]
        if not dup_ids:
            continue
        best_price = max([float(canon["current_price"] or 0)] + [float(r["current_price"] or 0) for r in grp[1:]])
        best_min = max([float(canon["min_qty"] or 0)] + [float(r["min_qty"] or 0) for r in grp[1:]])
        best_max = max([float(canon["max_qty"] or 0)] + [float(r["max_qty"] or 0) for r in grp[1:]])
        cur.execute("UPDATE items SET current_price=?, min_qty=?, max_qty=? WHERE id=?",
                    (best_price, best_min, best_max, canon_id))
        placeholders = ','.join('?' * len(dup_ids))
        # Las versiones anteriores solo migraban movimientos/pedidos/albaranes.
        # Eso dejaba recetas y production_lines apuntando a duplicados invisibles en Stock/Pedidos.
        for t in ("movements", "supplier_item_prices", "order_lines", "receipt_lines", "production_lines", "inventory_counts", "waste_entries"):
            try:
                cur.execute(f"UPDATE {t} SET item_id=? WHERE item_id IN ({placeholders})", [canon_id, *dup_ids])
            except Exception:
                pass
        try:
            cur.execute(f"UPDATE recipe_ingredients SET item_id=? WHERE item_id IN ({placeholders})", [canon_id, *dup_ids])
        except Exception:
            pass
        # Fusionar preferencias min/max sin romper UNIQUE(center_id, warehouse_id, item_id).
        try:
            pref_rows = cur.execute(f"SELECT center_id,warehouse_id,min_qty,max_qty FROM item_location_prefs WHERE item_id IN ({placeholders})", dup_ids).fetchall()
            for pr in pref_rows:
                existing = cur.execute(
                    "SELECT id,min_qty,max_qty FROM item_location_prefs WHERE center_id=? AND warehouse_id=? AND item_id=?",
                    (int(pr["center_id"]), int(pr["warehouse_id"]), canon_id),
                ).fetchone()
                if existing:
                    cur.execute(
                        "UPDATE item_location_prefs SET min_qty=?, max_qty=? WHERE id=?",
                        (max(float(existing["min_qty"] or 0), float(pr["min_qty"] or 0)),
                         max(float(existing["max_qty"] or 0), float(pr["max_qty"] or 0)),
                         int(existing["id"])),
                    )
                else:
                    # Use Postgres UPSERT when available; otherwise emulate INSERT OR IGNORE
                    center_id_val = int(pr["center_id"])
                    warehouse_id_val = int(pr["warehouse_id"])
                    min_val = float(pr["min_qty"] or 0)
                    max_val = float(pr["max_qty"] or 0)
                    if getattr(cur, "_is_postgres", False):
                        try:
                            cur.execute(
                                "INSERT INTO item_location_prefs(center_id,warehouse_id,item_id,min_qty,max_qty) VALUES(%s,%s,%s,%s,%s) ON CONFLICT (center_id,warehouse_id,item_id) DO NOTHING",
                                (center_id_val, warehouse_id_val, canon_id, min_val, max_val),
                            )
                        except Exception:
                            # Fallback to safe SELECT->INSERT emulation
                            try:
                                exists2 = cur.execute(
                                    'SELECT 1 FROM item_location_prefs WHERE center_id=? AND warehouse_id=? AND item_id=?',
                                    (center_id_val, warehouse_id_val, canon_id),
                                ).fetchone()
                                if not exists2:
                                    cur.execute(
                                        'INSERT INTO item_location_prefs(center_id,warehouse_id,item_id,min_qty,max_qty) VALUES(?,?,?,?,?)',
                                        (center_id_val, warehouse_id_val, canon_id, min_val, max_val),
                                    )
                            except Exception:
                                pass
                    else:
                        try:
                            exists2 = cur.execute(
                                'SELECT 1 FROM item_location_prefs WHERE center_id=? AND warehouse_id=? AND item_id=?',
                                (center_id_val, warehouse_id_val, canon_id),
                            ).fetchone()
                            if not exists2:
                                cur.execute(
                                    'INSERT INTO item_location_prefs(center_id,warehouse_id,item_id,min_qty,max_qty) VALUES(?,?,?,?,?)',
                                    (center_id_val, warehouse_id_val, canon_id, min_val, max_val),
                                )
                        except Exception:
                            pass
            cur.execute(f"DELETE FROM item_location_prefs WHERE item_id IN ({placeholders})", dup_ids)
        except Exception:
            pass
        cur.execute(f"DELETE FROM items WHERE id IN ({placeholders})", dup_ids)


def merge_exact_duplicate_items(cur):
    merge_duplicate_items(cur)


# ==============================================================================
# SEMILLAS (SEED)
# ==============================================================================

def _seed_load_items():
    if not SEED_ITEMS_CSV.exists():
        return []
    rows = []
    with SEED_ITEMS_CSV.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            name = (r.get("item_name") or "").strip()
            unit = (r.get("base_unit") or "").strip() or "g"
            if name:
                rows.append((name, unit, 0.0, 0.0))
    return rows


def _seed_load_prices():
    if not SEED_PRICES_CSV.exists():
        return []
    rows = []
    with SEED_PRICES_CSV.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            item_name = (r.get("item_name") or "").strip()
            base_unit = (r.get("base_unit") or "").strip()
            ref_unit = (r.get("ref_unit") or "").strip()
            try:
                ref_price = float(r.get("ref_price"))
            except Exception:
                continue
            if not item_name or ref_price < 0:
                continue
            factor = 1.0
            if ref_unit == "kg" and base_unit == "g":
                factor = 1000.0
            elif ref_unit == "l" and base_unit == "ml":
                factor = 1000.0
            rows.append((item_name, ref_price, ref_unit, factor))
    return rows


# ==============================================================================
# INIT DB
# ==============================================================================



def _classify_stock_area_from_name(name: str) -> str:
    n = _norm_text(name or '')
    if not n:
        return ''
    cleaning = [
        'lejia','desengrasante','detergente','lavavajillas','guantes','bolsas basura','bolsa basura',
        'film transparente','papel aluminio','papel horno','caja take away','take away','nitrilo',
        'servilleta','servilletas','papel secamanos','secamanos','papel higienico','bayeta','estropajo',
        'fregasuelos','ambientador','higienizante','desinfectante','papel film','envase take away','envases take away','papel cocina','papel de cocina','lavavajillas maquina','lavavajillas máquina','limpiacristales','multiusos','papel celulosa','papel wc','bobina industrial','aluminio cocina','film alimentario'
    ]
    frozen = ['congelado','congelada','precocido congelado','helado','ultracongelado','ultracongelada']
    fresh = [
        'tomate','lechuga','cebolla','ceboll','pimiento','pepino','cilantro','jalapeno','espinaca','zanahoria','patata','papa','berenjena','calabacin','aguacate','brocoli','col','repollo','hierba','menta','albahaca','cebollino','seta','champi','ajo','perejil','lima','limon','manzana','naranja','jengibre',
        'pollo','ternera','vacuno','cerdo','solomillo','costilla','hamburg','secreto','presa','carrillera','chuleta','entrecot','cordero','bacon','panceta','jamon','chorizo','morcilla','carne picada','huesos de pollo','huesos de ternera',
        'lubina','merluza','atun','salmon','bacalao','pescado','sepia','calamar','langost','gamba','pulpo','mejillon','marisco','dorada','almeja','anchoa',
        'huevo','huevos','leche','nata','queso','mantequilla','yogur','yogurt','mozzarella','parmesano','cheddar'
    ]
    dry = [
        'aceite','arroz','azucar','cacao','canela','clavo','comino','curry','curcuma','fideos','frijol',
        'garbanzos','gelatina','harina','judia blanca','lentejas','levadura','maicena','maiz dulce',
        'mostaza','nuez moscada','oregano','pan rallado','panko','pan precocido','pasta seca','sal',
        'salsa soja','vinagre','wasabi','aceituna','alcaparras','algas nori','brandy cocina',
        'cerveza para cocinar','caldo stock liquido','fondo blanco','fondo oscuro','demi glace',
        'ketchup','mayonesa','jarabe de arce','conserva','conservas','lata','bote','tarro','salsa','aceitunas','vinagre de',
        'pure','pure de','tomate frito','tomate triturado','tomate pelado','legumbre','garbanzo cocido',
        'alubia','judion','quinoa','bulgur','cuscus','cous cous','soja texturizada','coco rallado',
        'pimenton','pimienta','laurel','romero','tomillo','miel','mermelada','atun lata','atún lata','maizena',
        'maíz','maiz','sriracha','tabasco','hojaldre congelado','masa filo congelada','fondo de verduras',
        'caldo vegetal','salsa worcestershire','salsa inglesa','aceite oliva','aceite girasol','fritura',
        'garrafa aceite','garrafa vinagre','agua mineral','agua con gas','botella agua','botellin agua','botellín agua',
        'cafe','café','infusion','infusión','te','té','cacao polvo','azucar glas','azúcar glas','levadura quimica','levadura química'
    ]
    for k in cleaning:
        if k in n:
            return 'LIMPIEZA'
    for k in frozen:
        if k in n:
            return 'CONGELADOS'
    for k in fresh:
        if k in n:
            return 'FRESCOS'
    for k in dry:
        if k in n:
            return 'SECOS'
    return ''


def _preferred_warehouse_name_for_stock_area(stock_area: str) -> str:
    area = normalize_stock_area(stock_area or '')
    if area in {'FRESCOS', 'CONGELADOS'}:
        return 'camara'
    if area in {'SECOS', 'LIMPIEZA'}:
        return 'economato'
    return ''


def _safe_migrate_movements_to_operational_warehouse(cur):
    """Migra movimientos históricos y preferencias solo cuando la situación es clara y no ambigua.

    Reglas de seguridad:
    - solo artículos con stock_area operativo claro (no sin clasificar / sin ubicar)
    - dentro del mismo centro/artículo, todos los movimientos deben estar en un solo almacén actual
    - solo se mueve a Cámara/Economato del mismo centro cuando ese almacén existe
    - también migra item_location_prefs si para ese centro/artículo hay una única preferencia clara
    """
    try:
        rows = cur.execute(
            "SELECT m.center_id, m.item_id, COUNT(DISTINCT m.warehouse_id) wh_count, MIN(m.warehouse_id) current_warehouse_id, COALESCE(i.stock_area,'') stock_area FROM movements m JOIN items i ON i.id=m.item_id GROUP BY m.center_id, m.item_id, COALESCE(i.stock_area,'')"
        ).fetchall()
    except Exception:
        rows = []

    moved = 0
    touched_pairs = set()
    for r in rows:
        try:
            center_id = int(r['center_id'] or 0)
            item_id = int(r['item_id'] or 0)
            wh_count = int(r['wh_count'] or 0)
            current_wh_id = int(r['current_warehouse_id'] or 0)
        except Exception:
            continue
        if center_id <= 0 or item_id <= 0 or wh_count != 1 or current_wh_id <= 0:
            continue
        preferred_name = _preferred_warehouse_name_for_stock_area(r['stock_area'] or '')
        if not preferred_name:
            continue
        current_wh = cur.execute("SELECT id,name FROM warehouses WHERE id=? AND center_id=?", (current_wh_id, center_id)).fetchone()
        if not current_wh:
            continue
        current_name = _norm_text(current_wh['name'] or '')
        if preferred_name in current_name:
            touched_pairs.add((center_id, item_id))
            continue
        target = cur.execute(
            "SELECT id,name FROM warehouses WHERE center_id=? AND lower(replace(name,'á','a')) LIKE ? ORDER BY id LIMIT 1",
            (center_id, f'%{preferred_name}%')
        ).fetchone()
        if not target:
            continue
        target_id = int(target['id'] or 0)
        if target_id <= 0 or target_id == current_wh_id:
            touched_pairs.add((center_id, item_id))
            continue
        cur.execute(
            "UPDATE movements SET warehouse_id=? WHERE center_id=? AND item_id=? AND warehouse_id=?",
            (target_id, center_id, item_id, current_wh_id)
        )
        moved += int(cur.rowcount or 0)
        touched_pairs.add((center_id, item_id))

    # Preferencias de ubicación: solo migrar si la preferencia actual también es única y clara.
    for center_id, item_id in list(touched_pairs):
        row = cur.execute(
            "SELECT COUNT(*) pref_count, MIN(lp.warehouse_id) current_warehouse_id, COALESCE(i.stock_area,'') stock_area FROM item_location_prefs lp JOIN items i ON i.id=lp.item_id WHERE lp.center_id=? AND lp.item_id=?",
            (center_id, item_id)
        ).fetchone()
        if not row:
            continue
        try:
            pref_count = int(row['pref_count'] or 0)
            current_wh_id = int(row['current_warehouse_id'] or 0)
        except Exception:
            continue
        if pref_count != 1 or current_wh_id <= 0:
            continue
        preferred_name = _preferred_warehouse_name_for_stock_area(row['stock_area'] or '')
        if not preferred_name:
            continue
        current_wh = cur.execute("SELECT id,name FROM warehouses WHERE id=? AND center_id=?", (current_wh_id, center_id)).fetchone()
        if not current_wh:
            continue
        if preferred_name in _norm_text(current_wh['name'] or ''):
            continue
        target = cur.execute(
            "SELECT id FROM warehouses WHERE center_id=? AND lower(replace(name,'á','a')) LIKE ? ORDER BY id LIMIT 1",
            (center_id, f'%{preferred_name}%')
        ).fetchone()
        if not target:
            continue
        target_id = int(target['id'] or 0)
        if target_id <= 0 or target_id == current_wh_id:
            continue
        cur.execute(
            "UPDATE item_location_prefs SET warehouse_id=? WHERE center_id=? AND item_id=? AND warehouse_id=?",
            (target_id, center_id, item_id, current_wh_id)
        )
        moved += int(cur.rowcount or 0)

    # standalone preference migration: casos claros aunque no haya movimientos tocados
    try:
        pref_rows = cur.execute(
            "SELECT lp.center_id, lp.item_id, COUNT(*) pref_count, MIN(lp.warehouse_id) current_warehouse_id, COALESCE(i.stock_area,'') stock_area FROM item_location_prefs lp JOIN items i ON i.id=lp.item_id GROUP BY lp.center_id, lp.item_id, COALESCE(i.stock_area,'')"
        ).fetchall()
    except Exception:
        pref_rows = []
    for r in pref_rows:
        try:
            center_id = int(r['center_id'] or 0)
            item_id = int(r['item_id'] or 0)
            pref_count = int(r['pref_count'] or 0)
            current_wh_id = int(r['current_warehouse_id'] or 0)
        except Exception:
            continue
        if center_id <= 0 or item_id <= 0 or pref_count != 1 or current_wh_id <= 0:
            continue
        preferred_name = _preferred_warehouse_name_for_stock_area(r['stock_area'] or '')
        if not preferred_name:
            continue
        current_wh = cur.execute("SELECT id,name FROM warehouses WHERE id=? AND center_id=?", (current_wh_id, center_id)).fetchone()
        if not current_wh:
            continue
        if preferred_name in _norm_text(current_wh['name'] or ''):
            continue
        target = cur.execute(
            "SELECT id FROM warehouses WHERE center_id=? AND lower(replace(name,'á','a')) LIKE ? ORDER BY id LIMIT 1",
            (center_id, f'%{preferred_name}%')
        ).fetchone()
        if not target:
            continue
        target_id = int(target['id'] or 0)
        if target_id <= 0 or target_id == current_wh_id:
            continue
        cur.execute(
            "UPDATE item_location_prefs SET warehouse_id=? WHERE center_id=? AND item_id=? AND warehouse_id=?",
            (target_id, center_id, item_id, current_wh_id)
        )
        moved += int(cur.rowcount or 0)
    return moved


def _autoclassify_item_stock_areas(cur):
    rows = cur.execute("SELECT id,name,COALESCE(stock_area,'') stock_area FROM items ORDER BY id").fetchall()
    updates = []
    reliable_direct = {'SECOS', 'LIMPIEZA', 'CONGELADOS'}
    for r in rows:
        current = normalize_stock_area(r['stock_area'] or '')
        suggested = _classify_stock_area_from_name(r['name'] or '')
        # Regla operativa vigente:
        # - lo no clasificado NO se fuerza a FRESCOS
        # - sí se pueden promocionar automáticamente solo las clasificaciones fiables
        #   (SECOS / LIMPIEZA / CONGELADOS)
        # - FRESCOS sigue yendo a SIN_CLASIFICACION salvo clasificación explícita
        if not current:
            if suggested in reliable_direct:
                updates.append((suggested, int(r['id'])))
            else:
                updates.append(('SIN_CLASIFICACION', int(r['id'])))
            continue
        if current == 'SIN_CLASIFICACION' and suggested in reliable_direct:
            updates.append((suggested, int(r['id'])))
            continue
    if updates:
        cur.executemany("UPDATE items SET stock_area=? WHERE id=?", updates)


def init_db():
    conn = db()
    cur = conn.cursor()
    # Do not perform runtime schema creation when running against Postgres.
    # Schema provisioning should be performed via `backend/migrate.py` and
    # applied before the app starts in production. The Postgres adapter will
    # also conservatively skip SQLite-only tokens, but prefer an explicit no-op.
    try:
        if getattr(cur, '_is_postgres', False):
            try:
                cur.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
            return
    except Exception:
        pass

        # Centralized SQLite schema creation (moved to backend/migrate.py)
        try:
                try:
                        import migrate as _migrate
                except Exception:
                        try:
                                from backend import migrate as _migrate
                        except Exception:
                                _migrate = None
                if _migrate and hasattr(_migrate, "ensure_sqlite_schema"):
                        try:
                                _migrate.ensure_sqlite_schema(conn)
                        except Exception:
                                pass
        except Exception:
                pass
    ensure_columns(cur)
    ensure_items_columns(cur)

    # Datos iniciales
    if cur.execute("SELECT COUNT(*) c FROM centers").fetchone()["c"] == 0:
        centers = [("Restaurante Centro", "RESTAURANT"), ("Restaurante Norte", "RESTAURANT"),
                   ("Restaurante Sur", "RESTAURANT"), ("Restaurante Playa", "RESTAURANT"),
                   ("Restaurante Barrio", "RESTAURANT"), ("Restaurante Premium", "RESTAURANT"),
                   ("Cocina Central", "CENTRAL_KITCHEN")]
        cur.executemany("INSERT INTO centers(name,kind) VALUES(?,?)", centers)
        for ce in cur.execute("SELECT id FROM centers").fetchall():
            for wh in ["Cocina", "Economato", "Cámara"]:
                cur.execute("INSERT INTO warehouses(center_id,name) VALUES(?,?)", (ce["id"], wh))

    try:
        cur.execute("UPDATE warehouses SET name='Cámara' WHERE name LIKE 'CÃ%'")
    except Exception:
        pass

    if cur.execute("SELECT COUNT(*) c FROM items").fetchone()["c"] == 0:
        seed_items = _seed_load_items()
        if seed_items:
            cur.executemany("INSERT INTO items(name,unit,min_qty,max_qty) VALUES(?,?,?,?)", seed_items)
        else:
            cur.executemany("INSERT INTO items(name,unit,min_qty,max_qty) VALUES(?,?,?,?)", [
                ("Solomillo", "g", 0, 0), ("Patata", "g", 0, 0),
                ("Aceite de oliva", "ml", 0, 0), ("Sal", "g", 0, 0), ("Mantequilla", "g", 0, 0)])

    merge_exact_duplicate_items(cur)

    if cur.execute("SELECT COUNT(*) c FROM suppliers").fetchone()["c"] == 0:
        cur.executemany("INSERT INTO suppliers(name,phone,email) VALUES(?,?,?)", [
            ("Referencia Mercasa (Madrid)", None, None),
            ("Proveedor A", "900111111", "a@proveedor.com"),
            ("Proveedor B", "900222222", "b@proveedor.com")])

    sid_row = cur.execute("SELECT id FROM suppliers WHERE name='Referencia Mercasa (Madrid)'").fetchone()
    if sid_row and cur.execute("SELECT COUNT(*) c FROM supplier_item_prices").fetchone()["c"] == 0:
        now = datetime.utcnow().isoformat()
        for (item_name, price_per_purchase, purchase_unit, factor) in _seed_load_prices():
            row = cur.execute("SELECT id FROM items WHERE name=?", (item_name,)).fetchone()
            if not row:
                continue
            cur.execute(
                """INSERT INTO supplier_item_prices(supplier_id,item_id,center_id,price_per_purchase,
                   purchase_unit,purchase_to_base_factor,is_preferred,updated_at) VALUES(?,?,?,?,?,?,?,?)""",
                (sid_row["id"], row["id"], None, float(price_per_purchase), purchase_unit, float(factor), 1, now))

    merge_duplicate_items(cur)
    _autoclassify_item_stock_areas(cur)
    _safe_migrate_movements_to_operational_warehouse(cur)

    if cur.execute("SELECT COUNT(*) c FROM recipes").fetchone()["c"] == 0:
        cur.execute(
            """INSERT INTO recipes(code,name,category,subcategory,waste_pct,contingency_pct,
               target_food_cost_pct,target_margin_pct,manual_price,suggested_price,prep_steps,allergens)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("REC-PRI-0001", "Solomillo a la plancha", "Principales", "Carne", 12, 5, 30, 70, 19.5, 20.0,
             "1. Porcionar.\n2. Salpimentar.\n3. Sellar.\n4. Mantequilla.\n5. Emplatar.", "Leche"))
        r1 = get_last_insert_id(cur)
        cur.executemany(
            "INSERT INTO recipe_ingredients(recipe_id,item_name,qty_gross,qty_net,unit) VALUES (?,?,?,?,?)",
            [(r1, "Solomillo", 220, 200, "g"), (r1, "Sal", 2, 2, "g"), (r1, "Mantequilla", 10, 10, "g")])

    conn.commit()
    conn.close()


def _clear_pending_receipts_runtime():
    conn = db()
    cur = conn.cursor()
    rows = cur.execute("SELECT id FROM receipts WHERE status='PENDING' ORDER BY id").fetchall()
    for r in rows:
        rid = int(r["id"])
        try:
            ph_rows = cur.execute("SELECT file_path FROM receipt_photos WHERE receipt_id=?", (rid,)).fetchall()
            for ph in ph_rows:
                try:
                    fp = UPLOADS_DIR / ph["file_path"]
                    if fp.exists():
                        fp.unlink()
                except Exception:
                    pass
            cur.execute("DELETE FROM receipt_ocr_lines WHERE ocr_run_id IN (SELECT id FROM receipt_ocr_runs WHERE receipt_id=?)", (rid,))
            cur.execute("DELETE FROM receipt_ocr_runs WHERE receipt_id=?", (rid,))
            cur.execute("DELETE FROM receipt_lines WHERE receipt_id=?", (rid,))
            cur.execute("DELETE FROM receipt_photos WHERE receipt_id=?", (rid,))
            cur.execute("DELETE FROM receipts WHERE id=? AND status='PENDING'", (rid,))
        except Exception:
            pass
    conn.commit()
    conn.close()


# ==============================================================================
# ELABORADOS — Stock de artículos producidos con info de porciones y receta
# ==============================================================================

def get_elaborados_stock(center_id=None):
    """
    Devuelve artículos que tienen stock originado en producciones confirmadas,
    con porciones calculadas automáticamente desde la receta asociada.

    Lógica:
    - Busca items cuyo stock acumulado en movements tiene al menos un movimiento
      con nota que empieza por "PRODUCCIÓN"
    - Cruza con production_lines (line_type=IN) para obtener la producción origen
    - Busca la receta cuyo nombre coincide con el item para obtener yield_portions
      y yield_final_qty (gramaje/porciones por lote)
    - Calcula porciones = stock_qty / (yield_final_qty / yield_portions)
    """
    conn = db()
    cur = conn.cursor()

    center_clause = ""
    params = []
    if center_id:
        center_clause = "AND m.center_id = ?"
        params.append(int(center_id))

    # Artículos con stock de producción + info de la última producción que los generó
    sql = f"""
    SELECT
        i.id         item_id,
        i.name       item_name,
        i.unit       unit,
        c.id         center_id,
        c.name       center_name,
        w.id         warehouse_id,
        w.name       warehouse_name,
        COALESCE(SUM(CASE
            WHEN m.movement_type IN ('ENTRADA','IN')  THEN m.qty
            WHEN m.movement_type IN ('SALIDA','OUT')  THEN -m.qty
            ELSE -m.qty
        END), 0)     stock_qty,
        -- Última producción que generó este artículo
        (SELECT p2.id
           FROM productions p2
           JOIN production_lines pl2 ON pl2.production_id = p2.id
          WHERE pl2.item_id = i.id
            AND pl2.line_type = 'IN'
            AND p2.status IN ('CONFIRMED','ARCHIVED')
            {('AND p2.center_id = ?' if center_id else '')}
          ORDER BY p2.id DESC LIMIT 1
        ) last_prod_id,
        (SELECT p2.created_at
           FROM productions p2
           JOIN production_lines pl2 ON pl2.production_id = p2.id
          WHERE pl2.item_id = i.id
            AND pl2.line_type = 'IN'
            AND p2.status IN ('CONFIRMED','ARCHIVED')
            {('AND p2.center_id = ?' if center_id else '')}
          ORDER BY p2.id DESC LIMIT 1
        ) last_prod_at,
        (SELECT p2.note
           FROM productions p2
           JOIN production_lines pl2 ON pl2.production_id = p2.id
          WHERE pl2.item_id = i.id
            AND pl2.line_type = 'IN'
            AND p2.status IN ('CONFIRMED','ARCHIVED')
            {('AND p2.center_id = ?' if center_id else '')}
          ORDER BY p2.id DESC LIMIT 1
        ) last_prod_note,
        -- Receta asociada (nombre = item)
        (SELECT r.id FROM recipes r
          WHERE lower(trim(r.name)) = lower(trim(i.name))
          ORDER BY r.id LIMIT 1
        ) recipe_id,
        (SELECT r.name FROM recipes r
          WHERE lower(trim(r.name)) = lower(trim(i.name))
          ORDER BY r.id LIMIT 1
        ) recipe_name,
        (SELECT r.yield_portions FROM recipes r
          WHERE lower(trim(r.name)) = lower(trim(i.name))
          ORDER BY r.id LIMIT 1
        ) yield_portions,
        (SELECT r.yield_final_qty FROM recipes r
          WHERE lower(trim(r.name)) = lower(trim(i.name))
          ORDER BY r.id LIMIT 1
        ) yield_final_qty,
        (SELECT r.yield_final_unit FROM recipes r
          WHERE lower(trim(r.name)) = lower(trim(i.name))
          ORDER BY r.id LIMIT 1
        ) yield_final_unit
    FROM items i
    JOIN (
        -- Solo items que tienen AL MENOS UN movimiento de producción
        SELECT DISTINCT item_id, center_id, warehouse_id
        FROM movements
        WHERE movement_type IN ('ENTRADA','IN')
          AND note LIKE 'PRODUCCIÓN%'
          {('AND center_id = ?' if center_id else '')}
    ) produced ON produced.item_id = i.id
    JOIN centers c ON c.id = produced.center_id
    JOIN warehouses w ON w.id = produced.warehouse_id
    LEFT JOIN movements m ON m.item_id = i.id
        AND m.center_id = produced.center_id
        AND m.warehouse_id = produced.warehouse_id
    WHERE 1=1
        {center_clause}
    GROUP BY i.id, i.name, i.unit, c.id, c.name, w.id, w.name
    HAVING stock_qty > 0
    ORDER BY c.name, i.name
    """

    # Construir params con los duplicados necesarios para los subqueries
    full_params = []
    if center_id:
        # produced subquery: 1 param
        full_params.append(int(center_id))
        # last_prod_id, last_prod_at, last_prod_note: 3 subqueries × 1 param cada uno
        full_params.extend([int(center_id)] * 3)
        # center_clause: 1 param
        full_params.append(int(center_id))
    
    rows = cur.execute(sql, full_params).fetchall()
    conn.close()

    result = []
    for r in rows:
        stock_qty    = float(r["stock_qty"] or 0)
        yield_qty    = float(r["yield_final_qty"] or 0)
        yield_port   = float(r["yield_portions"] or 0)

        # Calcular porciones: stock / (gramaje_por_porcion)
        # gramaje_por_porcion = yield_final_qty / yield_portions
        porciones = None
        gramaje_porcion = None
        if yield_qty > 0 and yield_port > 0:
            gramaje_porcion = yield_qty / yield_port
            if gramaje_porcion > 0:
                porciones = stock_qty / gramaje_porcion

        result.append({
            "item_id":        r["item_id"],
            "item_name":      r["item_name"],
            "unit":           r["unit"],
            "center_id":      r["center_id"],
            "center_name":    r["center_name"],
            "warehouse_id":   r["warehouse_id"],
            "warehouse_name": r["warehouse_name"],
            "stock_qty":      stock_qty,
            "last_prod_id":   r["last_prod_id"],
            "last_prod_at":   r["last_prod_at"],
            "last_prod_note": r["last_prod_note"],
            "recipe_id":      r["recipe_id"],
            "recipe_name":    r["recipe_name"],
            "yield_portions": yield_port,
            "yield_final_qty": yield_qty,
            "yield_final_unit": r["yield_final_unit"],
            "porciones":      porciones,
            "gramaje_porcion": gramaje_porcion,
        })

    return result


# ==============================================================================
# HELPERS DE ESCALADO DE PRODUCCIONES (v8.7.198)
# ==============================================================================

def _canonical_unit(unit: str) -> str:
    """Normaliza unidades a su forma canónica base."""
    u = (unit or "").strip().lower()
    if u in {"g", "kg", "gr", "gramo", "gramos", "ml", "l", "lt", "lts", "litro", "litros"}: return "g"
    if u in {"ud", "u", "unidad", "unidades"}: return "ud"
    if u in {"racion", "raciones"}: return "raciones"
    if u in {"porcion", "porciones"}: return "porciones"
    return u or "ud"


def _convert_qty(qty: float, from_unit: str, to_unit: str) -> float:
    """Convierte cantidad entre unidades usando _unit_factor."""
    try:
        return float(qty or 0.0) * float(_unit_factor(from_unit, to_unit))
    except Exception:
        return float(qty or 0.0)


def _resolve_recipe_id(cur, recipe_id, recipe_query: str):
    """Resuelve una receta desde ID, código, texto de datalist o búsqueda tolerante.

    Se usa en Producciones e Inventario. No exige que el usuario escriba el
    nombre exacto: normaliza tildes, signos, dobles espacios y tolera errores
    leves como CACIO/CACCIO o PEPE/PEPPE.
    """
    try:
        if str(recipe_id or '').isdigit() and int(recipe_id) > 0:
            row = cur.execute("SELECT id FROM recipes WHERE id=?", (int(recipe_id),)).fetchone()
            if row:
                return int(row[0] if not hasattr(row, 'keys') else row['id'])
    except Exception:
        pass
    q = (recipe_query or '').strip()
    if not q:
        return None

    import re, unicodedata
    from difflib import SequenceMatcher

    def rid(row):
        return int(row[0] if not hasattr(row, 'keys') else row['id'])

    q_up = q.upper().strip()
    # Si viene de un datalist tipo "REC-SAL-0004 · CACIO PEPPE", probar código y nombre.
    parts = [x.strip() for x in re.split(r'[·\|]', q_up) if x.strip()]
    candidates_q = [q_up] + parts
    for cand in candidates_q:
        row = cur.execute("SELECT id FROM recipes WHERE upper(trim(code))=? ORDER BY id LIMIT 1", (cand,)).fetchone()
        if row: return rid(row)
        row = cur.execute("SELECT id FROM recipes WHERE upper(trim(name))=? ORDER BY id LIMIT 1", (cand,)).fetchone()
        if row: return rid(row)

    for cand in candidates_q:
        row = cur.execute("SELECT id FROM recipes WHERE upper(name) LIKE ? ORDER BY length(name), name LIMIT 1", (cand + '%',)).fetchone()
        if row: return rid(row)
        row = cur.execute("SELECT id FROM recipes WHERE upper(name) LIKE ? ORDER BY length(name), name LIMIT 1", ('%' + cand + '%',)).fetchone()
        if row: return rid(row)

    def norm(v):
        txt = str(v or '').strip().lower()
        txt = unicodedata.normalize('NFKD', txt)
        txt = ''.join(ch for ch in txt if not unicodedata.combining(ch))
        txt = re.sub(r'[^a-z0-9]+', ' ', txt)
        txt = re.sub(r'(.)\1{1,}', r'\1', txt)  # peppe/caccio -> pepe/cacio
        return ' '.join(txt.split())

    nq = norm(q)
    if not nq:
        return None
    active_clause = db_truthy_sql("is_active", cur)
    rows = cur.execute(f"SELECT id,code,name,category,subcategory FROM recipes WHERE {active_clause} ORDER BY name LIMIT 800").fetchall()
    best = None
    best_score = 0.0
    q_tokens = set(nq.split())
    for r in rows:
        name = r['name'] if hasattr(r, 'keys') else r[2]
        code = r['code'] if hasattr(r, 'keys') else r[1]
        hay = norm(f"{code or ''} {name or ''}")
        if not hay:
            continue
        h_tokens = set(hay.split())
        token_score = (len(q_tokens & h_tokens) / max(len(q_tokens), 1)) if q_tokens else 0
        ratio = SequenceMatcher(None, nq, hay).ratio()
        contains = 1.0 if nq in hay or hay in nq else 0.0
        score = max(token_score, ratio, contains)
        if score > best_score:
            best_score = score
            best = r
    if best is not None and best_score >= 0.48:
        return rid(best)
    return None



# ==============================================================================
# CORRECCIONES OPERATIVAS LIGERAS DE STARTUP
# ==============================================================================

def apply_startup_business_corrections():
    """Correcciones idempotentes sobre la base real activa.

    No borra datos operativos. Solo normaliza reglas cerradas:
    - hierbas frescas por manojo;
    - AGUACHILES como preparación;
    - min/max heredados en gramos cuando la unidad ya está en kg.
    """
    herbs = {
        'ALBAHACA': 1.80, 'CILANTRO': 1.50, 'CEBOLLINO': 1.60, 'MENTA': 1.80,
        'PEREJIL': 0.80, 'HIERBABUENA': 1.80, 'ENELDO': 1.80, 'ROMERO': 1.60,
        'TOMILLO': 1.60, 'CEBOLLETA': 1.20,
    }
    def _n(v):
        s = unicodedata.normalize('NFD', str(v or '').upper())
        s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
        s = re.sub(r'[^A-Z0-9]+', ' ', s)
        return re.sub(r'\s+', ' ', s).strip()
    try:
        conn = db(); cur = conn.cursor(); ensure_columns(cur)
        cols = set(get_table_columns_from_cursor(cur, 'items'))
        rows = cur.execute('SELECT id,name,unit,min_qty,max_qty FROM items').fetchall()
        for r in rows:
            name_n = _n(r['name'])
            if name_n in herbs:
                sets = ['unit=?','stock_area=?','order_category=?','item_type=?','current_price=?']
                vals = ['manojo','FRESCOS','verduras','INSUMO',herbs[name_n]]
                extras = {
                    'price_status':'PRECIO_ESTIMADO',
                    'price_source':'MERCADO_ESTIMADO_ESP_2025_2026',
                    'price_confidence':'media',
                    'price_reference_year':'2025/2026',
                    'price_operational_unit':'manojo',
                    'price_operational_value':herbs[name_n],
                    'price_notes':'Hierba fresca operativa por manojo. Validar precio con proveedor/albarán.',
                }
                for k,v in extras.items():
                    if k in cols:
                        sets.append(f'{k}=?'); vals.append(v)
                vals.append(int(r['id']))
                cur.execute(f"UPDATE items SET {', '.join(sets)} WHERE id=?", tuple(vals))
            if name_n in {'AGUACHILE','AGUACHILES'} or name_n.startswith('AGUACHILE'):
                sets = ['unit=?','stock_area=?','order_category=?','item_type=?']
                vals = ['kg','PREPARACIONES','preparaciones','PREPARACION']
                extras = {
                    'price_status':'PRECIO_ESTIMADO',
                    'price_source':'COSTE_PREPARACION_ESTIMADO',
                    'price_confidence':'baja',
                    'price_operational_unit':'kg',
                    'price_notes':'Preparación/subreceta. No mostrar como insumo de compra manual.',
                }
                for k,v in extras.items():
                    if k in cols:
                        sets.append(f'{k}=?'); vals.append(v)
                vals.append(int(r['id']))
                cur.execute(f"UPDATE items SET {', '.join(sets)} WHERE id=?", tuple(vals))
        # Min/max heredados: 20000 con artículo kg debe ser 20, no 20000 kg.
        for r in cur.execute("SELECT id,unit,min_qty,max_qty FROM items").fetchall():
            unit = r['unit'] or ''
            min2 = normalize_minmax_qty_for_base(r['min_qty'], unit)
            max2 = normalize_minmax_qty_for_base(r['max_qty'], unit)
            if abs(float(r['min_qty'] or 0) - float(min2 or 0)) > 1e-9 or abs(float(r['max_qty'] or 0) - float(max2 or 0)) > 1e-9:
                cur.execute('UPDATE items SET min_qty=?, max_qty=? WHERE id=?', (min2, max2, int(r['id'])))
        for r in cur.execute("SELECT id,min_qty,max_qty,item_id FROM item_location_prefs").fetchall():
            item = cur.execute('SELECT unit FROM items WHERE id=?', (int(r['item_id']),)).fetchone()
            unit = item['unit'] if item else ''
            min2 = normalize_minmax_qty_for_base(r['min_qty'], unit)
            max2 = normalize_minmax_qty_for_base(r['max_qty'], unit)
            if abs(float(r['min_qty'] or 0) - float(min2 or 0)) > 1e-9 or abs(float(r['max_qty'] or 0) - float(max2 or 0)) > 1e-9:
                cur.execute('UPDATE item_location_prefs SET min_qty=?, max_qty=? WHERE id=?', (min2, max2, int(r['id'])))
        conn.commit(); conn.close()
        return True
    except Exception as exc:
        try:
            print(f"STARTUP_BUSINESS_CORRECTIONS_SKIP reason={exc}")
        except Exception:
            pass
        return False

# ==============================================================================
# GET_PRODUCTION_STOCKS — v8.7.198 (versión mejorada de get_elaborados_stock)
# Muestra stock de artículos que son resultado de producciones confirmadas.
# No filtra por nota "PRODUCCIÓN%" — usa production_lines directamente.
# ==============================================================================

def get_production_stocks(cur, center_id=None):
    """
    Stock de artículos que son resultado de producciones confirmadas.

    Blindajes v8_7_291:
    - Acepta line_type IN / ENTRADA / PRODUCCION / PRODUCCIÓN.
    - Acepta status CONFIRMED / CONFIRMADA.
    - Si una producción confirmada no tiene línea de entrada de elaborado, la devuelve
      como incidencia visible para no ocultar producciones ya hechas.
    - La receta se cruza primero por produced_item_id y después por nombre.
    """
    center_where = ""
    params = []
    if center_id:
        center_where = "WHERE c.id=?"
        params.append(int(center_id))

    sql = f"""
    WITH produced_items AS (
        SELECT DISTINCT pl.item_id
          FROM productions p
          JOIN production_lines pl ON pl.production_id=p.id
         WHERE UPPER(COALESCE(p.status,'')) IN ('CONFIRMED','CONFIRMADA','CONFIRMADO','ARCHIVED','ARCHIVADA','ARCHIVADO')
           AND UPPER(COALESCE(pl.line_type,'')) IN ('IN','ENTRADA','PRODUCCION','PRODUCCIÓN')
        UNION
        SELECT DISTINCT produced_item_id
          FROM recipes
         WHERE COALESCE(produced_item_id,0)>0
    )
    SELECT c.id center_id,
           c.name center_name,
           w.id warehouse_id,
           w.name warehouse_name,
           i.id item_id,
           i.name item_name,
           i.unit,
           i.current_price,
           COALESCE(SUM(CASE
               WHEN m.movement_type IN ('ENTRADA','IN')  THEN m.qty
               WHEN m.movement_type IN ('SALIDA','OUT')  THEN -m.qty
               ELSE 0
           END), 0) stock_qty,
           (SELECT p.id
              FROM productions p
              JOIN production_lines pl ON pl.production_id=p.id
             WHERE UPPER(COALESCE(p.status,'')) IN ('CONFIRMED','CONFIRMADA','CONFIRMADO','ARCHIVED','ARCHIVADA','ARCHIVADO')
               AND UPPER(COALESCE(pl.line_type,'')) IN ('IN','ENTRADA','PRODUCCION','PRODUCCIÓN')
               AND pl.item_id=i.id
               AND p.center_id=c.id
               AND p.warehouse_id=w.id
             ORDER BY p.id DESC LIMIT 1) last_prod_id,
           (SELECT p.created_at
              FROM productions p
              JOIN production_lines pl ON pl.production_id=p.id
             WHERE UPPER(COALESCE(p.status,'')) IN ('CONFIRMED','CONFIRMADA','CONFIRMADO','ARCHIVED','ARCHIVADA','ARCHIVADO')
               AND UPPER(COALESCE(pl.line_type,'')) IN ('IN','ENTRADA','PRODUCCION','PRODUCCIÓN')
               AND pl.item_id=i.id
               AND p.center_id=c.id
               AND p.warehouse_id=w.id
             ORDER BY p.id DESC LIMIT 1) last_production_at,
           (SELECT p.note
              FROM productions p
              JOIN production_lines pl ON pl.production_id=p.id
             WHERE UPPER(COALESCE(p.status,'')) IN ('CONFIRMED','CONFIRMADA','CONFIRMADO','ARCHIVED','ARCHIVADA','ARCHIVADO')
               AND UPPER(COALESCE(pl.line_type,'')) IN ('IN','ENTRADA','PRODUCCION','PRODUCCIÓN')
               AND pl.item_id=i.id
               AND p.center_id=c.id
               AND p.warehouse_id=w.id
             ORDER BY p.id DESC LIMIT 1) last_prod_note,
           COALESCE(
             (SELECT r.id FROM recipes r WHERE COALESCE(r.produced_item_id,0)=i.id ORDER BY r.id LIMIT 1),
             (SELECT r.id FROM recipes r WHERE lower(trim(r.name))=lower(trim(i.name)) ORDER BY r.id LIMIT 1)
           ) recipe_id,
           COALESCE(
             (SELECT r.name FROM recipes r WHERE COALESCE(r.produced_item_id,0)=i.id ORDER BY r.id LIMIT 1),
             (SELECT r.name FROM recipes r WHERE lower(trim(r.name))=lower(trim(i.name)) ORDER BY r.id LIMIT 1)
           ) recipe_name,
           COALESCE(
             (SELECT r.yield_portions FROM recipes r WHERE COALESCE(r.produced_item_id,0)=i.id ORDER BY r.id LIMIT 1),
             (SELECT r.yield_portions FROM recipes r WHERE lower(trim(r.name))=lower(trim(i.name)) ORDER BY r.id LIMIT 1)
           ) yield_portions,
           COALESCE(
             (SELECT r.yield_final_qty FROM recipes r WHERE COALESCE(r.produced_item_id,0)=i.id ORDER BY r.id LIMIT 1),
             (SELECT r.yield_final_qty FROM recipes r WHERE lower(trim(r.name))=lower(trim(i.name)) ORDER BY r.id LIMIT 1)
           ) yield_final_qty,
           COALESCE(
             (SELECT r.yield_final_unit FROM recipes r WHERE COALESCE(r.produced_item_id,0)=i.id ORDER BY r.id LIMIT 1),
             (SELECT r.yield_final_unit FROM recipes r WHERE lower(trim(r.name))=lower(trim(i.name)) ORDER BY r.id LIMIT 1)
           ) yield_final_unit,
           (SELECT mm.created_at FROM movements mm
             WHERE mm.center_id=c.id AND mm.warehouse_id=w.id AND mm.item_id=i.id
             ORDER BY mm.id DESC LIMIT 1) last_move_at,
           (SELECT mm.note FROM movements mm
             WHERE mm.center_id=c.id AND mm.warehouse_id=w.id AND mm.item_id=i.id
             ORDER BY mm.id DESC LIMIT 1) last_move_note
      FROM centers c
      JOIN warehouses w ON w.center_id=c.id
      JOIN produced_items pi ON 1=1
      JOIN items i ON i.id=pi.item_id
      LEFT JOIN movements m ON m.center_id=c.id
                            AND m.warehouse_id=w.id
                            AND m.item_id=i.id
      {center_where}
     GROUP BY c.id, c.name, w.id, w.name, i.id, i.name, i.unit, i.current_price
        HAVING ABS(COALESCE(SUM(CASE
                             WHEN m.movement_type IN ('ENTRADA','IN')  THEN m.qty
                             WHEN m.movement_type IN ('SALIDA','OUT')  THEN -m.qty
                             ELSE 0 END), 0)) > 0.000001
                OR (
                     SELECT p.id
                         FROM productions p
                         JOIN production_lines pl ON pl.production_id=p.id
                        WHERE UPPER(COALESCE(p.status,'')) IN ('CONFIRMED','CONFIRMADA','CONFIRMADO','ARCHIVED','ARCHIVADA','ARCHIVADO')
                            AND UPPER(COALESCE(pl.line_type,'')) IN ('IN','ENTRADA','PRODUCCION','PRODUCCIÓN')
                            AND pl.item_id=i.id
                            AND p.center_id=c.id
                            AND p.warehouse_id=w.id
                        ORDER BY p.id DESC LIMIT 1
                ) IS NOT NULL
     ORDER BY c.name, w.name, i.name
    """

    rows = cur.execute(sql, params).fetchall()
    payload = []
    seen_prod = set()
    for r in rows:
        try:
            raw_qty = float(r['stock_qty'] or 0)
            qty = raw_qty
            price = float(r['current_price'] or 0)
            value = qty * price if qty > 0 and price > 0 else 0.0
            unit_low = str(r['unit'] or '').lower()
            if unit_low in {'ud', 'porcion', 'porciones', 'racion', 'raciones'}:
                porciones = round(qty, 1) if qty > 0 else None
                gramaje_porcion = None
            else:
                yf_qty  = float(r['yield_final_qty']  or 0)
                yf_port = float(r['yield_portions']   or 0)
                if yf_qty > 0 and yf_port > 0 and qty > 0:
                    gramaje_base = yf_qty / yf_port
                    porciones = round(qty / gramaje_base, 1) if gramaje_base > 0 else None
                    gramaje_porcion = gramaje_base
                else:
                    porciones = None
                    gramaje_porcion = None
        except Exception:
            qty = 0.0; value = 0.0; porciones = None; gramaje_porcion = None
        d = dict(r)
        d['stock_qty'] = qty
        d['stock_value'] = round(value, 4)
        d['porciones_disponibles'] = porciones
        d['gramaje_porcion'] = gramaje_porcion if 'gramaje_porcion' in locals() else None
        d['issue'] = ''
        if d.get('last_prod_id'):
            seen_prod.add(int(d['last_prod_id']))
        if abs(qty) <= 0.000001 and d.get('last_prod_id'):
            d['issue'] = 'Producción confirmada sin stock positivo visible'
        payload.append(d)

    # Incidencias: producciones confirmadas sin línea IN de elaborado. Se muestran para revisar
    # produced_item_id/entrada de elaborado, en vez de ocultarlas como si no existieran.
    inc_params = []
    center_clause = ''
    if center_id:
        center_clause = 'AND p.center_id=?'
        inc_params.append(int(center_id))
    inc_rows = cur.execute(f"""
        SELECT p.id production_id, p.center_id, c.name center_name, p.warehouse_id, w.name warehouse_name,
               p.created_at, COALESCE(p.note,'') note
          FROM productions p
          JOIN centers c ON c.id=p.center_id
          JOIN warehouses w ON w.id=p.warehouse_id
         WHERE UPPER(COALESCE(p.status,'')) IN ('CONFIRMED','CONFIRMADA','CONFIRMADO','ARCHIVED','ARCHIVADA','ARCHIVADO')
           {center_clause}
           AND NOT EXISTS (
               SELECT 1 FROM production_lines pl
                WHERE pl.production_id=p.id
                  AND UPPER(COALESCE(pl.line_type,'')) IN ('IN','ENTRADA','PRODUCCION','PRODUCCIÓN')
           )
         ORDER BY p.id DESC
    """, tuple(inc_params)).fetchall()
    for r in inc_rows:
        pid = int(r['production_id'] or 0)
        if pid in seen_prod:
            continue
        payload.append({
            'center_id': int(r['center_id'] or 0),
            'center_name': r['center_name'],
            'warehouse_id': int(r['warehouse_id'] or 0),
            'warehouse_name': r['warehouse_name'],
            'item_id': 0,
            'item_name': f"Producción #{pid} sin elaborado vinculado",
            'unit': 'kg',
            'current_price': 0,
            'stock_qty': 0.0,
            'stock_value': 0.0,
            'porciones_disponibles': None,
            'gramaje_porcion': None,
            'last_prod_id': pid,
            'last_production_at': r['created_at'],
            'last_prod_note': r['note'],
            'recipe_id': None,
            'recipe_name': '',
            'issue': 'Falta línea de entrada de elaborado / produced_item_id',
        })
    return payload


# ==============================================================================
# COLLECT PRODUCTION INPUTS — v8.7.198
# Recoge ingredientes de una receta para producción con escalado correcto
# ==============================================================================

def _resolve_item_for_production(cur, *, item_id=None, item_name=""):
    """Resuelve un artículo consumible de producción por ID o nombre."""
    try:
        iid = int(item_id or 0)
    except Exception:
        iid = 0
    if iid:
        row = cur.execute("SELECT id,unit,name FROM items WHERE id=?", (iid,)).fetchone()
        if row:
            return row
    qn = (item_name or "").strip().lower()
    if not qn:
        return None
    row = cur.execute("SELECT id,unit,name FROM items WHERE lower(trim(name))=? ORDER BY id LIMIT 1", (qn,)).fetchone()
    if row:
        return row
    row = cur.execute("SELECT id,unit,name FROM items WHERE lower(name) LIKE ? ORDER BY id LIMIT 1", (qn + '%',)).fetchone()
    return row


def _collect_recipe_production_inputs(cur, recipe_id: int, scale_factor: float = 1.0, depth: int = 0, visited=None):
    """
    Recoge las líneas de entrada (OUT) para producir una receta.
    Soporta subrecetas recursivas y escalado por raciones/kg/lotes.
    Retorna: (lines, pending_names)
    """
    visited = set(visited or set())
    recipe_id = int(recipe_id or 0)
    if recipe_id <= 0 or depth > 6 or recipe_id in visited:
        return [], []
    visited.add(recipe_id)

    rows = cur.execute(
        """SELECT item_id, subrecipe_id, qty_gross, qty_net, unit, input_unit, item_name, waste_pct_ing
               FROM recipe_ingredients
              WHERE recipe_id=?
              ORDER BY id""",
        (recipe_id,),
    ).fetchall()
    out = []
    pending = []

    for r in rows:
        gross_base = _production_required_gross(cur, r)
        qty_base = float(gross_base or 0.0) * float(scale_factor or 1.0)
        if qty_base <= 0:
            continue

        item = _resolve_item_for_production(cur, item_id=r["item_id"], item_name=r["item_name"] or "")
        if item:
            base_unit  = (item["unit"] or "ud").strip() or "ud"
            input_unit = (r["input_unit"] or r["unit"] or base_unit).strip() or base_unit
            source_unit = _canonical_unit(input_unit or r["unit"] or base_unit)
            try:
                qty_base_for_stock = float(_convert_qty(qty_base, source_unit, base_unit))
            except Exception:
                qty_base_for_stock = float(qty_base)
            try:
                qty_input = float(_convert_qty(qty_base, source_unit, input_unit))
            except Exception:
                qty_input = float(qty_base)
            out.append({
                "item_id":    int(item["id"]),
                "item_name":  (item["name"] or "").strip() if item["name"] is not None else "",
                "qty_base":   float(qty_base_for_stock),
                "base_unit":  base_unit,
                "input_unit": input_unit,
                "qty_input":  float(qty_input),
            })
            continue

        subrecipe_id = int(r["subrecipe_id"] or 0)
        if subrecipe_id > 0:
            sub = cur.execute(
                "SELECT id,name,yield_final_qty,yield_final_unit FROM recipes WHERE id=?",
                (subrecipe_id,),
            ).fetchone()
            # Primero intentar consumir el elaborado como artículo de stock
            if sub and (sub["name"] or "").strip():
                sub_item = _resolve_item_for_production(cur, item_name=(sub["name"] or "").strip())
                if sub_item:
                    base_unit  = (sub_item["unit"] or "ud").strip() or "ud"
                    sub_yield_unit = (sub["yield_final_unit"] or "").strip() if sub else ""
                    input_unit = (r["input_unit"] or r["unit"] or sub_yield_unit or base_unit).strip() or base_unit
                    source_unit = _canonical_unit(input_unit or r["unit"] or sub_yield_unit or base_unit)
                    try:
                        qty_base_for_stock = float(_convert_qty(qty_base, source_unit, base_unit))
                    except Exception:
                        qty_base_for_stock = float(qty_base)
                    try:
                        qty_input = float(_convert_qty(qty_base, source_unit, input_unit))
                    except Exception:
                        qty_input = float(qty_base)
                    out.append({
                        "item_id":    int(sub_item["id"]),
                        "item_name":  (sub_item["name"] or "").strip() if sub_item["name"] is not None else "",
                        "qty_base":   float(qty_base_for_stock),
                        "base_unit":  base_unit,
                        "input_unit": input_unit,
                        "qty_input":  float(qty_input),
                    })
                    continue

            # Si no existe artículo, expandir subreceta recursivamente
            if sub and float(sub["yield_final_qty"] or 0.0) > 0 and (sub["yield_final_unit"] or "").strip():
                sub_unit = (sub["yield_final_unit"] or "").strip()
                sub_can  = _canonical_unit(sub_unit)
                try:
                    sub_yield_base = float(_convert_qty(float(sub["yield_final_qty"] or 0.0), sub_unit, sub_can))
                except Exception:
                    sub_yield_base = 0.0
                if sub_yield_base > 0:
                    child_scale = float(qty_base) / float(sub_yield_base)
                    child_lines, child_pending = _collect_recipe_production_inputs(
                        cur, int(subrecipe_id), child_scale, depth + 1, visited)
                    out.extend(child_lines)
                    pending.extend(child_pending)
                    continue

            pending.append((sub["name"] if sub and sub["name"] else r["item_name"] or "subreceta").strip())
            continue

        if (r["item_name"] or "").strip():
            pending.append((r["item_name"] or "").strip())

    return out, pending
