/**
 * Centralized, typed access to public runtime configuration.
 *
 * Only `NEXT_PUBLIC_*` variables are exposed to the browser, and every value
 * has a safe default so the app boots with **zero configuration** in local /
 * single-tenant demo mode (the confirmed default persona). Nothing here reaches
 * out to the backend — these are just the values the API layer will use later
 * (Stage 3, Milestone 3+).
 *
 * Reading configuration through this module (rather than sprinkling
 * `process.env.NEXT_PUBLIC_*` across the codebase) keeps every default defined
 * exactly once, mirroring the backend's single-source-of-truth settings module.
 */
export const env = {
  /** Base URL of the FastAPI backend, without the API prefix. */
  apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
  /** Versioned API prefix the backend mounts business routes under. */
  apiPrefix: process.env.NEXT_PUBLIC_API_PREFIX ?? "/api/v1",
  /** Header name used for API-key auth when the enterprise layer is enabled. */
  apiKeyHeader: process.env.NEXT_PUBLIC_API_KEY_HEADER ?? "X-API-Key",
  /** Display name used in the UI shell and document title. */
  appName: process.env.NEXT_PUBLIC_APP_NAME ?? "Product Intelligence",
} as const;

export type Env = typeof env;
