import { Library, ListChecks, ScanSearch, Search, Settings, Users, type LucideIcon } from "lucide-react";
import { t } from "@/lib/i18n/fr";

export type NavItem = { label: string; icon: LucideIcon; path?: string };

// `path` is relative to /w/[ws]. Four destinations a journalist uses every day; recordings live
// under Sources (they are sources), and the workspace's own pages sit in WORKSPACE_NAV.
export const NAV: NavItem[] = [
  { label: t.nav.claims, icon: ListChecks, path: "affirmations" },
  { label: t.nav.check, icon: Search, path: "verifier" },
  { label: t.nav.analyse, icon: ScanSearch, path: "analyser" },
  { label: t.nav.sources, icon: Library, path: "sources" },
];

export const WORKSPACE_NAV: NavItem[] = [
  { label: t.nav.members, icon: Users, path: "membres" },
  { label: t.nav.settings, icon: Settings, path: "parametres" },
];
