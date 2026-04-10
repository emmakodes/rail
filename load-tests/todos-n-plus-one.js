import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  vus: Number(__ENV.VUS || 10),
  duration: __ENV.DURATION || "30s",
};

const baseUrl = __ENV.API_BASE_URL || "http://localhost:8000";
const strategy = __ENV.TAG_LOAD_STRATEGY || "n_plus_one";
const limit = __ENV.LIMIT || "200";

export default function () {
  const response = http.get(
    `${baseUrl}/todos?include_tags=true&tag_load_strategy=${encodeURIComponent(strategy)}&limit=${encodeURIComponent(limit)}&offset=0`,
  );
  check(response, {
    "status is 200": (res) => res.status === 200,
    "db query header exists": (res) => !!res.headers["X-Db-Queries"],
  });
  sleep(1);
}
