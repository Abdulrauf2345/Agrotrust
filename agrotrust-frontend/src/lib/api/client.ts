import { ApiError } from "./errors";
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setAccessToken,
  setRefreshToken,
} from "@/lib/auth/tokenStorage";
import type { ApiErrorBody, AuthTokens } from "@/types/api";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

type QueryValue = string | number | boolean | undefined | null;

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Record<string, QueryValue>;
  idempotencyKey?: string;
  skipAuth?: boolean;
}

// Multiple queries can 401 around the same moment (several widgets fetching
// on mount). Without single-flighting, each would fire its own refresh
// call, racing to rotate the same single-use refresh token; the losers
// would then retry against an already-revoked token and force a real
// logout. This promise is the lock: the first 401 starts the refresh, every
// other caller awaits the same promise instead of starting its own.
let refreshInFlight: Promise<string | null> | null = null;

async function performRefresh(): Promise<string | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return null;
  try {
    const res = await fetch(`${BASE_URL}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) {
      clearTokens();
      return null;
    }
    const data = (await res.json()) as AuthTokens;
    setAccessToken(data.access_token);
    setRefreshToken(data.refresh_token);
    return data.access_token;
  } catch {
    clearTokens();
    return null;
  }
}

function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const url = new URL(path.replace(/^\//, ""), `${BASE_URL}/`);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null) url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

async function parseErrorBody(res: Response): Promise<ApiErrorBody | null> {
  try {
    return (await res.json()) as ApiErrorBody;
  } catch {
    return null;
  }
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, query, idempotencyKey, skipAuth = false } = options;

  const doFetch = async (): Promise<Response> => {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (!skipAuth) {
      const token = getAccessToken();
      if (token) headers.Authorization = `Bearer ${token}`;
    }
    if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;

    return fetch(buildUrl(path, query), {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  };

  let res = await doFetch();

  if (res.status === 401 && !skipAuth && getRefreshToken()) {
    if (!refreshInFlight) {
      refreshInFlight = performRefresh().finally(() => {
        refreshInFlight = null;
      });
    }
    const newToken = await refreshInFlight;
    if (newToken) {
      res = await doFetch();
    }
  }

  if (!res.ok) {
    const errorBody = await parseErrorBody(res);
    throw new ApiError(res.status, errorBody);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
