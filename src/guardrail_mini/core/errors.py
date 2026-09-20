"""Application-level errors that map to the public API error format."""

from collections.abc import Mapping


class GuardrailError(Exception):
    """An expected request or policy error with an HTTP status and stable code."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = dict(headers or {})
