"""FastAPI application factory."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from kodoku import __version__
from kodoku.api.events import router as events_router
from kodoku.api.health import router as health_router
from kodoku.api.run import router as run_router
from kodoku.api.sessions import router as sessions_router
from kodoku.settings import Settings, get_settings
from kodoku.ws.router import router as ws_router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    app = FastAPI(
        title="Kodoku",
        version=__version__,
        description="Decision Graph AI — Tree of Thoughts planner",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(sessions_router)
    app.include_router(events_router)
    app.include_router(run_router)
    app.include_router(ws_router)

    return app


app = create_app()
