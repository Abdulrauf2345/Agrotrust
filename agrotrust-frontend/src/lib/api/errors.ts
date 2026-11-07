import type { ApiErrorBody } from "@/types/api";

// Error codes that are already safe, readable sentences when the backend
// writes them (DomainError subclasses carry their own message). Anything
// not in this allowlist gets a generic fallback instead of leaking an
// internal detail (a ledger entry id, a stack hint, a SQL fragment) to the
// screen.
const READABLE_PREFIXES = ["VALIDATION_FAILED", "PERMISSION_DENIED", "CONFLICT", "NOT_FOUND", "RATE_LIMITED"];

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody | null) {
    const code = body?.error?.code ?? "UNKNOWN_ERROR";
    const rawMessage = body?.error?.message ?? "";
    super(ApiError.toDisplayMessage(status, code, rawMessage));
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = body?.error?.details ?? {};
  }

  private static toDisplayMessage(status: number, code: string, rawMessage: string): string {
    if (code === "AUTHENTICATION_FAILED") {
      return "Your session has expired. Please sign in again.";
    }
    if (READABLE_PREFIXES.some((p) => code.startsWith(p)) && rawMessage) {
      return rawMessage;
    }
    if (status >= 500) {
      return "Something went wrong on our side. Please try again in a moment.";
    }
    return rawMessage || "Something went wrong. Please try again.";
  }
}

export function isRetryable(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false;
  if (error.status === 429) return true;
  if (error.status >= 500) return true;
  return false;
}
