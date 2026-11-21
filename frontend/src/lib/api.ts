const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";
const TOKEN_KEY = "watchdog_access_token";
const REFRESH_TOKEN_KEY = "watchdog_refresh_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function getRefreshToken() {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setRefreshToken(token: string) {
  localStorage.setItem(REFRESH_TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

export function apiUrl(path: string) {
  return `${API_BASE_URL}${path}`;
}

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  auth?: boolean;
};

function extractErrorMessage(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const detail = (payload as { detail?: unknown; message?: unknown }).detail;
  const message = (payload as { message?: unknown }).message;
  if (typeof detail === "string") {
    return detail;
  }
  // FastAPI 422 validation errors return detail as an array of {loc, msg} objects
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (item && typeof item === "object" && typeof (item as { msg?: unknown }).msg === "string") {
          const loc = Array.isArray((item as { loc?: unknown[] }).loc)
            ? (item as { loc: unknown[] }).loc.slice(1).join(".")
            : "";
          return loc ? `${(item as { msg: string }).msg} (${loc})` : (item as { msg: string }).msg;
        }
        return String(item);
      })
      .filter(Boolean);
    return parts.length ? parts.join("; ") : null;
  }
  if (typeof message === "string") {
    return message;
  }
  return null;
}

// Single-flight access-token refresh: concurrent 401s share one attempt.
let refreshPromise: Promise<boolean> | null = null;
let redirectingToLogin = false;

async function refreshAccessToken(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      const refreshToken = getRefreshToken();
      if (!refreshToken) return false;
      try {
        const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (!response.ok) return false;
        const payload = (await response.json().catch(() => null)) as
          | { access_token?: unknown; refresh_token?: unknown }
          | null;
        if (payload && typeof payload.access_token === "string") {
          setToken(payload.access_token);
          if (typeof payload.refresh_token === "string") {
            setRefreshToken(payload.refresh_token);
          }
          return true;
        }
        return false;
      } catch {
        return false;
      } finally {
        setTimeout(() => {
          refreshPromise = null;
        }, 0);
      }
    })();
  }
  return refreshPromise;
}

function redirectToLogin() {
  if (redirectingToLogin) return;
  redirectingToLogin = true;
  clearToken();
  window.location.assign("/login");
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const send = async (): Promise<Response> => {
    const headers: HeadersInit = {
      "Content-Type": "application/json",
    };
    const token = getToken();
    if (options.auth !== false && token) {
      headers.Authorization = `Bearer ${token}`;
    }
    return fetch(`${API_BASE_URL}${path}`, {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  };

  let response = await send();

  // Access token expired: refresh once and retry before giving up.
  // Only skip refresh for the refresh endpoint itself; /auth/me must refresh.
  if (
    response.status === 401 &&
    options.auth !== false &&
    getRefreshToken() &&
    !path.startsWith("/auth/refresh")
  ) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      response = await send();
    } else {
      redirectToLogin();
      throw new Error("Session expired. Log in again.");
    }
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(extractErrorMessage(payload) ?? "Request failed");
  }

  if (payload && typeof payload === "object" && "data" in payload) {
    return payload.data as T;
  }
  return payload as T;
}

export function makeQuery(params: Record<string, string | number | boolean | null | undefined>) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== "") {
      query.set(key, String(value));
    }
  });
  const text = query.toString();
  return text ? `?${text}` : "";
}
