"""Secure API-key issuance, hashing, lookup, and short-lived authentication cache."""

import hashlib
import secrets
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import RLock
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from guardrail_mini.core.errors import GuardrailError
from guardrail_mini.db.models import ApiKey, Project


@dataclass(frozen=True)
class ApiKeyPrincipal:
    """Authenticated key and the project/tenant scope resolved from PostgreSQL."""

    key_id: UUID
    project_id: UUID
    tenant_id: UUID
    expires_at: datetime | None


@dataclass(frozen=True)
class _CacheEntry:
    principal: ApiKeyPrincipal | None
    expires_monotonic: float


def hash_api_key(raw_key: str) -> str:
    """Hash a high-entropy generated API key before any persistent storage."""

    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def issue_api_key(
    session: Session,
    project_id: UUID,
    name: str,
    expires_in_days: int | None = None,
) -> tuple[ApiKey, str]:
    """Add a generated key record and return its plaintext exactly once to the caller."""

    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("API key name must not be empty.")
    if expires_in_days is not None and not 1 <= expires_in_days <= 3650:
        raise ValueError("API key expiration must be between 1 and 3,650 days.")

    raw_key = f"gr_live_{secrets.token_urlsafe(32)}"
    key_hash = hash_api_key(raw_key)
    expires_at = (
        datetime.now(UTC) + timedelta(days=expires_in_days) if expires_in_days is not None else None
    )
    record = ApiKey(
        project_id=project_id,
        name=normalized_name,
        key_prefix=raw_key[:16],
        key_hash=key_hash,
        is_active=True,
        expires_at=expires_at,
    )
    session.add(record)
    return record, raw_key


class ApiKeyAuthenticator:
    """Validate bearer tokens against PostgreSQL and cache project context in process."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        cache_ttl_seconds: int = 30,
        max_entries: int = 10_000,
    ) -> None:
        self._session_factory = session_factory
        self._cache_ttl_seconds = cache_ttl_seconds
        self._negative_ttl_seconds = min(5, cache_ttl_seconds)
        self._max_entries = max_entries
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = RLock()

    def authenticate(self, raw_key: str) -> ApiKeyPrincipal:
        """Resolve a raw bearer token to an active, unexpired project principal."""

        if not raw_key:
            raise _authentication_error()
        key_hash = hash_api_key(raw_key)
        now_monotonic = time.monotonic()
        with self._lock:
            entry = self._cache.get(key_hash)
            if entry is not None and entry.expires_monotonic > now_monotonic:
                self._cache.move_to_end(key_hash)
                if entry.principal is None:
                    raise _authentication_error()
                if _is_expired(entry.principal.expires_at):
                    self._cache[key_hash] = _CacheEntry(
                        None, now_monotonic + self._negative_ttl_seconds
                    )
                    raise _authentication_error()
                return entry.principal
            self._cache.pop(key_hash, None)

        try:
            with self._session_factory() as session:
                row = session.execute(
                    select(ApiKey, Project.tenant_id)
                    .join(Project, ApiKey.project_id == Project.id)
                    .where(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
                ).one_or_none()
                if row is None:
                    self._remember(key_hash, None)
                    raise _authentication_error()
                record, tenant_id = row
                expires_at = _as_utc(record.expires_at)
                if _is_expired(expires_at):
                    self._remember(key_hash, None)
                    raise _authentication_error()
                record.last_used_at = datetime.now(UTC)
                session.commit()
                principal = ApiKeyPrincipal(
                    key_id=record.id,
                    project_id=record.project_id,
                    tenant_id=tenant_id,
                    expires_at=expires_at,
                )
        except GuardrailError:
            raise
        except SQLAlchemyError as error:
            raise GuardrailError(
                503,
                "DATABASE_UNAVAILABLE",
                "The authentication store is temporarily unavailable.",
            ) from error

        self._remember(key_hash, principal)
        return principal

    def invalidate(self, key_hash: str) -> None:
        """Immediately remove a key from this process after a revoke operation."""

        with self._lock:
            self._cache.pop(key_hash, None)

    def _remember(self, key_hash: str, principal: ApiKeyPrincipal | None) -> None:
        ttl = self._cache_ttl_seconds if principal is not None else self._negative_ttl_seconds
        entry = _CacheEntry(principal, time.monotonic() + ttl)
        with self._lock:
            self._cache[key_hash] = entry
            self._cache.move_to_end(key_hash)
            self._prune_expired(time.monotonic())
            while len(self._cache) > self._max_entries:
                self._cache.popitem(last=False)

    def _prune_expired(self, now_monotonic: float) -> None:
        expired = [
            key_hash
            for key_hash, entry in self._cache.items()
            if entry.expires_monotonic <= now_monotonic
        ]
        for key_hash in expired:
            self._cache.pop(key_hash, None)


def _authentication_error() -> GuardrailError:
    return GuardrailError(
        401,
        "AUTHENTICATION_FAILED",
        "A valid Bearer API key is required.",
    )


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _is_expired(expires_at: datetime | None) -> bool:
    return expires_at is not None and expires_at <= datetime.now(UTC)
