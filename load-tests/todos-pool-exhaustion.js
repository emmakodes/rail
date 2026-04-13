import http from "k6/http";
import { check, sleep } from "k6";

const baseUrl = __ENV.API_BASE_URL || "http://localhost:8000";
const holdSeconds = __ENV.HOLD_SECONDS || "5";

export const options = {
  vus: Number(__ENV.VUS || 10),
  duration: __ENV.DURATION || "20s",
};

export default function () {
  const response = http.get(
    `${baseUrl}/pool/exhaust?hold_seconds=${encodeURIComponent(holdSeconds)}`,
  );

  check(response, {
    "status is 200 or 503": (r) => r.status === 200 || r.status === 503,
    "request id header exists": (r) => Boolean(r.headers["x-request-id"]),
  });

  sleep(1);
}
