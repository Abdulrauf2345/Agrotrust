// Access token lives in memory only (never localStorage) so an XSS payload
// cannot read it from storage; the tradeoff is that a hard page refresh
// loses it, which is why the refresh token (longer-lived, single-use,
// rotated by the backend) is what persists, and a refresh call runs once on
// app boot to re-establish the in-memory access token.
//
// The refresh token has to live somewhere to survive a reload, and
// localStorage is the only thing available since this backend does not set
// HttpOnly cookies. That's a real, documented security tradeoff: an XSS bug
// could steal the refresh token. It is written down here rather than
// pretended away.

const REFRESH_TOKEN_KEY = "agrotrust.refresh_token";

let accessToken: string | null = null;

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getRefreshToken(): string | null {
  try {
    return localStorage.getItem(REFRESH_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setRefreshToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(REFRESH_TOKEN_KEY, token);
    else localStorage.removeItem(REFRESH_TOKEN_KEY);
  } catch {
    // Storage can throw in private browsing or with blocked site data.
    // Losing persistence degrades to "logged out after reload," not a crash.
  }
}

export function clearTokens(): void {
  setAccessToken(null);
  setRefreshToken(null);
}
