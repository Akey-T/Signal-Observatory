"""FastAPI application factory and lifecycle."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import Engine

from observatory_db.session import (
    create_database_engine,
    database_is_ready,
    wait_for_database,
)
from signal_observatory_api import __version__
from signal_observatory_api.logging import configure_logging
from signal_observatory_api.topics import router as topics_router
from signal_observatory_config import Settings, get_settings

logger = structlog.get_logger("api")


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        configure_logging(runtime_settings.log_level)
        logger.info("api_starting", **runtime_settings.public_summary())
        engine = create_database_engine(runtime_settings.database_url)
        await asyncio.to_thread(
            wait_for_database,
            engine,
            attempts=runtime_settings.database_connect_attempts,
            delay_seconds=runtime_settings.database_connect_delay_seconds,
        )
        application.state.engine = engine
        application.state.ready = True
        logger.info("api_started")
        try:
            yield
        finally:
            application.state.ready = False
            await asyncio.to_thread(engine.dispose)
            logger.info("api_stopped")

    application = FastAPI(
        title="Signal Observatory API",
        version=__version__,
        lifespan=lifespan,
    )
    application.include_router(topics_router)

    @application.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id", str(uuid4()))
        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            response = await call_next(request)
            response.headers["x-request-id"] = request_id
            return response
        finally:
            structlog.contextvars.clear_contextvars()

    @application.exception_handler(Exception)
    async def unhandled_exception(request: Request, error: Exception) -> JSONResponse:
        logger.exception(
            "unhandled_request_error",
            path=request.url.path,
            error_type=type(error).__name__,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "internal server error"},
        )

    @application.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="healthy", service="api", version=__version__)

    @application.get("/ready", response_model=HealthResponse)
    async def readiness(request: Request) -> HealthResponse | JSONResponse:
        engine: Engine | None = getattr(request.app.state, "engine", None)
        ready = getattr(request.app.state, "ready", False)
        if engine is None or not ready or not await asyncio.to_thread(database_is_ready, engine):
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "not_ready", "service": "api", "version": __version__},
            )
        return HealthResponse(status="ready", service="api", version=__version__)

    return application


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("signal_observatory_api.main:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run()
