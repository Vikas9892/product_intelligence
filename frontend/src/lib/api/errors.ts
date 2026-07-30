import axios from "axios";

/**
 * The backend's uniform error envelope:
 * `{ "success": false, "error": { "code", "message", "details" } }`.
 */
interface ErrorEnvelope {
  success?: boolean;
  error?: {
    code?: string;
    message?: string;
    details?: unknown;
  };
}

/**
 * Normalized API error. Every failed request from the client rejects with one
 * of these, so features handle a single shape regardless of whether the failure
 * came from the backend envelope, a network fault, or an unexpected response.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details?: unknown;

  constructor(message: string, opts: { status: number; code: string; details?: unknown }) {
    super(message);
    this.name = "ApiError";
    this.status = opts.status;
    this.code = opts.code;
    this.details = opts.details;
  }

  /** No response was received (offline, DNS, CORS, timeout). */
  get isNetworkError(): boolean {
    return this.status === 0;
  }
  get isUnauthorized(): boolean {
    return this.status === 401;
  }
  get isForbidden(): boolean {
    return this.status === 403;
  }
  get isNotFound(): boolean {
    return this.status === 404;
  }
  get isValidation(): boolean {
    return this.status === 422;
  }
  get isQuotaExceeded(): boolean {
    return this.status === 429;
  }
  get isServerError(): boolean {
    return this.status >= 500;
  }
}

/**
 * Convert any thrown value (typically an Axios error) into an `ApiError`,
 * preferring the backend envelope's `code`/`message`/`details` when present.
 */
export function parseApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;

  if (axios.isAxiosError(error)) {
    const status = error.response?.status ?? 0;
    const envelope = error.response?.data as ErrorEnvelope | undefined;
    const inner = envelope?.error;

    if (status === 0) {
      return new ApiError("Could not reach the server. Check your connection and try again.", {
        status: 0,
        code: "NETWORK_ERROR",
      });
    }

    return new ApiError(inner?.message ?? error.message ?? "Request failed", {
      status,
      code: inner?.code ?? `HTTP_${status}`,
      details: inner?.details,
    });
  }

  return new ApiError(error instanceof Error ? error.message : "Unexpected error", {
    status: 0,
    code: "UNKNOWN",
  });
}
