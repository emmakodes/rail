import http from "k6/http";
import { check, sleep } from "k6";

const baseUrl = __ENV.API_BASE_URL || "http://localhost:8000";
const targetPath = __ENV.TARGET_PATH || "/external/enrichment/no-breaker";
const simulate = __ENV.SIMULATE || "timeout";

export const options = {
  scenarios: {
    callers: {
      executor: "constant-vus",
      vus: Number(__ENV.VUS || 10),
      duration: __ENV.DURATION || "20s",
      exec: "callers",
    },
  },
};

export function callers() {
  const response = http.get(`${baseUrl}${targetPath}?simulate=${encodeURIComponent(simulate)}`);
  check(response, {
    "no-breaker is 200 or 504": (r) =>
      targetPath !== "/external/enrichment/no-breaker" || r.status === 200 || r.status === 504,
    "breaker path is 200 or 504": (r) =>
      targetPath !== "/external/enrichment/circuit-breaker" || r.status === 200 || r.status === 504,
  });
  sleep(0.2);
}
