import { API_URL, ApiError } from "@/lib/api";

/** The public API (no account): published verdicts, matches, tips and their follow-up. */
export async function publicApi<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_URL}/api/v1/public${path}`, {
    ...init,
    headers: { ...init.headers, ...(init.body ? { "Content-Type": "application/json" } : {}) },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, body?.error?.code ?? "error", body?.error?.message ?? res.statusText);
  }
  return res.json() as Promise<T>;
}

export type Newsroom = { slug: string; name: string };
export type PublicVerdict = {
  id: string;
  ref: string | null;
  title: string;
  verdict: "true" | "misleading" | "false" | "unverifiable";
  reason: string | null;
  post: string | null;
  sources: string[];
  origin: string | null;
  first_seen_at: string | null;
  published_at: string;
  newsroom: Newsroom;
};
export type TipStatus = {
  ref: string | null;
  title: string;
  status: "to_check" | "in_progress" | "verified" | "published";
  received_at: string;
  newsroom: Newsroom;
  verdict: PublicVerdict | null;
};

// Tips sent from this device, so a visitor finds their follow-up links again.
const MINE = "fanilo:tips";
export function rememberTip(tip: { token: string; ref: string; title: string }) {
  try {
    const all = JSON.parse(localStorage.getItem(MINE) ?? "[]") as (typeof tip)[];
    localStorage.setItem(MINE, JSON.stringify([tip, ...all.filter((t) => t.token !== tip.token)].slice(0, 20)));
  } catch {
    // Without storage the visitor keeps the link shown on screen.
  }
}
export function myTips(): { token: string; ref: string; title: string }[] {
  try {
    return JSON.parse(localStorage.getItem(MINE) ?? "[]");
  } catch {
    return [];
  }
}
