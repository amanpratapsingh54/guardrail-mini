"""Bounded, in-process per-project request rate limiting."""

from collections import OrderedDict
from collections.abc import Callable
from math import ceil
from threading import Lock
from time import monotonic
from uuid import UUID

from guardrail_mini.core.errors import GuardrailError


class ProjectRateLimiter:
    """Apply a fixed-window request limit for each authenticated project."""

    def __init__(
        self,
        requests_per_window: int,
        window_seconds: int = 60,
        max_projects: int = 10_000,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if requests_per_window < 1 or window_seconds < 1 or max_projects < 1:
            raise ValueError("Rate limit and cache bounds must be positive.")
        self._requests_per_window = requests_per_window
        self._window_seconds = window_seconds
        self._max_projects = max_projects
        self._clock = clock
        self._windows: OrderedDict[UUID, tuple[float, int]] = OrderedDict()
        self._lock = Lock()

    def check(self, project_id: UUID) -> None:
        """Consume one request slot or raise a structured 429 error."""

        now = self._clock()
        with self._lock:
            window = self._windows.get(project_id)
            if window is None or now - window[0] >= self._window_seconds:
                if window is None and len(self._windows) >= self._max_projects:
                    self._windows.popitem(last=False)
                self._windows[project_id] = (now, 1)
                self._windows.move_to_end(project_id)
                return

            started_at, requests = window
            if requests >= self._requests_per_window:
                retry_after = max(1, ceil(self._window_seconds - (now - started_at)))
                raise GuardrailError(
                    429,
                    "RATE_LIMITED",
                    "The project request limit has been reached. Try again later.",
                    headers={"Retry-After": str(retry_after)},
                )

            self._windows[project_id] = (started_at, requests + 1)
            self._windows.move_to_end(project_id)
