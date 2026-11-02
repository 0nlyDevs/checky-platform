import { authClient } from "@/lib/auth-client";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

let cached: { token: string; exp: number } | null = null;

/** Short-lived JWT for FastAPI, refreshed a minute before it expires. */
export async function getApiToken(): Promise<string> {
  const now = Date.now() / 1000;
  if (cached && cached.exp - 60 > now) return cached.token;
  const { data, error } = await authClient.token();
  if (error || !data) throw new Error("Not signed in");
  const exp = JSON.parse(atob(data.token.split(".")[1])).exp as number;
  cached = { token: data.token, exp };
  return data.token;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_URL}/api/v1${path}`, {
    ...init,
    headers: { ...init.headers, Authorization: `Bearer ${await getApiToken()}`, "Content-Type": "application/json" },
  });
  const body = await res.json();
  if (!res.ok) throw new Error(body?.error?.message ?? res.statusText);
  return body as T;
}
