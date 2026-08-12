import type { AuthResponse } from "./types";

const STORAGE_KEY = "sawtai_access_token";
let refreshPromise: Promise<string | null> | null = null;

export class ApiError extends Error {
  constructor(public status: number, message?: string) {
    super(message ?? `Request failed: ${status}`);
  }
}

export function getAccessToken(): string | null {
  return typeof sessionStorage === "undefined" ? null : sessionStorage.getItem(STORAGE_KEY);
}

export function setAccessToken(token: string | null) {
  if (typeof sessionStorage === "undefined") return;
  if (token) sessionStorage.setItem(STORAGE_KEY, token);
  else sessionStorage.removeItem(STORAGE_KEY);
}

export function authHeaders(): HeadersInit {
  const token = getAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = fetch("/api/v1/auth/refresh", {
      method: "POST",
      credentials: "include",
    }).then(async (response) => {
      if (!response.ok) {
        setAccessToken(null);
        return null;
      }
      const result = await response.json() as AuthResponse;
      setAccessToken(result.access_token);
      return result.access_token;
    }).finally(() => { refreshPromise = null; });
  }
  return refreshPromise;
}

async function request(path: string, init: RequestInit = {}, retry = true): Promise<Response> {
  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers: { ...init.headers, ...authHeaders() },
  });
  if (response.status === 401 && retry && !path.startsWith("/api/v1/auth/")) {
    const token = await refreshAccessToken();
    if (token) return request(path, init, false);
  }
  if (!response.ok) {
    let detail: string | undefined;
    try {
      const payload = await response.json() as { detail?: string | { message?: string } };
      detail = typeof payload.detail === "string" ? payload.detail : payload.detail?.message;
    } catch { detail = undefined; }
    throw new ApiError(response.status, detail);
  }
  return response;
}

export async function login(email: string, password: string): Promise<AuthResponse> {
  const response = await request("/api/v1/auth/token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, tenant_code: "shj-demo" }),
  }, false);
  const result = await response.json() as AuthResponse;
  setAccessToken(result.access_token);
  return result;
}

export async function restoreSession(): Promise<AuthResponse | null> {
  try {
    const response = await fetch("/api/v1/auth/refresh", { method: "POST", credentials: "include" });
    if (!response.ok) return null;
    const result = await response.json() as AuthResponse;
    setAccessToken(result.access_token);
    return result;
  } catch {
    return null;
  }
}

export async function logout(): Promise<void> {
  try { await request("/api/v1/auth/logout", { method: "POST" }, false); } finally { setAccessToken(null); }
}

export async function getJson<T>(path: string): Promise<T> {
  const response = await request(path);
  return response.json() as Promise<T>;
}

export async function postJson(path: string, body: unknown): Promise<Response> {
  return request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function postForm(path: string, body: FormData): Promise<Response> {
  return request(path, { method: "POST", body });
}

export async function deleteJson(path: string): Promise<Response> {
  return request(path, { method: "DELETE" });
}

export async function patchJson<T>(path: string, body: unknown): Promise<T> {
  const response = await request(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return response.json() as Promise<T>;
}
