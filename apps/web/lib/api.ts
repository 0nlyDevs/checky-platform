import { toast } from "sonner";
import { authClient } from "@/lib/auth-client";
import { t } from "@/lib/i18n/live";
import { isOffline, noteAnswer } from "@/lib/offline";

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
const OFFLINE_USER = "checky:offline-user";

function tokenSubject(token: string): string | null {
  try {
    const packed = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const claims = JSON.parse(atob(packed)) as { sub?: unknown };
    return typeof claims.sub === "string" && claims.sub ? claims.sub : null;
  } catch {
    return null;
  }
}

/** Short-lived JWT for FastAPI, refreshed a minute before it expires. */
export async function getApiToken(): Promise<string> {
  const now = Date.now() / 1000;
  if (cached && cached.exp - 60 > now) return cached.token;
  const { data, error } = await authClient.token();
  if (error || !data) throw new ApiError(401, "unauthorized", "Not signed in");
  const exp = JSON.parse(atob(data.token.split(".")[1])).exp as number;
  cached = { token: data.token, exp };
  const subject = tokenSubject(data.token);
  if (subject) localStorage.setItem(OFFLINE_USER, subject);
  return data.token;
}

export function clearApiToken() {
  cached = null;
  if (typeof localStorage !== "undefined") localStorage.removeItem(OFFLINE_USER);
}

/** The bearer header; offline (no way to refresh the token) the request goes without it, so the
 *  service worker can answer a read from what it saved. */
async function authorization(): Promise<Record<string, string>> {
  try {
    const token = await getApiToken();
    const subject = tokenSubject(token);
    return { Authorization: `Bearer ${token}`, ...(subject ? { "X-Checky-Cache-User": subject } : {}) };
  } catch (err) {
    if (isOffline()) {
      const subject = localStorage.getItem(OFFLINE_USER);
      return subject ? { "X-Checky-Cache-User": subject } : {};
    }
    throw err;
  }
}

/** Writes made offline are not sent (nothing is queued behind the journalist's back): one clear note. */
function refuseOffline(init: RequestInit) {
  const method = (init.method ?? "GET").toUpperCase();
  if (method === "GET" || method === "HEAD" || !isOffline()) return;
  toast(t.offline.writeBlocked, { id: "offline-write" });
  throw new ApiError(0, "offline", t.offline.writeBlocked);
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  refuseOffline(init);
  const res = await fetch(`${API_URL}/api/v1${path}`, {
    ...init,
    headers: {
      ...init.headers,
      ...(await authorization()),
      ...(init.body ? { "Content-Type": "application/json" } : {}),
    },
  });
  if (!init.method || init.method === "GET") noteAnswer(path, res);
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
