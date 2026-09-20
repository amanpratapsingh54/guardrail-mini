# API-Key Authentication

The API uses high-entropy bearer credentials scoped to a project. The project belongs to a tenant. Request context is resolved from the key record and returned with each successful evaluation as `tenant_id` and `project_id`.

## Create the first project key

The first credential must be created from a trusted shell because no API credential exists yet. Configure PostgreSQL in `.env` and apply migrations first (see [DATABASE.md](DATABASE.md)). From the repository root:

```bash
python scripts/bootstrap_dev_project.py
python scripts/create_api_key.py --project-id <PROJECT_ID_FROM_OUTPUT> --name local-development
```

`bootstrap_dev_project.py` creates or finds the named tenant and project and prints their UUIDs. `create_api_key.py` prints a new 256-bit random bearer key once; store it in a password manager or a local environment variable. The command never writes the raw token to PostgreSQL or a file.

For the current shell, set the returned token without adding it to Git:

```bash
export GUARDRAIL_API_KEY='<paste-the-key-once>'
```

In PowerShell:

```powershell
$env:GUARDRAIL_API_KEY = '<paste-the-key-once>'
```

## Call the API

```bash
curl -X POST http://127.0.0.1:8000/v1/guardrails/evaluate \
  -H "Authorization: Bearer $GUARDRAIL_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"input":"Please summarize this public document.","policies":["toxicity","pii","prompt_injection"]}'
```

A successful response includes the resolved tenant and project IDs. Calls without a valid key return HTTP 401 and `AUTHENTICATION_FAILED`; expired or revoked keys receive the same response.

## Create and revoke keys through the API

An existing key can create another key for its own project:

```bash
curl -X POST http://127.0.0.1:8000/v1/api-keys \
  -H "Authorization: Bearer $GUARDRAIL_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"name":"staging client","expires_in_days":90}'
```

The `201` response includes the raw `api_key` once, its ID, a short prefix, and expiry. Store the raw key securely; it cannot be retrieved later. Omit `expires_in_days` for a non-expiring key. Values must be between 1 and 3,650 days when provided.

Revoke an API key belonging to the current project:

```bash
curl -X DELETE "http://127.0.0.1:8000/v1/api-keys/<KEY_ID>" \
  -H "Authorization: Bearer $GUARDRAIL_API_KEY"
```

The response reports `status: revoked`. Trying to revoke a key owned by another project returns `API_KEY_NOT_FOUND`, so the endpoint does not confirm cross-project key IDs.

## Storage and caching

- API keys have a `gr_live_` prefix and 256 bits of URL-safe random material.
- PostgreSQL stores `SHA-256(raw_key)`, a short non-secret prefix, project ID, name, active/revoked state, expiry, creation time, and last-used time. The raw token is only returned by a creation response or the trusted bootstrap CLI.
- Authentication looks up a key hash and project scope in PostgreSQL on a cache miss. Valid contexts are cached in process for 30 seconds by default (`GUARDRAIL_API_KEY_CACHE_TTL_SECONDS`, range 1–300); invalid lookups are cached for at most 5 seconds.
- A revoke removes the cached key immediately in the worker handling the request. Other workers may accept a previously cached key until its cache entry expires. Lower the TTL when faster cross-worker revocation matters.
- The cache is bounded to 10,000 entries. Redis is not used.
- Every inference request uses the authenticated project context. Key creation and revocation queries include that project ID.
- HTTPS is required outside local development. Do not put keys in source control, URLs, or application logs.
