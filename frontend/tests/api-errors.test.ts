import { AxiosError, AxiosHeaders } from "axios";
import { describe, expect, it } from "vitest";

import { ApiError, parseApiError } from "@/lib/api/errors";

function axiosErrorWith(status: number, data: unknown): AxiosError {
  const err = new AxiosError("Request failed");
  err.response = {
    status,
    statusText: "",
    data,
    headers: {},
    config: { headers: new AxiosHeaders() },
  };
  return err;
}

describe("parseApiError", () => {
  it("reads the backend error envelope (code/message/details)", () => {
    const err = parseApiError(
      axiosErrorWith(422, {
        success: false,
        error: {
          code: "VALIDATION_ERROR",
          message: "Name is required",
          details: { field: "name" },
        },
      }),
    );
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(422);
    expect(err.code).toBe("VALIDATION_ERROR");
    expect(err.message).toBe("Name is required");
    expect(err.isValidation).toBe(true);
  });

  it("maps status codes to semantic flags", () => {
    expect(parseApiError(axiosErrorWith(401, {})).isUnauthorized).toBe(true);
    expect(parseApiError(axiosErrorWith(403, {})).isForbidden).toBe(true);
    expect(parseApiError(axiosErrorWith(404, {})).isNotFound).toBe(true);
    expect(parseApiError(axiosErrorWith(429, {})).isQuotaExceeded).toBe(true);
    expect(parseApiError(axiosErrorWith(500, {})).isServerError).toBe(true);
  });

  it("treats a response-less axios error as a network error", () => {
    const err = parseApiError(new AxiosError("Network Error"));
    expect(err.isNetworkError).toBe(true);
    expect(err.code).toBe("NETWORK_ERROR");
  });

  it("wraps unknown throwables", () => {
    const err = parseApiError(new Error("boom"));
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("UNKNOWN");
  });

  it("returns the same instance when already an ApiError", () => {
    const original = new ApiError("x", { status: 500, code: "X" });
    expect(parseApiError(original)).toBe(original);
  });
});
