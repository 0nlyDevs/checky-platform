import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import vm from "node:vm";

import { MOVED } from "../next.config.ts";

// The service worker's copy of the table, run as the browser would (no network needed).
const source = readFileSync(new URL("../public/sw.js", import.meta.url), "utf8");
const sandbox: Record<string, unknown> = {
  self: { location: { href: "https://checky.test/sw.js?v=1" }, addEventListener() {} },
  URL,
  URLSearchParams,
};
vm.runInNewContext(`${source}\nthis.__MOVED = MOVED; this.__moved = moved;`, sandbox);
const swMoved = JSON.parse(JSON.stringify(sandbox.__MOVED)) as [string, string][];
const moved = sandbox.__moved as (url: URL) => string | null;
const go = (path: string) => moved(new URL(path, "https://checky.test"));

test("the service worker redirects exactly what next.config.ts redirects", () => {
  assert.deepEqual(swMoved, MOVED);
});

test("old French addresses go to the English ones, with sub-paths, query and fragment", () => {
  const W = "00000000-0000-0000-0000-00000000000a";
  const I = "00000000-0000-0000-0000-00000000000b";
  const cases: [string, string][] = [
    ["/accueil", "/home"],
    ["/verifies", "/verdicts"],
    ["/verifies/", "/verdicts"],
    [`/verifies/${I}?ref=sms`, `/verdicts/${I}?ref=sms`],
    ["/signaler", "/report"],
    ["/suivi/tok_123", "/track/tok_123"],
    ["/officiel", "/official"],
    ["/sceau/c1", "/seal/c1"],
    ["/reponse/tok", "/reply/tok"],
    ["/flashs", "/flashes"],
    ["/flashs?radio=abc&lang=mg", "/flashes?radio=abc&lang=mg"],
    ["/flashs/audio?id=1", "/flashes/audio?id=1"],
    ["/connexion?suite=%2Fw%2F1", "/sign-in?suite=%2Fw%2F1"],
    ["/inscription", "/sign-up"],
    [`/w/${W}/affirmations`, `/w/${W}/claims`],
    [`/w/${W}/affirmations?vue=tableau`, `/w/${W}/claims?vue=tableau`],
    [`/w/${W}/affirmations/${I}`, `/w/${W}/claims/${I}`],
    // The poster rule comes before the general one, or the poster would 404.
    [`/w/${W}/affirmations/${I}/affiche`, `/w/${W}/claims/${I}/poster`],
    [`/w/${W}/analyser`, `/w/${W}/analyze`],
    [`/w/${W}/annuaire`, `/w/${W}/directory`],
    [`/w/${W}/chiffres`, `/w/${W}/figures`],
    [`/w/${W}/membres`, `/w/${W}/settings#equipe`],
    [`/w/${W}/parametres`, `/w/${W}/settings`],
    [`/w/${W}/registre`, `/w/${W}/registry`],
    [`/w/${W}/rubrique`, `/w/${W}/beat`],
    [`/w/${W}/transcriptions`, `/w/${W}/sources?vue=enregistrements`],
    [`/w/${W}/veille?type=clip`, `/w/${W}/watch?type=clip`],
    [`/w/${W}/verifier?lien=https%3A%2F%2Fx.test%2Fa`, `/w/${W}/verify?lien=https%3A%2F%2Fx.test%2Fa`],
  ];
  for (const [from, to] of cases) assert.equal(go(from), `https://checky.test${to}`, from);
});

test("English addresses and unrelated paths are left alone", () => {
  for (const path of ["/home", "/verdicts", "/verdicts/abc", "/report", "/track/t", "/seal/c1", "/sign-in", "/scanner", "/v/145", "/checky", "/", "/accueilx", "/w/w1/claims", "/w/w1/affirmationsx", "/w/w1/sources", "/w/w1/settings"]) {
    assert.equal(go(path), null, path);
  }
});

/** Every page and route handler of the app as a path with its parameters named `:`. */
function appRoutes(dir: string, base = ""): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      const segment = /^\(.*\)$/.test(entry.name) ? "" : "/" + entry.name.replace(/^\[.*\]$/, ":");
      out.push(...appRoutes(join(dir, entry.name), base + segment));
    } else if (/^(page|route)\.tsx?$/.test(entry.name)) out.push(base || "/");
  }
  return out;
}

test("every redirect lands on a page that exists, and not on another redirect", () => {
  const routes = appRoutes(new URL("../app", import.meta.url).pathname);
  assert.ok(routes.includes("/verdicts") && routes.includes("/w/:/claims"));
  for (const [, to] of MOVED) {
    const target = to.replace(/[?#].*$/, "").replace(/\/:path\*$/, "").replace(/\/:\w+/g, "/:");
    assert.ok(routes.some((route) => route === target || route.startsWith(`${target}/`)), `no page at ${to}`);
    const here = new URL(to.replace(/:ws/g, "w1").replace(/:id/g, "i1").replace(/\/:path\*$/, ""), "https://checky.test");
    assert.equal(moved(here), null, `${to} would redirect again`);
  }
  // The old folders are gone: nothing there to shadow a redirect.
  for (const old of ["accueil", "verifies", "signaler", "suivi", "officiel", "sceau", "reponse", "flashs", "connexion", "inscription"]) {
    assert.ok(!routes.some((route) => route === `/${old}` || route.startsWith(`/${old}/`)), old);
  }
  assert.ok(existsSync(new URL("../public/sw.js", import.meta.url)));
});
