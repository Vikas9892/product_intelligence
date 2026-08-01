import type { AxiosRequestConfig, AxiosResponse } from "axios";

import { apiClient } from "./client";

/**
 * Header the backend stamps on every response with its own server-side
 * measurement of handler duration (`backend/app/middleware/timing.py`, using a
 * monotonic `perf_counter`). Readable only on same-origin responses — see
 * `next.config.ts` for why the app proxies the API.
 */
const RESPONSE_TIME_HEADER = "x-response-time-ms";

/** Header echoing the backend's correlation id (`X-Request-ID` middleware). */
const REQUEST_ID_HEADER = "x-request-id";

/**
 * Where a latency number came from. Surfaced in the UI so a measurement is
 * never presented as something it isn't:
 *
 * - `server` — the backend's own `X-Response-Time-Ms`. Excludes network
 *   transfer, so it is true backend processing time.
 * - `client` — wall-clock round trip measured in the browser. Used only when
 *   the server header is unreadable (a direct cross-origin call without
 *   `expose_headers`). Includes network and proxy overhead.
 */
export type LatencySource = "server" | "client";

/** A response body plus the real timing metadata that came back with it. */
export interface TimedResponse<T> {
  data: T;
  /** Milliseconds. Interpret according to `latencySource`. */
  latencyMs: number;
  latencySource: LatencySource;
  /** Backend correlation id, when readable — useful for support/debugging. */
  requestId: string | null;
}

function readTiming<T>(response: AxiosResponse<T>, clientMs: number): TimedResponse<T> {
  const raw = response.headers?.[RESPONSE_TIME_HEADER];
  const serverMs = typeof raw === "string" ? Number.parseFloat(raw) : Number.NaN;
  const hasServerTiming = Number.isFinite(serverMs);

  const requestId = response.headers?.[REQUEST_ID_HEADER];

  return {
    data: response.data,
    latencyMs: hasServerTiming ? serverMs : clientMs,
    latencySource: hasServerTiming ? "server" : "client",
    requestId: typeof requestId === "string" ? requestId : null,
  };
}

/**
 * `apiPost` that also reports how long the backend took.
 *
 * Prefers the backend's own measurement and falls back to a client-measured
 * round trip, always reporting which one it returned. Nothing here is
 * estimated or synthesized — an unreadable header downgrades the *source*, it
 * never invents a number.
 */
export async function apiPostTimed<T>(
  url: string,
  body?: unknown,
  config?: AxiosRequestConfig,
): Promise<TimedResponse<T>> {
  const startedAt = performance.now();
  const response = await apiClient.post<T>(url, body, config);
  return readTiming(response, performance.now() - startedAt);
}

/** `apiGet` counterpart of {@link apiPostTimed}. */
export async function apiGetTimed<T>(
  url: string,
  config?: AxiosRequestConfig,
): Promise<TimedResponse<T>> {
  const startedAt = performance.now();
  const response = await apiClient.get<T>(url, config);
  return readTiming(response, performance.now() - startedAt);
}
