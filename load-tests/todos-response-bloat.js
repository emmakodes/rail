import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  vus: Number(__ENV.VUS || 5),
  duration: __ENV.DURATION || "20s",
};

const baseUrl = __ENV.API_BASE_URL || "http://localhost:8000";
const disablePagination = __ENV.DISABLE_PAGINATION || "false";
const limit = __ENV.LIMIT || "50";

export default function () {
  const response = http.get(
    `${baseUrl}/todos?disable_pagination=${encodeURIComponent(disablePagination)}&limit=${encodeURIComponent(limit)}&offset=0`,
  );
  check(response, {
    "status is 200": (res) => res.status === 200,
    "response bytes header exists": (res) => !!res.headers["X-Response-Bytes"],
  });
  sleep(1);
}
