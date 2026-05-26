from fastapi.responses import RedirectResponse


def admin_page_url(center_id: int = 0, ok: str | int | None = None, err: str | int | None = None) -> str:
    parts = ["/?page=admin", f"center_id={int(center_id or 0)}"]
    if ok is not None and str(ok) != "":
        parts.append(f"ok={ok}")
    if err is not None and str(err) != "":
        parts.append(f"err={err}")
    return "&".join(parts)


def redirect_admin(center_id: int = 0, ok: str | int | None = None, err: str | int | None = None, status_code: int = 303):
    return RedirectResponse(url=admin_page_url(center_id=center_id, ok=ok, err=err), status_code=status_code)


def normalize_center_name(name: str) -> str:
    return (name or "").strip()
