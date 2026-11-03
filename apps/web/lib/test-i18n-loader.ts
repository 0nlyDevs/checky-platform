import * as nodeModule from "node:module";

// The Node test runner needs the same dictionary path resolution as Next.js.
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

export const loadTestMessages = async () => (await import("./i18n/live.ts")).DICTS;
