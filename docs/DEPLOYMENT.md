# Cloud deployment

## Platform and operating shape

The deployment target is Google Cloud Run with Neon PostgreSQL. Cloud Run runs the existing Docker image, provides a managed HTTPS endpoint, and charges request-based services while instances start or handle work; it also has a monthly free allowance. The service is capped at one instance and scales to zero. Cloud Build and Artifact Registry are billed separately, so set a billing budget alert before the first build. See [Cloud Run pricing](https://cloud.google.com/run/pricing), [Cloud Run memory limits](https://cloud.google.com/run/docs/configuring/services/memory-limits), and [Cloud Run secrets](https://cloud.google.com/run/docs/configuring/services/secrets).

**Deployment status:** the Docker build and service configuration are verified locally. A public service has not been provisioned because this workspace has no authenticated Google Cloud project or Neon database.

The measured API container peaked at 2.10 GiB during the local load profile. The deployment uses one vCPU and 4 GiB memory, one in-flight request per instance, and `OMP_NUM_THREADS=1`. This leaves room above the observed memory high-water mark while limiting idle and concurrent compute. It is a small public demo configuration, not a production capacity claim.

PostgreSQL stores tenants, projects, and API-key hashes in Neon. The two verified source model artifacts and their derived ONNX graphs are baked into the immutable API image, so a cold start does not fetch model files and there is no writable model disk. Choose a Neon region close to Cloud Run's `us-east4` region and require TLS in the PostgreSQL connection URL. Neon supplies a standard PostgreSQL connection URI; this application uses the `postgresql+psycopg://` SQLAlchemy scheme. See [Neon's connection string guide](https://neon.com/docs/connect/connect-from-any-app).

The Cloud Run service allows public network access so clients can reach the API URL. Evaluation and API-key routes still require the application's bearer key. Only `/health`, `/live`, `/ready`, `/metrics`, and the public policy catalog are unauthenticated; do not send sensitive content to a public portfolio deployment.

## Prerequisites

- An existing Google Cloud project with billing enabled and permission to enable APIs, create Artifact Registry repositories, create service accounts and secrets, submit Cloud Builds, and deploy Cloud Run services.
- The `gcloud` CLI installed and authenticated with that project selected.
- A Neon PostgreSQL database with a migration owner role and a separate runtime role.
- Python 3.12 and the project virtual environment for applying migrations and issuing the first project key.

Set these values in the shell from the repository root:

```bash
export GOOGLE_CLOUD_PROJECT='your-google-cloud-project-id'
export CLOUD_RUN_REGION='us-east4'
```

`us-east4` is Northern Virginia. Keep the Neon database in a nearby US East region to reduce database round-trip time.

## Prepare PostgreSQL

Create a Neon PostgreSQL project and database. Use its owner connection URL only from your trusted local shell to run the migration and bootstrap the initial tenant/project. Change the URL scheme to `postgresql+psycopg://` and preserve Neon’s `sslmode=require` parameter.

Enter the owner URL without echoing it, then apply the schema and create the demo project and first API key:

```bash
read -s GUARDRAIL_DATABASE_URL
export GUARDRAIL_DATABASE_URL
alembic upgrade head
python scripts/bootstrap_dev_project.py
python scripts/create_api_key.py \
  --project-id <PROJECT_ID_FROM_OUTPUT> \
  --name portfolio-demo \
  --expires-in-days 90
unset GUARDRAIL_DATABASE_URL
```

Save the one-time API key in a password manager. Create a separate runtime role in Neon and grant it table access without schema-owner credentials. In the Neon SQL editor, connected as the migration owner, apply the following after replacing the role and database names:

```sql
GRANT CONNECT ON DATABASE your_database TO guardrail_app;
GRANT USAGE ON SCHEMA public TO guardrail_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO guardrail_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO guardrail_app;
ALTER DEFAULT PRIVILEGES FOR ROLE your_migration_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO guardrail_app;
ALTER DEFAULT PRIVILEGES FOR ROLE your_migration_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO guardrail_app;
```

Create `guardrail_app` in Neon with a password, then use that role's TLS connection URL for Cloud Run. The migration owner URL is used only from your trusted local shell.

## Build the self-contained image

Enable the required Google APIs and create a regional Docker repository:

```bash
gcloud services enable \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  secretmanager.googleapis.com

gcloud artifacts repositories create guardrail \
  --repository-format=docker \
  --location="$CLOUD_RUN_REGION"
```

Cloud Build downloads the exact model revisions, verifies their source manifests, exports the two ONNX graphs, and pushes the completed image to Artifact Registry. The source model and generated graph files are not added to Git.

```bash
export GUARDRAIL_IMAGE="${CLOUD_RUN_REGION}-docker.pkg.dev/${GOOGLE_CLOUD_PROJECT}/guardrail/guardrail-mini:$(git rev-parse --short HEAD)"
gcloud builds submit \
  --region="$CLOUD_RUN_REGION" \
  --config=deployment/cloudrun/cloudbuild.yaml \
  --substitutions="_IMAGE=$GUARDRAIL_IMAGE" \
  .
```

The Cloud Build service account needs permission to push to the `guardrail` Artifact Registry repository. If the build reports a permission error, grant that service account `roles/artifactregistry.writer` on the project or repository and retry.

## Configure the runtime secret

Create the service identity and store the **runtime-role** PostgreSQL URL in Secret Manager. Enter the URL at the hidden prompt; the command sends it through standard input rather than placing it in command history or a build argument.

```bash
gcloud iam service-accounts create guardrail-runtime \
  --display-name='Guardrail Mini Cloud Run runtime'

gcloud secrets create guardrail-database-url \
  --replication-policy=automatic

read -s GUARDRAIL_DATABASE_URL
printf '%s' "$GUARDRAIL_DATABASE_URL" | \
  gcloud secrets versions add guardrail-database-url --data-file=-
unset GUARDRAIL_DATABASE_URL

gcloud secrets add-iam-policy-binding guardrail-database-url \
  --member="serviceAccount:guardrail-runtime@${GOOGLE_CLOUD_PROJECT}.iam.gserviceaccount.com" \
  --role=roles/secretmanager.secretAccessor
```

If the secret already exists, skip `gcloud secrets create` and add a new version. Update the `:1` secret version in `scripts/deploy_cloudrun.sh` to the selected version before deploying. The migration owner URL is never stored in the Cloud Run service.

## Deploy

Deploy the image with HTTPS, the runtime database secret, a startup probe on `/ready`, a four-minute startup-probe budget, a five-minute request timeout, and scale-to-zero/max-one settings:

```bash
export GUARDRAIL_IMAGE
bash scripts/deploy_cloudrun.sh
```

Cloud Run configures the TLS endpoint and provides the service URL at the end of deployment. The service account needs `roles/secretmanager.secretAccessor` on the runtime URL secret. `scripts/deploy_cloudrun.sh` sets the container port to `8080`, requires the API key for inference, caps each instance at one in-flight request, and allows the public endpoint to be reached over HTTPS.

## Verify the public API

Copy the HTTPS URL printed by Cloud Run, then check readiness and evaluate all three policies:

```bash
export BASE_URL='https://your-service-identifier-uc.a.run.app'
curl --fail "$BASE_URL/ready"
curl --fail "$BASE_URL/v1/policies"
curl --fail -X POST "$BASE_URL/v1/guardrails/evaluate" \
  -H "Authorization: Bearer $GUARDRAIL_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"input":"Please summarize the public report.","policies":["toxicity","pii","prompt_injection"]}'
```

The evaluation should return HTTP 200, include one result for each policy, and return `ALLOW` for this benign sample. Without a valid key, the evaluation route should return HTTP 401. The API model metadata should show both pinned model revisions.

## Operations and limits

- Database backups and restoration belong to the managed PostgreSQL provider. Test a backup restore before treating the demo database as important data.
- Model versions and ONNX graphs are immutable image contents. A model update requires a new image build and deployment.
- Cloud Run may scale the service to zero. The first request after an idle period can wait for the container to load its classifiers; subsequent requests use the warm instance.
- The one-instance cap protects the small database and bounds compute. It also limits throughput; increase capacity only after a remote-generator benchmark and a database connection review.
- The local Compose metrics stack is not part of this cloud topology. Cloud Run platform logs and metrics are available in Google Cloud; the unauthenticated `/metrics` route should not be scraped from an untrusted network.
- Create a budget alert in Google Cloud Billing before deploying. Free allowances and prices can change, and image builds, registry storage, network egress, and the Neon plan have their own usage limits or charges.

## Remove the demo deployment

To stop future API compute, delete the Cloud Run service. Delete the Artifact Registry image repository and Secret Manager secret only if you no longer need their contents. Keep or delete the Neon database separately after exporting any data you want to retain.

```bash
gcloud run services delete guardrail-mini --region="$CLOUD_RUN_REGION"
```
