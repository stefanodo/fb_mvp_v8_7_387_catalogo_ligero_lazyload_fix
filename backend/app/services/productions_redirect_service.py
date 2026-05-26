from urllib.parse import urlencode


def production_redirect_url(*, center_id=None, production_id=None, ok=None, err=None, anchor="productionDetailPanel", extra=None):
    params = {"page": "producciones"}
    if center_id is not None:
        params["center_id"] = center_id
    if production_id is not None:
        params["pid"] = production_id
    if ok is not None:
        params["ok"] = ok
    if err is not None:
        params["err"] = err
    if extra:
        params.update(extra)
    base = f"/?{urlencode(params)}"
    if anchor:
        return f"{base}#{anchor}"
    return base
