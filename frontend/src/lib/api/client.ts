import axios from "axios";

import { env } from "@/config/env";

import { getApiKey } from "./auth-token";
import { parseApiError } from "./errors";

/**
 * Versioned API prefix. The client's `baseURL` is the backend root, so
 * versioned business routes are called as `${API_PREFIX}/products/...` while
 * the unversioned probes (`/health`, `/ready`, `/version`) are called at the
 * root. Endpoint functions (added per feature stage) compose these paths.
 */
export const API_PREFIX = env.apiPrefix;

/**
 * The single Axios instance used by the whole app. Components never import this
 * directly — they go through endpoint functions and React Query hooks.
 *
 * - **Request interceptor** attaches the API key header when one is present
 *   (single-tenant demo mode sends no header).
 * - **Response interceptor** normalizes every failure into an `ApiError`, so
 *   callers always handle one error shape.
 */
export const apiClient = axios.create({
  baseURL: env.apiBaseUrl,
  timeout: 30_000,
  headers: { Accept: "application/json" },
});

apiClient.interceptors.request.use((config) => {
  const key = getApiKey();
  if (key) {
    config.headers.set(env.apiKeyHeader, key);
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => Promise.reject(parseApiError(error)),
);
