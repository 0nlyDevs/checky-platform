import { authClient } from "@/lib/auth-client";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

let cached: { token: string; exp: number } | null = null;

/** Short-lived JWT for FastAPI, refreshed a minute before it expires. */
export async function getApiToken(): Promise<string> {
  const now = Date.now() / 1000;
  if (cached && cached.exp - 60 > now) return cached.token;
  const { data, error } = await authClient.token();
  if (error || !data) throw new ApiError(401, "unauthorized", "Not signed in");
  const exp = JSON.parse(atob(data.token.split(".")[1])).exp as number;
  cached = { token: data.token, exp };
  return data.token;
}

export function clearApiToken() {
  cached = null;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_URL}/api/v1${path}`, {
    ...init,
    headers: {
      ...init.headers,
      Authorization: `Bearer ${await getApiToken()}`,
      ...(init.body ? { "Content-Type": "application/json" } : {}),
    },
  });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    throw new ApiError(res.status, body?.error?.code ?? "http_error", body?.error?.message ?? res.statusText);
  }
  return body as T;
}

/** SWR fetcher: the key is the API path. */
export const fetcher = <T,>(path: string) => api<T>(path);

/** A file the API makes (a PDF): fetched with the JWT, then saved under the name the API gives. */
export async function downloadFile(path: string, fallbackName: string): Promise<string> {
  const res = await fetch(`${API_URL}/api/v1${path}`, { headers: { Authorization: `Bearer ${await getApiToken()}` } });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, body?.error?.code ?? "http_error", body?.error?.message ?? res.statusText);
  }
  const name = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "")?.[1] ?? fallbackName;
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
  return name;
}
