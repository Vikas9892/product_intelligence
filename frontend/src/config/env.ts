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
  /**
   * Base URL the browser sends API requests to, without the API prefix.
   *
   * Defaults to `""` — a **same-origin** path, served by this app's rewrite
   * proxy (see `next.config.ts`). That default is deliberate: the backend ships
   * with CORS disabled and without `expose_headers`, so same-origin is the only
   * configuration that both connects at all and can read the backend's
   * `X-Response-Time-Ms` timing header.
   *
   * Set to an absolute origin (e.g. `http://localhost:8000`) to bypass the
   * proxy and call the backend directly; that requires the backend to be run
   * with `APPLICATION__CORS_ALLOWED_ORIGINS` configured.
   */
  apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "",
  /** Versioned API prefix the backend mounts business routes under. */
  apiPrefix: process.env.NEXT_PUBLIC_API_PREFIX ?? "/api/v1",
  /** Header name used for API-key auth when the enterprise layer is enabled. */
  apiKeyHeader: process.env.NEXT_PUBLIC_API_KEY_HEADER ?? "X-API-Key",
  /**
   * Whether the deployment runs against a backend with the enterprise layer
   * enabled. `false` (the default) is single-tenant demo mode: no auth gate,
   * no API key required. Set to `true` when the backend has
   * `ENTERPRISE__ENABLED=true` so the UI activates API-key auth and RBAC gating.
   */
  enterpriseEnabled: process.env.NEXT_PUBLIC_ENTERPRISE_ENABLED === "true",
  /** Display name used in the UI shell and document title. */
  appName: process.env.NEXT_PUBLIC_APP_NAME ?? "Product Intelligence",
} as const;

export type Env = typeof env;
