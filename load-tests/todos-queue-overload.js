import http from "k6/http";
import { check } from "k6";

const baseUrl = __ENV.API_BASE_URL || "http://localhost:8000";
const backgroundMode = __ENV.BACKGROUND_MODE || "unbounded";

export const options = {
  scenarios: {
    producers: {
      executor: "constant-arrival-rate",
      rate: Number(__ENV.RATE || 500),
      timeUnit: "1s",
      duration: __ENV.DURATION || "20s",
      preAllocatedVUs: Number(__ENV.PREALLOCATED_VUS || 50),
      maxVUs: Number(__ENV.MAX_VUS || 200),
      exec: "createTodo",
    },
  },
};

export function createTodo() {
  const payload = JSON.stringify({
    title: `queue overload ${__ITER} ${Date.now()}`,
  });
  const response = http.post(
    `${baseUrl}/todos?background_mode=${encodeURIComponent(backgroundMode)}`,
    payload,
    {
      headers: {
        "Content-Type": "application/json",
      },
    },
  );
  check(response, {
    "todo create is 201": (r) => r.status === 201,
  });
}
