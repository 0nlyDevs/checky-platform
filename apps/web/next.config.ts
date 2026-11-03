import type { NextConfig } from "next";

// French page paths before the English ones: printed QR codes, SMS, shares and e-mailed links
// still carry them. Sub-paths and the query string follow; the browser keeps the `#…` fragment.
// First match wins. public/sw.js holds the same table for offline use (lib/moved-paths.test.ts
// fails when the two differ).
export const MOVED: [string, string][] = [
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

const nextConfig: NextConfig = {
  // Names the service worker's caches (public/sw.js): a new build replaces the old shell.
  env: { NEXT_PUBLIC_BUILD_ID: process.env.NEXT_PUBLIC_BUILD_ID ?? Date.now().toString(36) },
  async redirects() {
    return MOVED.map(([source, destination]) => ({ source, destination, permanent: true }));
  },
  async headers() {
    return [
      {
        source: "/sw.js",
        headers: [
          { key: "Content-Type", value: "application/javascript; charset=utf-8" },
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
        ],
      },
    ];
  },
  transpilePackages: ["@checky/shared"],
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
