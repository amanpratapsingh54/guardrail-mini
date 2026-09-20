# PostgreSQL Development Database

Phase 5 uses PostgreSQL for control-plane records. SQLAlchemy defines the tables and Alembic applies versioned migrations. Models and inference configuration stay in the API process after startup; the normal request path does not query PostgreSQL for policy settings.

## Option A: PostgreSQL with Docker

Prerequisite: Docker Desktop (macOS/Windows) or Docker Engine (Linux) must be running. Execute from a terminal; commands are otherwise identical on macOS, Windows PowerShell, and Linux.

```bash
docker run -d --name guardrail-postgres \
  -e POSTGRES_USER=guardrail \
  -e POSTGRES_PASSWORD=guardrail_dev_only \
  -e POSTGRES_DB=guardrail \
  -p 5432:5432 \
  -v guardrail-postgres-data:/var/lib/postgresql/data \
  --health-cmd='pg_isready -U guardrail -d guardrail' \
  --health-interval=5s --health-timeout=3s --health-retries=10 \
  postgres:16
```

This starts the official PostgreSQL 16 image, creates the `guardrail` database and local development role, publishes port 5432, and keeps data in a named Docker volume. The first start downloads the image. `docker ps` should show `guardrail-postgres` as `healthy` after initialization; inspect startup with `docker logs guardrail-postgres`.

Copy `.env.example` to `.env` in the repository root and add this local-only connection string:

```dotenv
GUARDRAIL_DATABASE_URL=postgresql+psycopg://guardrail:guardrail_dev_only@localhost:5432/guardrail
```

The credentials above are for local development only. Use a managed secret or deployment environment variable for any shared or public service.

## Option B: native PostgreSQL on macOS

Install Homebrew if needed, then run these commands in Terminal:

```bash
brew install postgresql@16
brew services start postgresql@16
createuser --createdb guardrail_user
psql postgres -c "ALTER ROLE guardrail_user WITH LOGIN PASSWORD 'local_dev_only';"
createdb --owner=guardrail_user guardrail
```

`brew services list` should show PostgreSQL started. Configure `.env` with:

```dotenv
GUARDRAIL_DATABASE_URL=postgresql+psycopg://guardrail_user:local_dev_only@localhost:5432/guardrail
```

For Windows and Linux, the Docker option above is the documented baseline. A native PostgreSQL installation can use the same database URL pattern with the locally created username, password, host, port, and database name.

## Apply and inspect migrations

Run from the repository root with the project's virtual environment active:

```bash
alembic upgrade head
alembic current
```

Expected output includes revision `0001_control_plane (head)`. If PostgreSQL is in Docker, inspect tables and columns with:

```bash
docker exec -it guardrail-postgres psql -U guardrail -d guardrail -c '\dt'
docker exec -it guardrail-postgres psql -U guardrail -d guardrail -c '\d api_keys'
```

The tables are `tenants`, `projects`, `api_keys`, `policy_metadata`, `policy_configurations`, and `model_versions`. The Alembic version table records which revision was applied. `api_keys` stores a key prefix and one-way hash; it has no plaintext secret column.

## Reset a development database

This deletes all local PostgreSQL data. For the Docker option, run these commands from any terminal:

```bash
docker stop guardrail-postgres
docker rm guardrail-postgres
docker volume rm guardrail-postgres-data
```

Then repeat the `docker run` command above and `alembic upgrade head`. For a native development database, remove and recreate only the project database with `dropdb guardrail` followed by the `createdb` command. Do not run reset commands against a shared or production database.

## Migration behavior

- Set `GUARDRAIL_DATABASE_URL` in `.env` or the shell environment before running Alembic.
- `alembic upgrade head` applies all revisions; `alembic downgrade -1` reverses one revision.
- The automated migration test uses a temporary SQLite file to check upgrade, schema records, and downgrade without requiring a database service.
- PostgreSQL uses the same SQLAlchemy UUID and JSON abstractions; Psycopg 3 is the PostgreSQL driver.
- The schema introduces project policy overrides now. Authentication and per-request project resolution are added in Phase 7.
