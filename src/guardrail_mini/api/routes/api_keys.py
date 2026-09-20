"""Project-scoped API-key creation and revocation endpoints."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from guardrail_mini.api.auth import get_authenticated_project
from guardrail_mini.auth.keys import ApiKeyAuthenticator, ApiKeyPrincipal, issue_api_key
from guardrail_mini.core.errors import GuardrailError
from guardrail_mini.db.models import ApiKey

router = APIRouter(prefix="/v1/api-keys", tags=["api-keys"])


class CreateApiKeyRequest(BaseModel):
    """Metadata and optional lifetime for a new key within the current project."""

    name: str = Field(min_length=1, max_length=200)
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("The API key name must contain a visible character.")
        return value


class CreateApiKeyResponse(BaseModel):
    """The generated key is returned only in this one creation response."""

    id: UUID
    name: str
    key_prefix: str
    api_key: str
    created_at: datetime
    expires_at: datetime | None


class RevokeApiKeyResponse(BaseModel):
    id: UUID
    status: str


def _session_factory(request: Request) -> sessionmaker[Session]:
    factory: sessionmaker[Session] | None = getattr(
        request.app.state, "database_session_factory", None
    )
    if factory is None:
        raise GuardrailError(
            503, "DATABASE_UNAVAILABLE", "The authentication store is unavailable."
        )
    return factory


@router.post("", response_model=CreateApiKeyResponse, status_code=status.HTTP_201_CREATED)
def create_api_key(
    body: CreateApiKeyRequest,
    request: Request,
    principal: Annotated[ApiKeyPrincipal, Depends(get_authenticated_project)],
) -> CreateApiKeyResponse:
    """Create a project-scoped key; plaintext is included only in this response."""

    with _session_factory(request).begin() as session:
        record, raw_key = issue_api_key(
            session,
            project_id=principal.project_id,
            name=body.name,
            expires_in_days=body.expires_in_days,
        )
        session.flush()
        response = CreateApiKeyResponse(
            id=record.id,
            name=record.name,
            key_prefix=record.key_prefix,
            api_key=raw_key,
            created_at=record.created_at,
            expires_at=record.expires_at,
        )
    return response


@router.delete("/{key_id}", response_model=RevokeApiKeyResponse)
def revoke_api_key(
    key_id: UUID,
    request: Request,
    principal: Annotated[ApiKeyPrincipal, Depends(get_authenticated_project)],
) -> RevokeApiKeyResponse:
    """Revoke a key that belongs to the authenticated project."""

    with _session_factory(request).begin() as session:
        record = session.scalar(
            select(ApiKey).where(
                ApiKey.id == key_id,
                ApiKey.project_id == principal.project_id,
            )
        )
        if record is None:
            raise GuardrailError(
                404,
                "API_KEY_NOT_FOUND",
                "The API key does not exist in this project.",
            )
        record.is_active = False
        key_hash = record.key_hash

    authenticator: ApiKeyAuthenticator | None = getattr(
        request.app.state, "api_key_authenticator", None
    )
    if authenticator is not None:
        authenticator.invalidate(key_hash)
    return RevokeApiKeyResponse(id=key_id, status="revoked")
