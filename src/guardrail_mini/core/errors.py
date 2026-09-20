"""Application-level errors that map to the public API error format."""


class GuardrailError(Exception):
    """An expected request or policy error with an HTTP status and stable code."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
