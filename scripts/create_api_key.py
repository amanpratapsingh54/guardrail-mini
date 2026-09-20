"""Issue an initial project API key from a trusted local shell."""

import argparse
from uuid import UUID

from guardrail_mini.auth.keys import issue_api_key
from guardrail_mini.core.config import get_settings
from guardrail_mini.db.models import Project
from guardrail_mini.db.session import create_database_engine, create_session_factory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True, type=UUID)
    parser.add_argument("--name", required=True)
    parser.add_argument("--expires-in-days", type=int)
    arguments = parser.parse_args()

    settings = get_settings()
    if settings.database_url is None:
        raise RuntimeError("Set GUARDRAIL_DATABASE_URL in .env first.")
    engine = create_database_engine(settings.database_url)
    factory = create_session_factory(engine)
    try:
        with factory.begin() as session:
            project = session.get(Project, arguments.project_id)
            if project is None:
                raise ValueError(f"Project {arguments.project_id} does not exist.")
            record, raw_key = issue_api_key(
                session,
                project_id=project.id,
                name=arguments.name,
                expires_in_days=arguments.expires_in_days,
            )
            session.flush()
            key_id = record.id
            key_prefix = record.key_prefix
            expires_at = record.expires_at
    finally:
        engine.dispose()

    print(f"API key ID: {key_id}")
    print(f"Key prefix: {key_prefix}")
    print(f"Expires at: {expires_at or 'never'}")
    print("Copy this key now. It is shown only once:")
    print(raw_key)


if __name__ == "__main__":
    main()
