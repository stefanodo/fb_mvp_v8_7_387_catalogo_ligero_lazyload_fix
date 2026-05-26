from urllib.parse import urlencode


def form_int(form, name: str, default: int = 0) -> int:
    try:
        return int(str(form.get(name, default) or default).strip())
    except Exception:
        return default


def parse_receipt_base_form(form) -> dict:
    return {
        "center_id": form_int(form, "center_id", 0),
        "warehouse_id": form_int(form, "warehouse_id", 0),
        "supplier_id": form_int(form, "supplier_id", 0),
        "doc_number": (form.get("doc_number") or "").strip(),
        "doc_date": (form.get("doc_date") or "").strip(),
        "note": (form.get("note") or "").strip(),
        "new_supplier_name": (form.get("new_supplier_name") or "").strip(),
        "new_supplier_phone": (form.get("new_supplier_phone") or "").strip(),
        "new_supplier_email": (form.get("new_supplier_email") or "").strip(),
        "new_supplier_tax_id": (form.get("new_supplier_tax_id") or "").strip(),
        "new_supplier_address": (form.get("new_supplier_address") or "").strip(),
    }


def receipt_page_url(center_id: int | None = None, aid: int | None = None, anchor: str | None = None, **params) -> str:
    query = {"page": "albaranes"}
    if center_id:
        query["center_id"] = int(center_id)
    if aid:
        query["aid"] = int(aid)
    for key, value in params.items():
        if value is None or value == "":
            continue
        query[key] = value
    url = f"/?{urlencode(query)}"
    if anchor:
        url += f"#{anchor}"
    return url
