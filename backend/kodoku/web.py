"""Serve the prebuilt Next.js static export from FastAPI (packaged single-port mode).

In dev (no build present) this is a no-op and the app is API-only; run `next dev`
separately. When packaged, the build is bundled at `kodoku/_web`.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def web_dir() -> Path | None:
    bundled = Path(__file__).parent / "_web"
    if bundled.is_dir():
        return bundled
    dev = Path(__file__).parents[2] / "frontend" / "out"
    if dev.is_dir():
        return dev
    return None


def mount_web(app: FastAPI) -> bool:
    root = web_dir()
    if root is None:
        return False

    shell = root / "s" / "_" / "index.html"

    @app.get("/s/{session_id}", include_in_schema=False)
    async def session_shell(session_id: str) -> FileResponse:
        return FileResponse(shell)

    # html=True serves index.html for "/" and directory paths (e.g. /settings).
    app.mount("/", StaticFiles(directory=root, html=True), name="web")
    return True
