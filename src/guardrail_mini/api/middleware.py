"""HTTP middleware for request body limits."""

from re import fullmatch
from uuid import uuid4

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from guardrail_mini.observability.metrics import ERRORS_TOTAL


class RequestBodyLimitMiddleware:
    """Buffer only bounded HTTP request bodies before routing them to FastAPI."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = self._request_id(scope)
        content_length = self._content_length(scope)
        if content_length is not None and content_length > self.max_bytes:
            await self._reject(scope, receive, send, request_id)
            return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.max_bytes:
                await self._reject(scope, receive, send, request_id)
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break

        body_message: Message = {"type": "http.request", "body": bytes(body), "more_body": False}
        body_replayed = False

        async def replay_body() -> Message:
            nonlocal body_replayed
            if not body_replayed:
                body_replayed = True
                return body_message
            return await receive()

        await self.app(scope, replay_body, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send, request_id: str) -> None:
        ERRORS_TOTAL.labels(error_code="INVALID_REQUEST").inc()
        response = JSONResponse(
            status_code=413,
            headers={"X-Request-ID": request_id},
            content={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "Request body exceeds the configured size limit.",
                    "request_id": request_id,
                }
            },
        )
        await response(scope, receive, send)

    @staticmethod
    def _request_id(scope: Scope) -> str:
        state = scope.get("state", {})
        state_request_id = state.get("request_id") if isinstance(state, dict) else None
        if isinstance(state_request_id, str):
            return state_request_id
        supplied_id = next(
            (
                value.decode("latin-1")
                for key, value in scope.get("headers", [])
                if key.lower() == b"x-request-id"
            ),
            "",
        )
        if fullmatch(r"[A-Za-z0-9._-]{1,64}", supplied_id):
            return supplied_id
        return f"req_{uuid4().hex}"

    @staticmethod
    def _content_length(scope: Scope) -> int | None:
        raw_length = next(
            (value for key, value in scope.get("headers", []) if key.lower() == b"content-length"),
            None,
        )
        if raw_length is None:
            return None
        try:
            return int(raw_length)
        except ValueError:
            return None
