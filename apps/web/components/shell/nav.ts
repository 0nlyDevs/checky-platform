import { IconBooks, IconFolderOpen, IconGear, IconScan, IconUsers, type Icon } from "@/lib/icons";
import { t } from "@/lib/i18n/fr";

export type NavItem = { label: string; icon: Icon; path?: string };

// `path` is relative to /w/[ws]. Three places a journalist works in every day: check what came in,
// follow the dossiers, find a source. Recordings live under Sources (they are sources), and the
// newsroom's own pages sit in WORKSPACE_NAV.
export const NAV: NavItem[] = [
  { label: t.nav.check, icon: IconScan, path: "verifier" },
  { label: t.nav.claims, icon: IconFolderOpen, path: "affirmations" },
  { label: t.nav.sources, icon: IconBooks, path: "sources" },
];

export const WORKSPACE_NAV: NavItem[] = [
  { label: t.nav.members, icon: IconUsers, path: "membres" },
  { label: t.nav.settings, icon: IconGear, path: "parametres" },
];
