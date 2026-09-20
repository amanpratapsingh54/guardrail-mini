"""FastAPI application entry point."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from guardrail_mini import __version__
from guardrail_mini.api.routes.evaluate import load_model_from_settings
from guardrail_mini.api.routes.evaluate import router as evaluate_router
from guardrail_mini.api.routes.health import router as health_router
from guardrail_mini.api.routes.policies import router as policies_router
from guardrail_mini.core.config import Settings, get_settings
from guardrail_mini.core.errors import GuardrailError
from guardrail_mini.core.policy_engine import PolicyRegistry
from guardrail_mini.models.registry import resolve_model_directories
from guardrail_mini.policies.pii import PiiPolicy, load_pii_detector
from guardrail_mini.policies.prompt_injection import (
    PromptInjectionPolicy,
    load_prompt_injection_classifier,
)
from guardrail_mini.policies.toxicity import ToxicityClassifier, ToxicityPolicy


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
        model_directories = resolve_model_directories(app_settings)
        model_settings = app_settings.model_copy(
            update={
                "toxicity_model_dir": model_directories["toxicity"],
                "prompt_injection_model_dir": model_directories["prompt_injection"],
            }
        )
        classifier = resolve_model(model_settings)
        pii_detector = load_pii_detector()
        prompt_injection_classifier = load_prompt_injection_classifier(
            model_settings.prompt_injection_model_dir,
            model_settings.model_device,
        )
        app.state.policy_registry = PolicyRegistry(
            [
                ToxicityPolicy(
                    classifier,
                    threshold=app_settings.toxicity_threshold,
                    review_threshold=app_settings.toxicity_review_threshold,
                ),
                PiiPolicy(
                    pii_detector,
                    threshold=app_settings.pii_threshold,
                    review_threshold=app_settings.pii_review_threshold,
                ),
                PromptInjectionPolicy(
                    prompt_injection_classifier,
                    threshold=app_settings.prompt_injection_threshold,
                    review_threshold=app_settings.prompt_injection_review_threshold,
                ),
            ]
        )
        app.state.ready = True
        yield
        app.state.policy_registry = None
        app.state.ready = False

    application = FastAPI(
        title=app_settings.app_name,
        version=__version__,
        description="A small API for evaluating text against configurable guardrail policies.",
        lifespan=lifespan,
    )

    @application.exception_handler(GuardrailError)
    async def guardrail_error_handler(
        request: Request,
        error: GuardrailError,
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", f"req_{uuid4().hex}")
        return JSONResponse(
            status_code=error.status_code,
            content={
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "request_id": request_id,
                }
            },
        )

    application.include_router(health_router)
    application.include_router(evaluate_router)
    application.include_router(policies_router)
    return application


app = create_app()
