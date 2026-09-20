"""FastAPI bearer-key dependency and project context."""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from guardrail_mini.auth.keys import ApiKeyAuthenticator, ApiKeyPrincipal
from guardrail_mini.core.errors import GuardrailError

bearer_scheme = HTTPBearer(auto_error=False)


def get_authenticated_project(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> ApiKeyPrincipal:
    """Authenticate a bearer key and return its tenant-scoped project context."""

    authenticator: ApiKeyAuthenticator | None = getattr(
        request.app.state, "api_key_authenticator", None
    )
    if authenticator is None:
        raise GuardrailError(503, "MODEL_NOT_READY", "The API is not ready for requests.")
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise GuardrailError(
            401,
            "AUTHENTICATION_FAILED",
            "A valid Bearer API key is required.",
        )
    principal = authenticator.authenticate(credentials.credentials)
    request.state.tenant_id = principal.tenant_id
    request.state.project_id = principal.project_id
    return principal
