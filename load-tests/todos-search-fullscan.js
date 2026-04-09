import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  vus: Number(__ENV.VUS || 20),
  duration: __ENV.DURATION || "30s",
};

const baseUrl = __ENV.API_BASE_URL || "http://localhost:8000";
const search = __ENV.SEARCH || "work";
const searchMode = __ENV.SEARCH_MODE || "contains";
const limit = __ENV.LIMIT || "50";
const offset = __ENV.OFFSET || "0";

export default function () {
  const response = http.get(
    `${baseUrl}/todos?search=${encodeURIComponent(search)}&search_mode=${searchMode}&limit=${encodeURIComponent(limit)}&offset=${encodeURIComponent(offset)}`,
  );
  check(response, {
    "status is 200": (res) => res.status === 200,
  });
  sleep(1);
}
