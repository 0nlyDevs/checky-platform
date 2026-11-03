import assert from "node:assert/strict";
import { readdirSync } from "node:fs";
import * as nodeModule from "node:module";
import { test } from "node:test";

// The dictionaries import `@/lib/…` and extensionless paths, as Next resolves them; teach Node the same.
// (`registerHooks` is in Node ≥ 22.15; the installed @types/node predates it.)
type Next = (specifier: string, context: object) => unknown;
const { registerHooks } = nodeModule as unknown as {
  registerHooks: (hooks: { resolve: (specifier: string, context: object, next: Next) => unknown }) => void;
};
const web = new URL("../", import.meta.url);
registerHooks({
  resolve(specifier, context, next) {
    let spec = specifier.startsWith("@/") ? new URL(specifier.slice(2), web).href : specifier;
    if ((spec.startsWith(".") || spec.startsWith("file:")) && !/\.[cm]?[jt]sx?$/.test(spec)) spec += ".ts";
    return next(spec, context);
  },
});

type Tree = Record<string, unknown>;
const plain = (v: unknown): v is Tree => !!v && typeof v === "object" && !Array.isArray(v);

/** Keys printed on the verdict card in the card's own language: a Malagasy screen still prints a French card in French. */
const SAME_IN_EVERY_LANGUAGE = ["card.words"];

/** Every French leaf (string, list or function) that the translation does not give, and every function whose arity differs. */
function gaps(fr: Tree, other: Tree | undefined, path = ""): string[] {
  const out: string[] = [];
  for (const [key, value] of Object.entries(fr)) {
    const at = path ? `${path}.${key}` : key;
    if (SAME_IN_EVERY_LANGUAGE.includes(at)) continue;
    const mine = other?.[key];
    if (plain(value)) out.push(...gaps(value, plain(mine) ? mine : undefined, at));
    else if (mine === undefined) out.push(at);
    else if (typeof value === "function" && (typeof mine !== "function" || mine.length !== value.length)) out.push(`${at} (signature)`);
    else if (typeof value !== "function" && typeof mine !== typeof value) out.push(`${at} (type)`);
  }
  return out;
}

async function pair(name: string) {
  const fr = (await import(new URL(`./i18n/${name}.ts`, import.meta.url).href)) as Record<string, Tree>;
  const mg = (await import(new URL(`./i18n/${name.replace(/^fr/, "mg")}.ts`, import.meta.url).href)) as Record<string, Tree>;
  return { fr, mg };
}

test("the Malagasy dictionary gives every French key", async () => {
  const { fr, mg } = await pair("fr");
  assert.deepEqual(gaps(fr.fr, mg.mg), []);
});

// Parts the components import directly (palette, publication, resources) are checked file by file too.
for (const file of readdirSync(new URL("./i18n/fr/", import.meta.url)).filter((f) => f.endsWith(".ts"))) {
  const name = file.replace(/\.ts$/, "");
  test(`mg/${file} gives every key of fr/${file}`, async () => {
    const { fr, mg } = await pair(`fr/${name}`);
    for (const [key, value] of Object.entries(fr)) {
      if (plain(value)) assert.deepEqual(gaps(value, mg[key]), [], `export ${key}`);
    }
  });
}
