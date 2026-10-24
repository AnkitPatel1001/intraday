// Fetch wrapper for the market intelligence backend.

export const BASE_URL: string =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  path: string;

  constructor(message: string, status: number, path: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.path = path;
  }
}

const SESSION_PATH = "/api/v1/auth/session";
const SESSION_TOKEN_KEY = "mi_session";

let cachedToken: string | null = null;
let tokenLoaded = false;

function isBrowser(): boolean {
  return typeof window !== "undefined";
}

function loadToken(): string | null {
  if (!isBrowser()) return null;
  if (!tokenLoaded) {
    tokenLoaded = true;
    try {
      cachedToken = window.localStorage.getItem(SESSION_TOKEN_KEY);
    } catch {
      cachedToken = null;
    }
  }
  return cachedToken;
}

function storeToken(token: string | null): void {
  cachedToken = token;
  tokenLoaded = true;
  if (!isBrowser()) return;
  try {
    if (token === null) window.localStorage.removeItem(SESSION_TOKEN_KEY);
    else window.localStorage.setItem(SESSION_TOKEN_KEY, token);
  } catch {
    /* localStorage unavailable — memory-only token */
  }
}

function buildUrl(path: string, query?: object): string {
  const url = new URL(path.startsWith("http") ? path : BASE_URL + path);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === "") continue;
      if (Array.isArray(value)) {
        url.searchParams.delete(key);
        for (const v of value) url.searchParams.append(key, String(v));
      } else {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.toString();
}

async function handle<T>(res: Response, path: string): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body?.detail ?? body?.error ?? JSON.stringify(body);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(
      typeof detail === "string" ? detail : JSON.stringify(detail),
      res.status,
      path
    );
  }
  return (await res.json()) as T;
}

async function requestSessionToken(): Promise<string> {
  let res: Response;
  try {
    res = await fetch(BASE_URL + SESSION_PATH, {
      method: "POST",
      cache: "no-store",
    });
  } catch (err) {
    throw new ApiError(
      `backend unreachable at ${BASE_URL}: ${
        err instanceof Error ? err.message : String(err)
      }`,
      0,
      SESSION_PATH
    );
  }
  const body = await handle<{ token: string; expires_in: number }>(
    res,
    SESSION_PATH
  );
  if (!body || typeof body.token !== "string" || body.token === "") {
    throw new ApiError("session response missing token", res.status, SESSION_PATH);
  }
  storeToken(body.token);
  return body.token;
}

async function fetchWithAuth(
  path: string,
  url: string,
  init: RequestInit,
  retryOnUnauthorized = true
): Promise<Response> {
  const headers = new Headers(init.headers);
  const isSessionRequest = path === SESSION_PATH;
  if (!isSessionRequest) {
    const token = loadToken();
    if (token) headers.set("X-Session-Token", token);
  }
  const res = await fetch(url, { ...init, headers });
  if (
    res.status === 401 &&
    retryOnUnauthorized &&
    !isSessionRequest &&
    isBrowser()
  ) {
    storeToken(null);
    await requestSessionToken();
    return fetchWithAuth(path, url, init, false);
  }
  return res;
}

export async function apiGet<T>(
  path: string,
  query?: object
): Promise<T> {
  const url = buildUrl(path, query);
  let res: Response;
  try {
    res = await fetchWithAuth(path, url, { cache: "no-store" });
  } catch (err) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(
      `backend unreachable at ${BASE_URL}: ${
        err instanceof Error ? err.message : String(err)
      }`,
      0,
      path
    );
  }
  return handle<T>(res, path);
}

export async function apiPost<T>(
  path: string,
  body?: unknown,
  query?: object
): Promise<T> {
  const url = buildUrl(path, query);
  let res: Response;
  try {
    res = await fetchWithAuth(path, url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
  } catch (err) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(
      `backend unreachable at ${BASE_URL}: ${
        err instanceof Error ? err.message : String(err)
      }`,
      0,
      path
    );
  }
  return handle<T>(res, path);
}

export const api = {
  get: apiGet,
  post: apiPost,
  base: BASE_URL,
};
