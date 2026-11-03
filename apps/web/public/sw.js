/* Checky's service worker: the correspondent's desk and the seal checks keep working with no network.
 *
 * Registered by components/pwa/service-worker.tsx in production builds only (or with
 * NEXT_PUBLIC_SW=1), as /sw.js?v=<build>&api=<API origin>. What it keeps:
 *   shell   (per build) the public seal pages (/scanner, /seal/_, /verdicts/_, /verdicts, /official),
 *           the desk pages the app asks it to warm, and the JS/CSS/fonts those pages load
 *   static  /_next/static/* (hashed, immutable): cache first
 *   pages   every page opened: network first, the saved copy offline
 *   data    the API reads a correspondent needs offline (dossiers, Ma rubrique, Annuaire, Chiffres,
 *           the registry, members, the issuers' keys, published verdicts): network first, the saved
 *           copy offline, marked `X-Checky-Cached-At`
 * Never kept: anything that is not a GET, Next's own /api/* routes (auth, token, session), RSC
 * payloads, and API routes outside the list below. Signing out clears `pages` and `data`.
 */
const params = new URL(self.location.href).searchParams;
const VERSION = params.get("v") || "0";
const API = (params.get("api") || "").replace(/\/$/, "");
const SHELL = `checky-shell-${VERSION}`;
const STATIC = `checky-static-${VERSION}`;
const PAGES = "checky-pages";
const DATA = "checky-data";
const KEEP = [SHELL, STATIC, PAGES, DATA];

// Public pages that must open with no network; `_` stands for any id (the page reads its address).
const PRECACHE = ["/scanner", "/seal/_", "/verdicts/_", "/verdicts", "/official"];
const ASSETS = ["/manifest.webmanifest", "/logo.svg", "/icon.svg", "/icons/icon-192.png"];

// API reads kept for offline use (paths after /api/v1).
const DATA_ROUTES = [
  /^\/me$/,
  /^\/workspaces\/[^/]+$/,
  /^\/workspaces\/[^/]+\/(items|sources|rubrique|alerts|contacts|figures|documents|registry|members|verification|me\/prefs|veille|meteo|antenne|activity)(\/|$)/,
  /^\/public\/(seal-keys|verdicts|registry|sceau|newsrooms|countries|flashs)(\/|$)/,
];
// Pages never kept: signing in and out, invitations.
const NO_PAGE = /^\/(sign-in|sign-up|invitation|api)(\/|$)/;

// French page paths before the English ones. The same table as MOVED in next.config.ts, which
// redirects them online (lib/moved-paths.test.ts keeps the two identical): an old QR, bookmark or
// SMS link opened with no network goes to the new address, whose cached copy then opens.
const MOVED = [
  ["/accueil", "/home"],
  ["/verifies/:path*", "/verdicts/:path*"],
  ["/signaler", "/report"],
  ["/suivi/:path*", "/track/:path*"],
  ["/officiel", "/official"],
  ["/sceau/:path*", "/seal/:path*"],
  ["/reponse/:path*", "/reply/:path*"],
  ["/flashs/:path*", "/flashes/:path*"],
  ["/connexion", "/sign-in"],
  ["/inscription", "/sign-up"],
  ["/w/:ws/affirmations/:id/affiche", "/w/:ws/claims/:id/poster"],
  ["/w/:ws/affirmations/:path*", "/w/:ws/claims/:path*"],
  ["/w/:ws/analyser", "/w/:ws/analyze"],
  ["/w/:ws/annuaire", "/w/:ws/directory"],
  ["/w/:ws/chiffres", "/w/:ws/figures"],
  ["/w/:ws/membres", "/w/:ws/settings#equipe"],
  ["/w/:ws/parametres", "/w/:ws/settings"],
  ["/w/:ws/registre", "/w/:ws/registry"],
  ["/w/:ws/rubrique", "/w/:ws/beat"],
  ["/w/:ws/transcriptions", "/w/:ws/sources?vue=enregistrements"],
  ["/w/:ws/veille", "/w/:ws/watch"],
  ["/w/:ws/verifier", "/w/:ws/verify"],
];

/** The values a MOVED pattern captures from a path (`:name` one segment, `:path*` the rest), or null. */
function capture(pattern, pathname) {
  const names = [];
  const source = pattern
    .split("/")
    .slice(1)
    .map((part) => {
      if (part === ":path*") {
        names.push("path");
        return "(?:/(.*))?";
      }
      if (part.startsWith(":")) {
        names.push(part.slice(1));
        return "/([^/]+)";
      }
      return "/" + part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    })
    .join("");
  const match = new RegExp(`^${source}$`).exec(pathname);
  if (!match) return null;
  return Object.fromEntries(names.map((name, i) => [name, match[i + 1] || ""]));
}

/** The English address of an old French page address (query kept), or null. */
function moved(url) {
  for (const [from, to] of MOVED) {
    const values = capture(from, url.pathname);
    if (!values) continue;
    const target = to.replace(/\/:(\w+)\*?/g, (_, name) => (values[name] ? `/${values[name]}` : ""));
    const next = new URL(target, url.origin);
    for (const [key, value] of url.searchParams) if (!next.searchParams.has(key)) next.searchParams.append(key, value);
    return next.href;
  }
  return null;
}

const OFFLINE_HTML = `<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Hors connexion · Checky</title>
<style>body{font:18px/1.5 system-ui,sans-serif;margin:0;padding:48px 16px;background:#f3f2ee;color:#0a0a0b}main{max-width:36rem;margin:auto}a{color:inherit;font-weight:700}@media (prefers-color-scheme:dark){body{background:#0a0a0b;color:#f3f2ee}}</style></head>
<body><main><h1>Hors connexion</h1><p>Cette page n'a pas encore été ouverte sur cet appareil. Elle s'ouvrira au retour du réseau.</p><p lang="en">Offline: this page was not opened on this device yet.</p>
<p><a href="/scanner">Scanner un sceau (marche sans réseau)</a></p><p><a href="javascript:history.back()">Retour</a></p></main></body></html>`;

const isRsc = (request, url) => request.headers.get("RSC") === "1" || url.searchParams.has("_rsc");

/** A copy of a response with the moment it was saved (and only the headers a page reads). */
async function stamped(response) {
  const headers = new Headers();
  for (const name of ["content-type", "cache-control"]) {
    const value = response.headers.get(name);
    if (value) headers.set(name, value);
  }
  headers.set("x-checky-cached-at", new Date().toISOString());
  return new Response(await response.blob(), { status: response.status, statusText: response.statusText, headers });
}

/** Saves a page and every /_next/static file its HTML names (scripts, styles, fonts). */
async function keepPage(cacheName, url) {
  const response = await fetch(url, { credentials: "same-origin" });
  if (!response.ok || response.redirected) return;
  const html = await response.clone().text();
  await (await caches.open(cacheName)).put(url, response);
  const assets = new Set(html.match(/\/_next\/static\/[^"'\s<>\\)]+/g) || []);
  const statics = await caches.open(STATIC);
  await Promise.all(
    [...assets].map(async (asset) => {
      if (await statics.match(asset)) return;
      const res = await fetch(asset).catch(() => null);
      if (res && res.ok) await statics.put(asset, res);
    }),
  );
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      await Promise.all(PRECACHE.map((page) => keepPage(SHELL, page).catch(() => null)));
      const shell = await caches.open(SHELL);
      await Promise.all(ASSETS.map((asset) => shell.add(asset).catch(() => null)));
      await self.skipWaiting();
    })(),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      for (const name of await caches.keys()) if (name.startsWith("checky-") && !KEEP.includes(name)) await caches.delete(name);
      // Pages saved under an old French path are never served again: the address redirects.
      const pages = await caches.open(PAGES);
      for (const request of await pages.keys()) if (moved(new URL(request.url))) await pages.delete(request);
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("message", (event) => {
  const data = event.data || {};
  if (data.type === "warm" && Array.isArray(data.pages)) {
    // Desk pages the app wants openable offline (same origin only).
    const pages = data.pages.filter((p) => typeof p === "string" && p.startsWith("/") && !NO_PAGE.test(p));
    event.waitUntil(Promise.all(pages.map((page) => keepPage(PAGES, page).catch(() => null))));
  } else if (data.type === "clear-private") {
    event.waitUntil(Promise.all([caches.delete(PAGES), caches.delete(DATA)]));
  }
});

async function cacheFirst(request, cacheName) {
  const hit = await caches.match(request);
  if (hit) return hit;
  const response = await fetch(request);
  if (response.ok) (await caches.open(cacheName)).put(request, response.clone());
  return response;
}

async function page(request, url) {
  const renamed = moved(url);
  if (renamed) return Response.redirect(renamed, 308);
  try {
    const response = await fetch(request);
    if (response.ok && !response.redirected && response.type === "basic" && !NO_PAGE.test(url.pathname)) {
      (await caches.open(PAGES)).put(url.pathname + url.search, response.clone());
    }
    return response;
  } catch {
    const key = url.pathname + url.search;
    const hit = (await caches.match(key)) || (await caches.match(url.pathname, { ignoreSearch: true }));
    if (hit) return hit;
    // A seal page opened from a QR: the shared copy reads the id from the address.
    const shared = url.pathname.startsWith("/seal/") ? "/seal/_" : /^\/verdicts\/[^/]+$/.test(url.pathname) ? "/verdicts/_" : null;
    if (shared) {
      const copy = await caches.match(shared);
      if (copy) return copy;
    }
    return new Response(OFFLINE_HTML, { status: 503, headers: { "content-type": "text/html; charset=utf-8" } });
  }
}

async function data(request) {
  const path = new URL(request.url).pathname.slice("/api/v1".length);
  // Private answers are keyed by the signed-in user, not merely by URL. The cache key has no
  // bearer token; an offline request uses the last user id saved by the app on this device.
  const privateRead = !path.startsWith("/public/");
  let scope = "public";
  if (privateRead) {
    const auth = request.headers.get("authorization") || "";
    if (auth.startsWith("Bearer ")) {
      try {
        const packed = auth.slice(7).split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
        scope = JSON.parse(atob(packed)).sub || "";
      } catch { scope = ""; }
    } else scope = request.headers.get("x-checky-cache-user") || "";
  }
  const key = new URL(request.url);
  key.searchParams.set("__checky_scope", scope);
  try {
    const response = await fetch(request);
    if (response.ok && scope) (await caches.open(DATA)).put(key.href, await stamped(response.clone()));
    return response;
  } catch {
    const hit = scope && await caches.match(key.href);
    if (hit) return hit;
    return new Response(JSON.stringify({ error: { code: "offline", message: "Offline, and nothing saved on this device for this request" } }), {
      status: 503,
      headers: { "content-type": "application/json", "x-checky-offline": "1" },
    });
  }
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);

  if (url.origin === self.location.origin) {
    if (url.pathname.startsWith("/api/") || url.pathname === "/sw.js") return;
    if (url.pathname.startsWith("/_next/static/")) return event.respondWith(cacheFirst(request, STATIC));
    if (url.pathname.startsWith("/_next/")) return;
    if (isRsc(request, url)) {
      // A client-side move offline: no payload, so Next opens the page in full (the cached copy).
      return event.respondWith(fetch(request).catch(() => new Response("", { status: 503 })));
    }
    if (request.mode === "navigate") return event.respondWith(page(request, url));
    if (ASSETS.includes(url.pathname) || url.pathname.startsWith("/icons/")) return event.respondWith(cacheFirst(request, SHELL));
    return;
  }

  if (API && url.origin === new URL(API).origin && url.pathname.startsWith("/api/v1/")) {
    const path = url.pathname.slice("/api/v1".length);
    if (DATA_ROUTES.some((route) => route.test(path))) event.respondWith(data(request));
  }
});
