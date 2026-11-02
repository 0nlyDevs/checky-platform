// Shared between web (and later mobile): generated API types, constants, i18n strings.
import type { components, paths } from "./api";

export type { components, paths };

type Schemas = components["schemas"];
export type Me = Schemas["MeOut"];
export type Membership = Schemas["MembershipOut"];
export type Workspace = Schemas["WorkspaceOut"];
export type Item = Schemas["ItemOut"];
export type ItemPage = Schemas["ItemPage"];
export type ItemIn = Schemas["ItemIn"];
export type ItemPatch = Schemas["ItemPatch"];
export type Comment = Schemas["CommentOut"];
export type Activity = Schemas["ActivityOut"];
export type AiCompleteIn = Schemas["CompleteIn"];
export type AiCompletion = Schemas["CompleteOut"];

// The desk (admin, editor, journalist), a veilleur (reports what was heard on a radio) and an
// issuer (an institution that registers and seals its own communiqués).
export const ROLES = ["admin", "editor", "journalist", "veilleur", "issuer"] as const;
export type Role = (typeof ROLES)[number];

export const STATUSES = ["to_check", "in_progress", "verified", "published"] as const;
export type Status = (typeof STATUSES)[number];

export const VERDICTS = ["true", "misleading", "false", "unverifiable"] as const;
export type Verdict = (typeof VERDICTS)[number];
