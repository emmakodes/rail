import http from "k6/http";
import { check, sleep } from "k6";

const baseUrl = __ENV.API_BASE_URL || "http://localhost:8000";
const path = __ENV.PATH || "/memory/leak";
const payloadSize = Number(__ENV.PAYLOAD_SIZE || 50000);
const body = JSON.stringify({
  note: "x".repeat(payloadSize),
  created_at: new Date().toISOString(),
});

export const options = {
  vus: Number(__ENV.VUS || 20),
  duration: __ENV.DURATION || "20s",
};

export function setup() {
  const reset = http.post(`${baseUrl}/memory/reset`);
  check(reset, {
    "memory reset is 200": (r) => r.status === 200,
  });
}

export default function () {
  const response = http.post(`${baseUrl}${path}`, body, {
    headers: { "Content-Type": "application/json" },
  });

  check(response, {
    "status is 200": (r) => r.status === 200,
  });

  sleep(0.1);
}
