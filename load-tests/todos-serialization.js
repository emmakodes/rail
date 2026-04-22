import http from "k6/http";
import { check, sleep } from "k6";

const baseUrl = __ENV.API_BASE_URL || "http://localhost:8000";
const path = __ENV.PATH || "/serialization/todos/slow";
const rowCount = __ENV.ROW_COUNT || "500";

export const options = {
  vus: Number(__ENV.VUS || 5),
  duration: __ENV.DURATION || "20s",
};

export default function () {
  const response = http.get(
    `${baseUrl}${path}?row_count=${encodeURIComponent(rowCount)}`,
  );

  check(response, {
    "status is 200 or 304": (r) => r.status === 200 || r.status === 304,
    "serialization headers exist": (r) =>
      Boolean(r.headers["X-Db-Ms"] || r.headers["x-db-ms"]),
  });

  sleep(0.2);
}
