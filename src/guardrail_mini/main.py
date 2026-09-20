"""FastAPI application entry point."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from guardrail_mini import __version__
from guardrail_mini.api.routes.evaluate import load_model_from_settings
from guardrail_mini.api.routes.evaluate import router as evaluate_router
from guardrail_mini.api.routes.health import router as health_router
from guardrail_mini.core.config import Settings, get_settings
from guardrail_mini.policies.toxicity import ToxicityClassifier


def create_app(
    settings: Settings | None = None,
    model_loader: Callable[[Settings], ToxicityClassifier] | None = None,
) -> FastAPI:
    """Build the API application, allowing settings to be injected in tests."""

    app_settings = settings or get_settings()
    resolve_model = model_loader or load_model_from_settings

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = app_settings
        app.state.ready = False
        app.state.toxicity_classifier = resolve_model(app_settings)
        app.state.ready = True
        yield
        app.state.toxicity_classifier = None
        app.state.ready = False

    application = FastAPI(
        title=app_settings.app_name,
        version=__version__,
        description="A small API for evaluating text against configurable guardrail policies.",
        lifespan=lifespan,
    )
    application.include_router(health_router)
    application.include_router(evaluate_router)
    return application


app = create_app()
