from collections import OrderedDict

from app.core import production_with_lines, _collect_recipe_production_inputs


def _ln_get(ln, key, default=None):
    try:
        if isinstance(ln, dict):
            return ln.get(key, default)
        return ln[key]
    except Exception:
        return default


def _parse_charge_summary(note: str = "") -> OrderedDict[str, int]:
    out: OrderedDict[str, int] = OrderedDict()
    for raw in [x.strip() for x in str(note or '').split(' + ') if x.strip()]:
        if '·' in raw:
            name, rhs = [x.strip() for x in raw.split('·', 1)]
            digits = ''.join(ch for ch in rhs.lower() if (ch.isdigit() or ch == '.'))
            try:
                qty = int(float(digits)) if digits else 1
            except Exception:
                qty = 1
            out[name] = max(1, int(qty))
        else:
            out[raw] = out.get(raw, 0) + 1
    return out


def _build_recipe_breakdown(cur, production_detail: dict | None):
    if not production_detail:
        return []
    parts = _parse_charge_summary(production_detail.get('note') or '')
    sections = []
    for recipe_name, loads in parts.items():
        rec = cur.execute("SELECT id,name FROM recipes WHERE lower(trim(name))=lower(trim(?)) ORDER BY id LIMIT 1", ((recipe_name or '').strip(),)).fetchone()
        if not rec:
            continue
        collected_lines, _ = _collect_recipe_production_inputs(cur, int(rec['id']), float(loads or 1))
        grouped = OrderedDict()
        for ln in collected_lines:
            item_id = int(_ln_get(ln, 'item_id', 0) or 0)
            if item_id <= 0:
                continue
            item_name = _ln_get(ln, 'item_name') or _ln_get(ln, 'name') or _ln_get(ln, 'recipe_name') or f"ITEM {item_id}"
            input_unit = (_ln_get(ln, 'input_unit') or _ln_get(ln, 'base_unit') or 'ud')
            base_unit = (_ln_get(ln, 'base_unit') or input_unit or 'ud')
            g = grouped.setdefault(item_id, {
                'item_name': item_name,
                'qty_input': 0.0,
                'input_unit': input_unit,
                'qty_base': 0.0,
                'base_unit': base_unit,
            })
            g['qty_input'] += float(_ln_get(ln, 'qty_input', 0.0) or 0.0)
            g['qty_base'] += float(_ln_get(ln, 'qty_base', 0.0) or 0.0)
        sections.append({
            'recipe_id': int(rec['id']),
            'recipe_name': rec['name'],
            'loads': int(loads or 1),
            'lines': list(grouped.values()),
        })
    return sections


def get_production_detail(cur, production_id):
    if not str(production_id or '').isdigit():
        return None
    detail = production_with_lines(cur, int(production_id))
    if not detail:
        return None
    detail['recipe_breakdown'] = _build_recipe_breakdown(cur, detail)
    return detail


def list_productions(cur, center_id=None, show_archived: bool = False, production_group_filter: str = ""):
    status_clause = "p.status='ARCHIVED'" if show_archived else "COALESCE(p.status,'') <> 'ARCHIVED'"
    group_filter = (production_group_filter or '').strip()
    group_clause = " AND COALESCE(p.production_group,'Otros')=?" if group_filter else ""
    extra = [group_filter] if group_filter else []
    if center_id:
        rows = cur.execute(
            f"""SELECT p.id,p.center_id,p.warehouse_id,p.status,p.created_at,p.note,
                       COALESCE(p.production_group,'Otros') production_group,
                       c.name center_name,w.name warehouse_name
                  FROM productions p
                  JOIN centers c ON c.id=p.center_id
                  JOIN warehouses w ON w.id=p.warehouse_id
                 WHERE p.center_id=? AND {status_clause}{group_clause}
                 ORDER BY p.id DESC""",
            tuple([int(center_id)] + extra),
        ).fetchall()
    else:
        rows = cur.execute(
            f"""SELECT p.id,p.center_id,p.warehouse_id,p.status,p.created_at,p.note,
                       COALESCE(p.production_group,'Otros') production_group,
                       c.name center_name,w.name warehouse_name
                  FROM productions p
                  JOIN centers c ON c.id=p.center_id
                  JOIN warehouses w ON w.id=p.warehouse_id
                 WHERE {status_clause}{group_clause}
                 ORDER BY p.id DESC""",
            tuple(extra),
        ).fetchall()
    return [{k: r[k] for k in r.keys()} for r in rows]
