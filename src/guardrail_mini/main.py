"""FastAPI application entry point."""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from re import fullmatch
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from guardrail_mini import __version__
from guardrail_mini.api.middleware import RequestBodyLimitMiddleware
from guardrail_mini.api.routes.api_keys import router as api_keys_router
from guardrail_mini.api.routes.demo import router as demo_router
from guardrail_mini.api.routes.evaluate import load_model_from_settings
from guardrail_mini.api.routes.evaluate import router as evaluate_router
from guardrail_mini.api.routes.health import router as health_router
from guardrail_mini.api.routes.policies import router as policies_router
from guardrail_mini.auth.keys import ApiKeyAuthenticator
from guardrail_mini.auth.rate_limit import ProjectRateLimiter
from guardrail_mini.core.config import Settings, get_settings
from guardrail_mini.core.errors import GuardrailError
from guardrail_mini.core.policy_engine import PolicyRegistry
from guardrail_mini.db.models import ApiKey
from guardrail_mini.db.session import create_database_engine, create_session_factory
from guardrail_mini.models.registry import resolve_model_directories
from guardrail_mini.observability.logging import configure_logging, request_id_context
from guardrail_mini.observability.metrics import (
    ERRORS_TOTAL,
    REQUEST_DURATION_SECONDS,
    REQUESTS_TOTAL,
)
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
    app_logger = configure_logging(app_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = app_settings
        app.state.ready = False
        if app_settings.database_url is None:
            raise RuntimeError("GUARDRAIL_DATABASE_URL is required to start the authenticated API.")
        engine = create_database_engine(app_settings.database_url)
        try:
            factory = create_session_factory(engine)
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                connection.execute(select(ApiKey.id).limit(1))
            app.state.database_engine = engine
            app.state.database_session_factory = factory
            app.state.api_key_authenticator = ApiKeyAuthenticator(
                factory,
                cache_ttl_seconds=app_settings.api_key_cache_ttl_seconds,
            )
            model_directories = resolve_model_directories(app_settings, factory)
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
                runtime=model_settings.model_runtime,
                onnx_cache_dir=model_settings.onnx_cache_dir,
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
        except SQLAlchemyError as error:
            raise RuntimeError(
                "The control-plane database is unavailable or its migrations are missing."
            ) from error
        finally:
            app.state.policy_registry = None
            app.state.api_key_authenticator = None
            app.state.database_session_factory = None
            app.state.database_engine = None
            app.state.ready = False
            engine.dispose()

    application = FastAPI(
        title=app_settings.app_name,
        version=__version__,
        description="A small API for evaluating text against configurable guardrail policies.",
        lifespan=lifespan,
    )
    application.add_middleware(
        RequestBodyLimitMiddleware,
        max_bytes=app_settings.max_request_body_bytes,
    )
    application.state.rate_limiter = ProjectRateLimiter(
        app_settings.rate_limit_requests_per_minute,
    )
    application.state.demo_rate_limiter = ProjectRateLimiter(
        app_settings.demo_rate_limit_requests_per_minute,
        max_projects=4096,
    )

    @application.middleware("http")
    async def add_request_observability(
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        supplied_request_id = request.headers.get("X-Request-ID", "")
        request_id = (
            supplied_request_id
            if fullmatch(r"[A-Za-z0-9._-]{1,64}", supplied_request_id)
            else f"req_{uuid4().hex}"
        )
        request.state.request_id = request_id
        request.scope.setdefault("state", {})["request_id"] = request_id
        request_token = request_id_context.set(request_id)
        started = perf_counter()
        status_code = 500
        try:
            try:
                response = await call_next(request)
                status_code = response.status_code
            except Exception as error:
                ERRORS_TOTAL.labels(error_code="INTERNAL_ERROR").inc()
                app_logger.error(
                    "internal_error",
                    extra={
                        "event": "internal_error",
                        "request_id": request_id,
                        "error_code": "INTERNAL_ERROR",
                        "exception_type": type(error).__name__,
                    },
                )
                response = JSONResponse(
                    status_code=500,
                    content={
                        "error": {
                            "code": "INTERNAL_ERROR",
                            "message": "An internal error occurred.",
                            "request_id": request_id,
                        }
                    },
                )
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            route = request.scope.get("route")
            route_path = getattr(route, "path", "unmatched")
            latency_seconds = perf_counter() - started
            REQUESTS_TOTAL.labels(
                method=request.method,
                route=route_path,
                status_code=str(status_code),
            ).inc()
            REQUEST_DURATION_SECONDS.labels(method=request.method, route=route_path).observe(
                latency_seconds
            )
            app_logger.log(
                logging.WARNING if status_code >= 400 else logging.INFO,
                "http_request_completed",
                extra={
                    "event": "http_request_completed",
                    "request_id": request_id,
                    "tenant_id": getattr(request.state, "tenant_id", None),
                    "project_id": getattr(request.state, "project_id", None),
                    "method": request.method,
                    "path": route_path,
                    "status_code": status_code,
                    "latency_ms": round(latency_seconds * 1000, 3),
                },
            )
            request_id_context.reset(request_token)

    @application.exception_handler(GuardrailError)
    async def guardrail_error_handler(
        request: Request,
        error: GuardrailError,
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", f"req_{uuid4().hex}")
        ERRORS_TOTAL.labels(error_code=error.code).inc()
        app_logger.warning(
            "guardrail_error",
            extra={"event": "guardrail_error", "request_id": request_id, "error_code": error.code},
        )
        return JSONResponse(
            status_code=error.status_code,
            content={
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "request_id": request_id,
                }
            },
            headers=error.headers,
        )

    @application.exception_handler(RequestValidationError)
    async def request_validation_error_handler(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        del error
        request_id = getattr(request.state, "request_id", f"req_{uuid4().hex}")
        ERRORS_TOTAL.labels(error_code="INVALID_REQUEST").inc()
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "Request validation failed.",
                    "request_id": request_id,
                }
            },
        )

    @application.exception_handler(HTTPException)
    async def http_error_handler(request: Request, error: HTTPException) -> JSONResponse:
        request_id = getattr(request.state, "request_id", f"req_{uuid4().hex}")
        code = "MODEL_NOT_READY" if error.status_code == 503 else "HTTP_ERROR"
        ERRORS_TOTAL.labels(error_code=code).inc()
        message = (
            "The application is not ready." if code == "MODEL_NOT_READY" else "HTTP request failed."
        )
        return JSONResponse(
            status_code=error.status_code,
            content={"error": {"code": code, "message": message, "request_id": request_id}},
            headers=error.headers,
        )

    application.include_router(health_router)
    application.include_router(demo_router)
    application.include_router(evaluate_router)
    application.include_router(policies_router)
    application.include_router(api_keys_router)
    return application


app = create_app()
