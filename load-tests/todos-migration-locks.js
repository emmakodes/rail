import http from "k6/http";
import { check, sleep } from "k6";

const API_BASE_URL = __ENV.API_BASE_URL || "http://localhost:8000";
const MODE = __ENV.MODE || "dangerous";
const READ_LIMIT = Number(__ENV.READ_LIMIT || 50);
const VUS = Number(__ENV.VUS || 10);
const DURATION = __ENV.DURATION || "20s";

export const options = {
  vus: VUS,
  duration: DURATION,
};

export function setup() {
  const resetResponse = http.post(`${API_BASE_URL}/migrations/zero-downtime/reset`);
  check(resetResponse, { "migration reset is 200": (r) => r.status === 200 });

  const startPath =
    MODE === "safe"
      ? "/migrations/zero-downtime/safe/start"
      : "/migrations/zero-downtime/dangerous/start";

  const startResponse = http.post(`${API_BASE_URL}${startPath}`);
  check(startResponse, { "migration start is 200": (r) => r.status === 200 });

  sleep(0.5);
}

export default function () {
  const response = http.get(
    `${API_BASE_URL}/migrations/zero-downtime/read?limit=${READ_LIMIT}`
  );

  check(response, {
    "dangerous mode read is 200 or 500": (r) =>
      MODE !== "dangerous" || r.status === 200 || r.status === 500,
    "safe mode read is 200": (r) => MODE !== "safe" || r.status === 200,
  });

  sleep(0.2);
}
