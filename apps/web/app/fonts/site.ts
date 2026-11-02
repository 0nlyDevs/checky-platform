import localFont from "next/font/local";

// Public pages only (landing, sign-in, sign-up), self-hosted and not modified.
// Anton (Vernon Adams, SIL OFL 1.1): headlines. Special Elite (Astigmatic, Apache 2.0): the case file's typed labels.
export const anton = localFont({
  variable: "--font-anton",
  display: "swap",
  src: [{ path: "./Anton-400.woff2", weight: "400" }],
});

export const specialElite = localFont({
  variable: "--font-typed",
  display: "swap",
  src: [{ path: "./SpecialElite-400.woff2", weight: "400" }],
});
