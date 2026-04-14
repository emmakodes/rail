import http from "k6/http";
import { check, sleep } from "k6";

const baseUrl = __ENV.API_BASE_URL || "http://localhost:8000";
const blockingPath = __ENV.BLOCKING_PATH || "/loop/blocking";
const blockSeconds = __ENV.BLOCK_SECONDS || "1";

export const options = {
  scenarios: {
    blockers: {
      executor: "constant-vus",
      vus: Number(__ENV.BLOCKING_VUS || 5),
      duration: __ENV.DURATION || "20s",
      exec: "blockers",
    },
    fast_reads: {
      executor: "constant-vus",
      vus: Number(__ENV.FAST_VUS || 5),
      duration: __ENV.DURATION || "20s",
      exec: "fastReads",
    },
  },
};

export function blockers() {
  const response = http.get(
    `${baseUrl}${blockingPath}?block_seconds=${encodeURIComponent(blockSeconds)}`,
  );
  check(response, {
    "blocking endpoint is 200": (r) => r.status === 200,
  });
  sleep(0.2);
}

export function fastReads() {
  const response = http.get(`${baseUrl}/loop/fast`);
  check(response, {
    "fast endpoint is 200": (r) => r.status === 200,
  });
  sleep(0.2);
}
