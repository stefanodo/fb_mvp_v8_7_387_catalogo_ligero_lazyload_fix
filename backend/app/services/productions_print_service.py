from app.core import fmt_dt, human_qty, status_label


def _esc(value):
    return (value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def production_line_qty_str(line):
    try:
        q = float(line.get("qty_input") or 0)
        u = (line.get("input_unit") or line.get("base_unit") or "").strip()
        return _esc(human_qty(q, u))
    except Exception:
        return _esc(str(line.get("qty_base") or ""))


def render_single_production_print(pd: dict) -> str:
    lines = pd.get("lines") or []
    rows = "".join(
        f"<tr><td>{_esc(l.get('line_type',''))}</td><td>{_esc(l.get('item_name',''))}</td>"
        f"<td style='text-align:right'>{production_line_qty_str(l)}</td></tr>"
        for l in lines
    )
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>Producción #{pd['id']}</title>
<style>
  @page {{ size:A4; margin:14mm; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,Arial,sans-serif; font-size:12px; }}
  h1 {{ font-size:18px; margin:0 0 6px 0; }}
  .meta {{ margin:0 0 12px 0; color:#333; }}
  table {{ width:100%; border-collapse:collapse; }}
  th,td {{ border:1px solid #999; padding:6px; }}
  th {{ background:#f2f2f2; text-align:left; }}
  .print-footer {{ margin-top:auto; padding-top:10mm; text-align:right; font-size:9px; color:#666; }}
</style></head><body>
<h1>Producción #{pd['id']} · {_esc(pd.get('center_name',''))} · {_esc(pd.get('warehouse_name',''))}</h1>
<div class='meta'>
  <div><b>Estado:</b> {_esc(status_label(pd.get('status','')))}</div>
  <div><b>Fecha:</b> {_esc(fmt_dt(pd.get('created_at','')))}</div>
  <div><b>Nota:</b> {_esc(pd.get('note','') or '—')}</div>
</div>
<table><thead><tr><th>Tipo</th><th>Artículo</th><th style='text-align:right'>Cantidad</th></tr></thead>
<tbody>{rows}</tbody></table>
<div class='print-footer'>F&amp;B MAC System · Created by Mauro Ciccarelli</div>
<script>window.print();</script>
</body></html>"""


def render_group_print(rows, production_group: str) -> str:
    def card_row(r):
        note = r['note'] or f"PRODUCCIÓN #{r['id']}"
        return (
            f"<div class='card'>"
            f"<div class='title'>{_esc(note)}</div>"
            f"<div class='meta'>#{int(r['id'])} · {_esc(r['warehouse_name'] or '')} · "
            f"{_esc(fmt_dt(r['created_at']) or '')} · {_esc(status_label(r['status'] or ''))}</div>"
            f"</div>"
        )

    cards = ''.join(card_row(r) for r in rows)
    return f"""<!doctype html><html><head><meta charset='utf-8'>
<title>Partida {_esc(production_group)}</title>
<style>
@page {{ size:A4; margin:12mm; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,Arial,sans-serif; font-size:12px; color:#111; }}
h1 {{ font-size:20px; margin:0 0 8px 0; }}
.meta0 {{ color:#555; margin:0 0 12px 0; }}
.grid {{ display:grid; grid-template-columns:1fr; gap:10px; }}
.card {{ border:1px solid #bbb; border-radius:8px; padding:10px; break-inside:avoid; }}
.title {{ font-weight:700; font-size:14px; margin-bottom:4px; }}
.meta {{ color:#444; }}
</style></head><body>
<h1>Partida · {_esc(production_group)}</h1>
<div class='meta0'>{len(rows)} producciones</div>
<div class='grid'>{cards}</div>
<script>window.print();</script></body></html>"""
