import http from "k6/http";
import { check, sleep } from "k6";

const baseUrl = __ENV.API_BASE_URL || "http://localhost:8000";
const slowPath = __ENV.SLOW_PATH || "/external/hang";

export const options = {
  scenarios: {
    slow_calls: {
      executor: "constant-vus",
      vus: Number(__ENV.SLOW_VUS || 5),
      duration: __ENV.DURATION || "20s",
      exec: "slowCalls",
    },
    fast_calls: {
      executor: "constant-vus",
      vus: Number(__ENV.FAST_VUS || 5),
      duration: __ENV.DURATION || "20s",
      exec: "fastCalls",
    },
  },
};

export function slowCalls() {
  const response = http.get(`${baseUrl}${slowPath}`);
  check(response, {
    "slow path is 200 or 504": (r) => r.status === 200 || r.status === 504,
  });
  sleep(0.2);
}

export function fastCalls() {
  const response = http.get(`${baseUrl}/external/fast`);
  check(response, {
    "fast path is 200": (r) => r.status === 200,
  });
  sleep(0.2);
}
