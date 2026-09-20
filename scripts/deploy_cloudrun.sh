#!/usr/bin/env bash

set -euo pipefail

: "${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT to an existing billed Google Cloud project.}"
: "${CLOUD_RUN_REGION:=us-east4}"
: "${GUARDRAIL_IMAGE:?Set GUARDRAIL_IMAGE to the Artifact Registry image built by Cloud Build.}"

service_account="guardrail-runtime@${GOOGLE_CLOUD_PROJECT}.iam.gserviceaccount.com"
secret_name="guardrail-database-url"

gcloud config set project "${GOOGLE_CLOUD_PROJECT}"
gcloud run deploy guardrail-mini \
  --image "${GUARDRAIL_IMAGE}" \
  --region "${CLOUD_RUN_REGION}" \
  --port 8080 \
  --cpu 1 \
  --memory 4Gi \
  --concurrency 1 \
  --min 0 \
  --max 1 \
  --timeout 300 \
  --startup-probe=httpGet.path=/ready,httpGet.port=8080,timeoutSeconds=10,periodSeconds=10,failureThreshold=24 \
  --service-account "${service_account}" \
  --set-env-vars "GUARDRAIL_ENVIRONMENT=production,GUARDRAIL_HOST=0.0.0.0,GUARDRAIL_PORT=8080,GUARDRAIL_MODEL_DEVICE=cpu,GUARDRAIL_MODEL_RUNTIME=onnxruntime,GUARDRAIL_ONNX_CACHE_DIR=/app/data/onnx-cache,GUARDRAIL_RATE_LIMIT_REQUESTS_PER_MINUTE=600,GUARDRAIL_DEMO_ENABLED=true,GUARDRAIL_DEMO_RATE_LIMIT_REQUESTS_PER_MINUTE=10,OMP_NUM_THREADS=1" \
  --set-secrets "GUARDRAIL_DATABASE_URL=${secret_name}:1" \
  --allow-unauthenticated
