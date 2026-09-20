"""Startup must fail closed when control-plane schema is unavailable."""

from pathlib import Path

import pytest

from guardrail_mini.core.config import Settings
from guardrail_mini.main import create_app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_startup_does_not_report_ready_without_database_schema(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'missing-schema.db'}",
    )  # type: ignore[call-arg]
    app = create_app(settings)

    with pytest.raises(RuntimeError, match="database is unavailable"):
        async with app.router.lifespan_context(app):
            pytest.fail("Startup unexpectedly succeeded without the control-plane schema.")

    assert app.state.ready is False
