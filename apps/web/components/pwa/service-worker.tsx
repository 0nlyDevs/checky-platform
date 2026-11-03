"use client";

import { useEffect } from "react";
import { API_URL } from "@/lib/api";

/** In production builds only (or with NEXT_PUBLIC_SW=1): a service worker would serve stale
 *  chunks to the dev server's hot reload. In dev, one left over from a production run is removed. */
const ENABLED = process.env.NODE_ENV === "production" || process.env.NEXT_PUBLIC_SW === "1";
const BUILD = process.env.NEXT_PUBLIC_BUILD_ID ?? "dev";

/** Registers public/sw.js (offline desk, seal checks with no network). Renders nothing. */
export function ServiceWorker() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    if (!ENABLED) {
      void navigator.serviceWorker.getRegistrations().then((all) => all.forEach((r) => void r.unregister()));
      return;
    }
    const url = `/sw.js?v=${encodeURIComponent(BUILD)}&api=${encodeURIComponent(new URL(API_URL).origin)}`;
    navigator.serviceWorker.register(url, { scope: "/" }).catch(() => {
      // no service worker: the pages still work online, and seal keys stay in localStorage
    });
  }, []);
  return null;
}

/** Tells the service worker to keep these pages (and their scripts) for offline use. */
export async function warmPages(pages: string[]) {
  if (!ENABLED || !("serviceWorker" in navigator)) return;
  const reg = await navigator.serviceWorker.ready.catch(() => null);
  reg?.active?.postMessage({ type: "warm", pages });
}

/** Signing out: the saved desk pages and API answers go. */
export async function clearPrivateCache() {
  try {
    if ("serviceWorker" in navigator) navigator.serviceWorker.controller?.postMessage({ type: "clear-private" });
    if ("caches" in window) await Promise.all([caches.delete("checky-pages"), caches.delete("checky-data")]);
  } catch {
    // nothing kept
  }
}
