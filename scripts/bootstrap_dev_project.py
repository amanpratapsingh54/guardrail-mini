"""Create or find a local tenant/project before issuing the first API key."""

import argparse

from sqlalchemy import select

from guardrail_mini.core.config import get_settings
from guardrail_mini.db.models import Project, Tenant
from guardrail_mini.db.session import create_database_engine, create_session_factory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-name", default="Local Development")
    parser.add_argument("--project-name", default="Guardrail Demo")
    arguments = parser.parse_args()

    settings = get_settings()
    if settings.database_url is None:
        raise RuntimeError("Set GUARDRAIL_DATABASE_URL in .env first.")
    engine = create_database_engine(settings.database_url)
    factory = create_session_factory(engine)
    try:
        with factory.begin() as session:
            tenant = session.scalar(select(Tenant).where(Tenant.name == arguments.tenant_name))
            if tenant is None:
                tenant = Tenant(name=arguments.tenant_name)
                session.add(tenant)
                session.flush()
            project = session.scalar(
                select(Project).where(
                    Project.tenant_id == tenant.id,
                    Project.name == arguments.project_name,
                )
            )
            if project is None:
                project = Project(tenant_id=tenant.id, name=arguments.project_name)
                session.add(project)
                session.flush()
            tenant_id = tenant.id
            project_id = project.id
    finally:
        engine.dispose()

    print(f"Tenant ID: {tenant_id}")
    print(f"Project ID: {project_id}")


if __name__ == "__main__":
    main()
