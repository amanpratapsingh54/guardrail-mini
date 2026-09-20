"""Run the development API using the configured host and port."""

import uvicorn

from guardrail_mini.core.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "guardrail_mini.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=settings.environment == "development",
    )


if __name__ == "__main__":
    main()
