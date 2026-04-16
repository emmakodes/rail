import http from "k6/http";
import { check, sleep } from "k6";

const baseUrl = __ENV.API_BASE_URL || "http://localhost:8000";
const cacheStrategy = __ENV.CACHE_STRATEGY || "plain";

export const options = {
  vus: Number(__ENV.VUS || 200),
  duration: __ENV.DURATION || "5s",
};

export function setup() {
  const warm = http.get(`${baseUrl}/todos?cache_strategy=${encodeURIComponent(cacheStrategy)}`);
  check(warm, {
    "warm cache is 200": (r) => r.status === 200,
  });

  const reset = http.get(`${baseUrl}/cache/todos/reset`);
  check(reset, {
    "cache reset is 200": (r) => r.status === 200,
  });

  return { cacheStrategy };
}

export default function (data) {
  const response = http.get(
    `${baseUrl}/todos?cache_strategy=${encodeURIComponent(data.cacheStrategy)}`,
  );

  check(response, {
    "status is 200": (r) => r.status === 200,
    "cache status header exists": (r) => Boolean(r.headers["X-Cache-Status"] || r.headers["x-cache-status"]),
  });

  sleep(0.1);
}
