#!/usr/bin/env python3
"""Vercel wrapper: lazily import the real FastAPI app.

This avoids import-time crashes surfacing as opaque 500s. On import
failure we return the traceback in the HTTP response body to aid
debugging during deployment.
"""
import sys
import asyncio
import traceback
from pathlib import Path

# Resolve backend on sys.path but don't import app.main here — do it lazily
repo_root = Path(__file__).resolve().parent.parent
BACKEND_PATH = str(repo_root / "backend")

_real_app = None
_import_error_text = None
_import_lock = asyncio.Lock()


async def _ensure_real_app():
	global _real_app, _import_error_text
	if _real_app or _import_error_text:
		return
	async with _import_lock:
		if _real_app or _import_error_text:
			return
		try:
			sys.path.insert(0, BACKEND_PATH)
			import importlib
			m = importlib.import_module("app.main")
			_real_app = getattr(m, "app", None)
			if _real_app is None:
				_import_error_text = "app not found in app.main"
		except Exception:
			_import_error_text = traceback.format_exc()


async def app(scope, receive, send):
	"""ASGI entrypoint used by Vercel.

	On first request this imports `app.main`. If the import fails the
	traceback is returned in the response body which helps debugging on
	remote environments where build logs are unavailable.
	"""
	# Only handle HTTP requests here; forward other scope types to the real app if available
	if scope.get("type") != "http":
		await _ensure_real_app()
		if _real_app:
			await _real_app(scope, receive, send)
			return
		# For non-http scopes return a minimal lifespan response when import failed
		await send({"type": "http.response.start", "status": 500, "headers": [[b"content-type", b"text/plain; charset=utf-8"]]})
		body = (_import_error_text or "Application import failed").encode("utf-8")
		await send({"type": "http.response.body", "body": body})
		return

	await _ensure_real_app()
	if _real_app:
		await _real_app(scope, receive, send)
		return

	# Import failed — return traceback to the client for debugging
	text = _import_error_text or "Application import failed"
	body = text.encode("utf-8")
	headers = [[b"content-type", b"text/plain; charset=utf-8"]]
	await send({"type": "http.response.start", "status": 500, "headers": headers})
	await send({"type": "http.response.body", "body": body})


__all__ = ["app"]
