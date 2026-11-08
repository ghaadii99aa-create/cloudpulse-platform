"""Serves the built dashboard from the API process, for single-service hosting. Disabled unless WEB_DIST is set."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

_PAGE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; "
                               "connect-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'",
}
_RESERVED = ("api/", "metrics", "healthz", "readyz")


class _ImmutableAssets(StaticFiles):
    """Vite fingerprints these file names, so a browser can keep them indefinitely."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def install_webapp(app: FastAPI, dist: str) -> None:
    root = Path(dist).resolve()
    index = root / "index.html"
    if not index.is_file():
        raise RuntimeError(f"WEB_DIST has no index.html: {root}")
    app.mount("/assets", _ImmutableAssets(directory=root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith(_RESERVED):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
        candidate = (root / path).resolve()
        target = candidate if path and candidate.is_file() and candidate.is_relative_to(root) else index
        return FileResponse(target, headers=_PAGE_HEADERS)
