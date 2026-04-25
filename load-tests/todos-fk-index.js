import http from "k6/http";
import { check, sleep } from "k6";

const API_BASE_URL = __ENV.API_BASE_URL || "http://localhost:8000";
const MODE = __ENV.MODE || "no_index";
const LIMIT = Number(__ENV.LIMIT || 50);
const COMPLETED_ONLY = (__ENV.COMPLETED_ONLY || "false").toLowerCase() === "true";

export const options = {
  vus: Number(__ENV.VUS || 10),
  duration: __ENV.DURATION || "20s",
};

export function setup() {
  const dropResponse = http.post(`${API_BASE_URL}/fk-index/index/drop`);
  check(dropResponse, { "fk index drop is 200": (r) => r.status === 200 });

  if (MODE === "basic") {
    const basicResponse = http.post(`${API_BASE_URL}/fk-index/index/basic`);
    check(basicResponse, { "fk basic index is 200": (r) => r.status === 200 });
  }

  if (MODE === "composite") {
    const compositeResponse = http.post(`${API_BASE_URL}/fk-index/index/composite`);
    check(compositeResponse, { "fk composite index is 200": (r) => r.status === 200 });
  }

  const statusResponse = http.get(`${API_BASE_URL}/fk-index/status`);
  check(statusResponse, { "fk status is 200": (r) => r.status === 200 });
  const statusPayload = statusResponse.json();

  return {
    userId: statusPayload.hot_user_id || 1,
  };
}

export default function (data) {
  const response = http.get(
    `${API_BASE_URL}/fk-index/join?user_id=${data.userId}&limit=${LIMIT}&completed_only=${COMPLETED_ONLY}`
  );

  check(response, {
    "fk join is 200": (r) => r.status === 200,
  });

  sleep(0.2);
}
