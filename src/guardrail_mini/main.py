"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from guardrail_mini import __version__
from guardrail_mini.api.routes.health import router as health_router
from guardrail_mini.core.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API application, allowing settings to be injected in tests."""

    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Model loading and warm-up will run here in a later phase.
        app.state.ready = True
        yield
        app.state.ready = False

    application = FastAPI(
        title=app_settings.app_name,
        version=__version__,
        description="A small API for evaluating text against configurable guardrail policies.",
        lifespan=lifespan,
    )
    application.include_router(health_router)
    return application


app = create_app()
