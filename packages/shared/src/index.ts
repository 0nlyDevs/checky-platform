// Shared between web (and later mobile): generated API types, constants, i18n strings.
export const ROLES = ["admin", "editor", "journalist"] as const;
export type Role = (typeof ROLES)[number];

export const VERDICTS = ["true", "misleading", "false", "unverifiable"] as const;
export type Verdict = (typeof VERDICTS)[number];
