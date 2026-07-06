from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from typing import Optional
from app.core import (
    human_qty, fmt_dt, status_label, fmt_num, fmt_price,
    display_price_from_base, preferred_price_unit, _ocr_state_label,
    db, get_dashboard_data, get_production_stocks
)
from pathlib import Path

router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / 'templates'

def _fmt_qty(value, decimals: int = 3):
    try:
        if value is None:
            return "0"
        v = float(value)
    except Exception:
        return str(value)
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return f"{v:.{decimals}f}".rstrip("0").rstrip(".")


def _normalize_search_text(value: str) -> str:
    if not value:
        return ""
    try:
        return str(value).strip().lower()
    except Exception:
        return str(value or "").strip().lower()


def _jinja_search_test(value, pattern) -> bool:
    return _normalize_search_text(pattern) in _normalize_search_text(value)


templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals.update(
    human_qty=human_qty,
    fmt_dt=fmt_dt,
    status_label=status_label,
    fmt_num=fmt_num,
    fmt_price=fmt_price,
    display_price_from_base=display_price_from_base,
    preferred_price_unit=preferred_price_unit,
    ocr_state_label=_ocr_state_label,
)
templates.env.filters['fmt_qty'] = _fmt_qty
templates.env.tests['search'] = _jinja_search_test


@router.get('/_lazy/stock_table')
def lazy_stock_table(request: Request, center_id: Optional[int] = 0):
    try:
        centers, warehouses, items, stocks, summary, recipes = get_dashboard_data(int(center_id) if center_id else None)
        # Render the partial template used by the full page so markup stays consistent
        context = {
            'request': request,
            'stocks': stocks,
            'selected_center_id': int(center_id or 0),
            'stock_q': '',
            'stock_q_norm': '',
            'stock_item_id_q': '',
            'stock_wh_id_q': '',
            'human_qty': human_qty,
        }
        html = templates.get_template('partials/stock_table.html').render(context)
        return HTMLResponse(html)
    except Exception as e:
        return JSONResponse({'ok': False, 'error': str(e)}, status_code=500)


@router.get('/_lazy/inventory_fragment')
def lazy_inventory_fragment(request: Request, center_id: Optional[int] = 0):
    try:
        centers, warehouses, items, stocks, summary, recipes = get_dashboard_data(int(center_id) if center_id else None)
        conn = db(); cur = conn.cursor()
        production_stocks = get_production_stocks(cur, int(center_id) if center_id else None)
        conn.close()
        from app.main import _build_inventory_context
        inventory_ctx = _build_inventory_context(
            center_id=int(center_id or 0),
            warehouses=warehouses,
            stocks=stocks,
            production_stocks=production_stocks,
            request=request,
        )
        context = {
            'request': request,
            'selected_center_id': int(center_id or 0),
            **inventory_ctx,
        }
        html = templates.get_template('partials/inventory_lazy_content.html').render(context)
        return HTMLResponse(html)
    except Exception as e:
        return JSONResponse({'ok': False, 'error': str(e)}, status_code=500)
