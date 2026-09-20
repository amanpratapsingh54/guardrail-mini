import http from 'k6/http';
import { check } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const baseURL = __ENV.BASE_URL || 'http://127.0.0.1:8000';
const apiKey = __ENV.API_KEY;
const rate = Number(__ENV.RATE || 10);
const duration = __ENV.DURATION || '30s';

if (!apiKey) {
  throw new Error('Set API_KEY to a local Guardrail Mini API key.');
}
if (!Number.isInteger(rate) || rate < 1) {
  throw new Error('RATE must be a positive integer in requests per second.');
}

const guardrailErrors = new Rate('guardrail_errors');
const policyPathLatency = new Trend('guardrail_policy_path_ms');
const apiOverheadEstimate = new Trend('guardrail_api_overhead_estimate_ms');
const requestedPolicies = ['toxicity', 'pii', 'prompt_injection'];

export const options = {
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
  scenarios: {
    evaluate_all_policies: {
      executor: 'constant-arrival-rate',
      rate,
      timeUnit: '1s',
      duration,
      preAllocatedVUs: Math.max(20, rate * 2),
      maxVUs: Math.max(40, rate * 4),
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    guardrail_errors: ['rate<0.01'],
    dropped_iterations: ['count==0'],
  },
};

export default function () {
  const response = http.post(
    `${baseURL}/v1/guardrails/evaluate`,
    JSON.stringify({
      input: 'Please summarize the public report.',
      policies: requestedPolicies,
    }),
    {
      headers: {
        Authorization: `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
      },
      tags: { name: 'POST /v1/guardrails/evaluate' },
      timeout: '30s',
    },
  );

  let body = null;
  if (response.status === 200) {
    try {
      body = response.json();
    } catch {
      body = null;
    }
  }

  const validResponse =
    body !== null &&
    requestedPolicies.every((policy) => Object.hasOwn(body.policy_results || {}, policy)) &&
    ['ALLOW', 'BLOCK', 'REVIEW'].includes(body.action);
  const passed = check(response, {
    'HTTP 200 with all requested policy results': () => response.status === 200 && validResponse,
  });
  guardrailErrors.add(!passed);

  if (passed && typeof body.latency_ms === 'number') {
    policyPathLatency.add(body.latency_ms);
    apiOverheadEstimate.add(Math.max(0, response.timings.duration - body.latency_ms));
  }
}
