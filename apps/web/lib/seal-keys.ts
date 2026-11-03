"use client";

import { API_URL } from "@/lib/api";
import { CACHED_AT_HEADER } from "@/lib/offline";
import type { SealKeys } from "@/lib/seal";

/**
 * The issuers' public keys and the revoked ones, kept on the device so a seal is checked with no
 * network. Fetched fresh when online (the service worker also keeps the last answer); the last good
 * copy also lives in localStorage, so the check works where no service worker runs.
 */
const STORE = "checky:seal-keys";

export type KeysOnDevice = SealKeys & { at: string; fresh: boolean };

function stored(): KeysOnDevice | null {
  try {
    const raw = localStorage.getItem(STORE);
    if (!raw) return null;
    const kept = JSON.parse(raw) as SealKeys & { at: string };
    return Array.isArray(kept.keys) && Array.isArray(kept.revoked) ? { ...kept, fresh: false } : null;
  } catch {
    return null;
  }
}

export async function loadSealKeys(): Promise<KeysOnDevice | null> {
  try {
    const res = await fetch(`${API_URL}/api/v1/public/seal-keys`);
    if (res.ok) {
      const body = (await res.json()) as SealKeys;
      const cachedAt = res.headers.get(CACHED_AT_HEADER);
      const at = cachedAt ?? new Date().toISOString();
      if (!cachedAt) {
        try {
          localStorage.setItem(STORE, JSON.stringify({ keys: body.keys, revoked: body.revoked, at }));
        } catch {
          // the service worker's copy still holds them
        }
      }
      // The service worker's copy may be older than the one kept here.
      const kept = stored();
      if (cachedAt && kept && kept.at > cachedAt) return kept;
      return { keys: body.keys, revoked: body.revoked, at, fresh: !cachedAt };
    }
  } catch {
    // no network and no service worker: the copy kept here
  }
  return stored();
}
