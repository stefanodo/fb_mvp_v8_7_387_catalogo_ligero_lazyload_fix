from __future__ import annotations

from app.core import db
import unicodedata


def _norm_item_name(v: str) -> str:
    s = unicodedata.normalize('NFKD', str(v or ''))
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    return ' '.join(s.lower().strip().split())


def stock_page_url(*, center_id:int=0, ok:str|None=None, err:str|None=None, anchor:str='stock', stock_section:str|None=None, stock_item_id:int|str|None=None, stock_wh_id:int|str|None=None, stock_q:str|None=None) -> str:
    params = [f"page=stock", f"center_id={int(center_id or 0)}"]
    if stock_section:
        params.append(f"stock_section={stock_section}")
    if stock_item_id not in (None, '', 0, '0'):
        params.append(f"stock_item_id={int(stock_item_id)}")
    if stock_wh_id not in (None, '', 0, '0'):
        params.append(f"stock_wh_id={int(stock_wh_id)}")
    if stock_q:
        from urllib.parse import quote_plus
        params.append(f"stock_q={quote_plus(str(stock_q))}")
    if ok:
        params.append(f"{ok}=1")
    if err:
        params.append(f"err={err}")
    return f"/?{'&'.join(params)}#{anchor}"


def resolve_item_id_strict(item_id, item_query:str=''):
    """Resuelve artículo existente sin crear duplicados ni movimientos huérfanos.

    Tolera texto con [#id], mayúsculas/minúsculas, acentos y coincidencia por prefijo
    única. Esto evita casos como PUERRO escrito manualmente que no vincula item_id.
    """
    conn = db(); cur = conn.cursor(); row = None
    raw = (item_query or '').strip()
    if str(item_id or '').isdigit() and int(item_id or 0) > 0:
        row = cur.execute('SELECT id FROM items WHERE id=?', (int(item_id),)).fetchone()
    if not row and raw:
        import re
        m = re.search(r'\[#(\d+)\]', raw)
        if m:
            row = cur.execute('SELECT id FROM items WHERE id=?', (int(m.group(1)),)).fetchone()
        name = re.sub(r'\s*\[#\d+\]\s*$', '', raw).strip()
        if not row and name:
            row = cur.execute('SELECT id,name FROM items WHERE lower(trim(name))=lower(trim(?)) LIMIT 1', (name,)).fetchone()
        if not row and name:
            qn = _norm_item_name(name)
            rows = cur.execute('SELECT id,name FROM items ORDER BY name COLLATE NOCASE').fetchall()
            exact = [r for r in rows if _norm_item_name(r['name']) == qn]
            starts = [r for r in rows if _norm_item_name(r['name']).startswith(qn)]
            contains = [r for r in rows if qn and qn in _norm_item_name(r['name'])]
            cand = exact or starts or contains
            # Si hay varios, tomar el más corto/natural, no crear nada nuevo.
            if cand:
                cand = sorted(cand, key=lambda r: (len(str(r['name'] or '')), str(r['name'] or '').lower()))
                row = cand[0]
    conn.close()
    return int(row['id']) if row else None
