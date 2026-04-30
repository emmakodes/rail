import http from "k6/http";
import { check, sleep } from "k6";

const API_BASE_URL = __ENV.API_BASE_URL || "http://localhost:8000";
const MODE = __ENV.MODE || "broken";
const HOLD_SECONDS = __ENV.HOLD_SECONDS || "0.5";

export const options = {
  scenarios: {
    writer_a: {
      executor: "constant-vus",
      vus: Number(__ENV.WRITER_A_VUS || 5),
      duration: __ENV.DURATION || "20s",
      exec: "writerA",
    },
    writer_b: {
      executor: "constant-vus",
      vus: Number(__ENV.WRITER_B_VUS || 5),
      duration: __ENV.DURATION || "20s",
      exec: "writerB",
    },
  },
};

function buildPath(data, reverseInput) {
  const baseParams = `first_id=${data.targetIds[0]}&second_id=${data.targetIds[1]}&completed=true`;
  if (MODE === "sorted") {
    return `/deadlock/fixed/sorted?${baseParams}&hold_seconds=${encodeURIComponent(HOLD_SECONDS)}&reverse_input=${reverseInput}`;
  }
  if (MODE === "batch") {
    return `/deadlock/fixed/batch?${baseParams}&reverse_input=${reverseInput}`;
  }
  return reverseInput
    ? `/deadlock/broken/reverse?${baseParams}&hold_seconds=${encodeURIComponent(HOLD_SECONDS)}`
    : `/deadlock/broken/forward?${baseParams}&hold_seconds=${encodeURIComponent(HOLD_SECONDS)}`;
}

function postPath(path) {
  return http.post(`${API_BASE_URL}${path}`, null, {
    headers: {
      "Content-Type": "application/json",
    },
  });
}

export function setup() {
  const resetResponse = postPath("/deadlock/reset");
  check(resetResponse, {
    "deadlock reset is 200": (r) => r.status === 200,
  });

  const body = resetResponse.json();
  const targetIds = body.targets.map((target) => target.id);
  return { targetIds };
}

export function writerA(data) {
  const response = postPath(buildPath(data, false));
  check(response, {
    "broken mode is 200 or 409": (r) => MODE !== "broken" || r.status === 200 || r.status === 409,
    "fixed mode is 200": (r) => MODE === "broken" || r.status === 200,
  });
  sleep(0.2);
}

export function writerB(data) {
  const response = postPath(buildPath(data, true));
  check(response, {
    "broken mode is 200 or 409": (r) => MODE !== "broken" || r.status === 200 || r.status === 409,
    "fixed mode is 200": (r) => MODE === "broken" || r.status === 200,
  });
  sleep(0.2);
}
