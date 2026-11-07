import { describe, it, expect } from "vitest";
import { ApiError, isRetryable } from "./errors";

describe("ApiError", () => {
  it("maps AUTHENTICATION_FAILED to a session-expired message", () => {
    const err = new ApiError(401, { error: { code: "AUTHENTICATION_FAILED", message: "bad token", details: {} } });
    expect(err.message).toBe("Your session has expired. Please sign in again.");
  });

  it("passes through an already-readable business message", () => {
    const err = new ApiError(422, {
      error: { code: "VALIDATION_FAILED", message: "quantity must be positive", details: {} },
    });
    expect(err.message).toBe("quantity must be positive");
  });

  it("never leaks an internal message for an unrecognized code", () => {
    const err = new ApiError(500, {
      error: { code: "INTERNAL_ERROR", message: "ledger entry le_8f2a failed constraint", details: {} },
    });
    expect(err.message).not.toContain("le_8f2a");
    expect(err.message).toBe("Something went wrong on our side. Please try again in a moment.");
  });

  it("retries 5xx and 429 but not 4xx validation errors", () => {
    const serverError = new ApiError(503, null);
    const rateLimited = new ApiError(429, null);
    const validation = new ApiError(422, { error: { code: "VALIDATION_FAILED", message: "x", details: {} } });
    expect(isRetryable(serverError)).toBe(true);
    expect(isRetryable(rateLimited)).toBe(true);
    expect(isRetryable(validation)).toBe(false);
  });
});
