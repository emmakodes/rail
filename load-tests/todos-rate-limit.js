import http from "k6/http";
import { check } from "k6";

const baseUrl = __ENV.API_BASE_URL || "http://localhost:8000";

export const options = {
  scenarios: {
    abuse: {
      executor: "constant-arrival-rate",
      rate: Number(__ENV.RATE || 1000),
      timeUnit: "1s",
      duration: __ENV.DURATION || "10s",
      preAllocatedVUs: Number(__ENV.PRE_ALLOCATED_VUS || 100),
      maxVUs: Number(__ENV.MAX_VUS || 300),
    },
  },
};

export default function () {
  const response = http.post(
    `${baseUrl}/todos`,
    JSON.stringify({ title: `spam-${Date.now()}-${Math.random()}` }),
    {
      headers: { "Content-Type": "application/json" },
    },
  );

  check(response, {
    "status is 201 or 429": (r) => r.status === 201 || r.status === 429,
    "rate limit headers exist when limited": (r) =>
      r.status !== 429 ||
      Boolean(r.headers["X-Rate-Limit-Limit"] || r.headers["x-rate-limit-limit"]),
  });
}
