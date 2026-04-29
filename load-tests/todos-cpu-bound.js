import http from "k6/http";
import { check, sleep } from "k6";

const baseUrl = __ENV.API_BASE_URL || "http://localhost:8000";
const cpuPath = __ENV.CPU_PATH || "/cpu/blocking";
const fastPath = __ENV.FAST_PATH || "/cpu/fast";
const iterations = __ENV.CPU_ITERATIONS || "10000000";
const jobs = __ENV.CPU_JOBS || "1";

export const options = {
  scenarios: {
    cpu_heavy: {
      executor: "constant-vus",
      vus: Number(__ENV.CPU_VUS || 2),
      duration: __ENV.DURATION || "20s",
      exec: "cpuHeavy",
    },
    fast_reads: {
      executor: "constant-vus",
      vus: Number(__ENV.FAST_VUS || 5),
      duration: __ENV.DURATION || "20s",
      exec: "fastReads",
    },
  },
};

export function cpuHeavy() {
  const response = http.get(
    `${baseUrl}${cpuPath}?iterations=${encodeURIComponent(iterations)}&jobs=${encodeURIComponent(jobs)}`,
  );
  check(response, {
    "cpu endpoint is 200": (r) => r.status === 200,
  });
  sleep(0.2);
}

export function fastReads() {
  const response = http.get(`${baseUrl}${fastPath}`);
  check(response, {
    "fast endpoint is 200": (r) => r.status === 200,
  });
  sleep(0.2);
}
