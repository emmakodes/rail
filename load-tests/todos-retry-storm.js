import http from "k6/http";
import { check, sleep } from "k6";

const baseUrl = __ENV.API_BASE_URL || "http://localhost:8000";
const path = __ENV.PATH || "/resilience/retry-storm";
const delaySeconds = __ENV.DELAY_SECONDS || "1";
const failAfterDelay = __ENV.FAIL_AFTER_DELAY || "true";

export const options = {
  vus: Number(__ENV.VUS || 20),
  duration: __ENV.DURATION || "20s",
};

export function setup() {
  http.post(`${baseUrl}/resilience/retry/reset`);
}

export default function () {
  const response = http.get(
    `${baseUrl}${path}?delay_seconds=${encodeURIComponent(delaySeconds)}&fail_after_delay=${encodeURIComponent(failAfterDelay)}`,
  );

  check(response, {
    "status is 200 or 503": (r) => r.status === 200 || r.status === 503,
    "retry headers exist when present": (r) =>
      !r.headers["X-Retry-Attempts"] || Boolean(r.headers["X-Retry-Attempts"]),
  });

  sleep(0.1);
}
