import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  vus: Number(__ENV.VUS || 50),
  duration: __ENV.DURATION || "30s",
};

const baseUrl = __ENV.API_BASE_URL || "http://localhost:8000";

export default function () {
  const response = http.get(`${baseUrl}/todos`);
  check(response, {
    "status is 200": (res) => res.status === 200,
  });
  sleep(1);
}
