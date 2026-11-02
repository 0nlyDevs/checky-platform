import { FolderOpen, Library, ScanSearch, Settings, Users, type LucideIcon } from "lucide-react";
import { t } from "@/lib/i18n/fr";

export type NavItem = { label: string; icon: LucideIcon; path?: string };

// `path` is relative to /w/[ws]. Three places a journalist works in every day: check what came in,
// follow the dossiers, find a source. Recordings live under Sources (they are sources), and the
// newsroom's own pages sit in WORKSPACE_NAV.
export const NAV: NavItem[] = [
  { label: t.nav.check, icon: ScanSearch, path: "verifier" },
  { label: t.nav.claims, icon: FolderOpen, path: "affirmations" },
  { label: t.nav.sources, icon: Library, path: "sources" },
];

export const WORKSPACE_NAV: NavItem[] = [
  { label: t.nav.members, icon: Users, path: "membres" },
  { label: t.nav.settings, icon: Settings, path: "parametres" },
];
