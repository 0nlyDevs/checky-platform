// Checky colour tokens, the single source of truth for the pairs the contrast test checks.
// globals.css repeats these values under the same names; tokens.test.ts fails when a text/background
// pair drops under 4.5:1. rgba tokens (border, rule, input) are listed in the CSS only.

export type TokenName =
  | "background"
  | "foreground"
  | "card"
  | "raised"
  | "active"
  | "muted-foreground"
  | "primary"
  | "primary-foreground"
  | "primary-hover"
  | "nav"
  | "nav-foreground"
  | "nav-hover"
  | "nav-active"
  | "nav-active-foreground"
  | "tag-inverted"
  | "tag-inverted-foreground"
  | "toast"
  | "toast-foreground"
  | "verdict-true"
  | "verdict-true-on"
  | "verdict-true-soft"
  | "verdict-true-ink"
  | "verdict-misleading"
  | "verdict-misleading-on"
  | "verdict-misleading-soft"
  | "verdict-misleading-ink"
  | "verdict-false"
  | "verdict-false-on"
  | "verdict-false-soft"
  | "verdict-false-ink"
  | "verdict-unverifiable"
  | "verdict-unverifiable-on"
  | "verdict-unverifiable-soft"
  | "verdict-unverifiable-ink";

export const light: Record<TokenName, string> = {
  background: "#f3f2ee",
  foreground: "#0a0a0b",
  card: "#fbfaf7",
  raised: "#e9e8e2",
  active: "#e2e1da",
  "muted-foreground": "#55544e",
  primary: "#0a0a0b",
  "primary-foreground": "#f3f2ee",
  "primary-hover": "#1f1f22",
  nav: "#0a0a0b",
  "nav-foreground": "#b9b8b2",
  "nav-hover": "#1f1f22",
  "nav-active": "#f3f2ee",
  "nav-active-foreground": "#0a0a0b",
  "tag-inverted": "#0a0a0b",
  "tag-inverted-foreground": "#f3f2ee",
  toast: "#0a0a0b",
  "toast-foreground": "#f3f2ee",
  "verdict-true": "#0b6b3a",
  "verdict-true-on": "#ffffff",
  "verdict-true-soft": "#e1f3e8",
  "verdict-true-ink": "#0b6b3a",
  "verdict-misleading": "#8a5700",
  "verdict-misleading-on": "#ffffff",
  "verdict-misleading-soft": "#f9ecd2",
  "verdict-misleading-ink": "#8a5700",
  "verdict-false": "#b3231a",
  "verdict-false-on": "#ffffff",
  "verdict-false-soft": "#fbe3e0",
  "verdict-false-ink": "#b3231a",
  "verdict-unverifiable": "#1d58c4",
  "verdict-unverifiable-on": "#ffffff",
  "verdict-unverifiable-soft": "#e0eafb",
  "verdict-unverifiable-ink": "#1d58c4",
};

export const dark: Record<TokenName, string> = {
  background: "#0a0a0b",
  foreground: "#f3f2ee",
  card: "#111113",
  raised: "#19191c",
  active: "#232327",
  "muted-foreground": "#a6a5a0",
  primary: "#f3f2ee",
  "primary-foreground": "#0a0a0b",
  // The primary is a paper fill in dark: its hover is a slightly darker paper, the label stays ink.
  "primary-hover": "#e2e1da",
  nav: "#1c1c1f",
  "nav-foreground": "#b4b3ad",
  "nav-hover": "#2a2a2e",
  "nav-active": "#f3f2ee",
  // The pill is paper in both themes: its label is the fixed ink, never the theme text (1:1 in dark).
  "nav-active-foreground": "#0a0a0b",
  "tag-inverted": "#f3f2ee",
  "tag-inverted-foreground": "#0a0a0b",
  toast: "#f3f2ee",
  "toast-foreground": "#0a0a0b",
  "verdict-true": "#3ddc84",
  "verdict-true-on": "#0a0a0b",
  "verdict-true-soft": "#0f2219",
  "verdict-true-ink": "#3ddc84",
  "verdict-misleading": "#ffb224",
  "verdict-misleading-on": "#0a0a0b",
  "verdict-misleading-soft": "#29200c",
  "verdict-misleading-ink": "#ffb224",
  "verdict-false": "#ff6a5f",
  "verdict-false-on": "#0a0a0b",
  "verdict-false-soft": "#2a1311",
  "verdict-false-ink": "#ff6a5f",
  "verdict-unverifiable": "#6aa8ff",
  "verdict-unverifiable-on": "#0a0a0b",
  "verdict-unverifiable-soft": "#101a2b",
  "verdict-unverifiable-ink": "#6aa8ff",
};

const VERDICTS = ["true", "misleading", "false", "unverifiable"] as const;

export const PAIRS: ReadonlyArray<[fg: TokenName, bg: TokenName]> = [
  ["foreground", "background"],
  ["foreground", "card"],
  ["foreground", "raised"],
  ["foreground", "active"],
  ["muted-foreground", "background"],
  ["muted-foreground", "card"],
  ["muted-foreground", "raised"],
  ["muted-foreground", "active"],
  ["primary-foreground", "primary"],
  ["primary-foreground", "primary-hover"],
  ["nav-foreground", "nav"],
  ["nav-foreground", "nav-hover"],
  ["nav-active-foreground", "nav-active"],
  ["tag-inverted-foreground", "tag-inverted"],
  ["toast-foreground", "toast"],
  ...VERDICTS.flatMap((v): Array<[TokenName, TokenName]> => [
    [`verdict-${v}-ink`, `verdict-${v}-soft`],
    [`verdict-${v}-ink`, "background"],
    [`verdict-${v}-ink`, "card"],
    [`verdict-${v}-on`, `verdict-${v}`],
  ]),
];

function channel(v: number): number {
  const c = v / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const m = /^#([0-9a-f]{6})$/i.exec(hex);
  if (!m) throw new Error(`contrast() takes #rrggbb, got ${hex}`);
  const n = parseInt(m[1], 16);
  return 0.2126 * channel((n >> 16) & 255) + 0.7152 * channel((n >> 8) & 255) + 0.0722 * channel(n & 255);
}

/** WCAG 2.1 contrast ratio between two #rrggbb colours. */
export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
