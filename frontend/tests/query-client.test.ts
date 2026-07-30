import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api/errors";
import { createQueryClient } from "@/lib/api/query-client";

function retryFn() {
  const retry = createQueryClient().getDefaultOptions().queries?.retry;
  if (typeof retry !== "function") throw new Error("expected a retry function");
  return retry as (failureCount: number, error: unknown) => boolean;
}

describe("query client retry policy", () => {
  it("never retries 4xx client errors", () => {
    const retry = retryFn();
    expect(retry(0, new ApiError("bad", { status: 400, code: "X" }))).toBe(false);
    expect(retry(0, new ApiError("nope", { status: 404, code: "X" }))).toBe(false);
  });

  it("retries network and server errors up to twice", () => {
    const retry = retryFn();
    const serverError = new ApiError("boom", { status: 500, code: "X" });
    expect(retry(0, serverError)).toBe(true);
    expect(retry(1, serverError)).toBe(true);
    expect(retry(2, serverError)).toBe(false);
  });

  it("disables automatic mutation retries", () => {
    const mutationRetry = createQueryClient().getDefaultOptions().mutations?.retry;
    expect(mutationRetry).toBe(false);
  });
});
