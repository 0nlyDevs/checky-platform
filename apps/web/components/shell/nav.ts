import { AudioLines, Library, ListChecks, Search, Settings, Users, type LucideIcon } from "lucide-react";
import { t } from "@/lib/i18n/fr";

export type NavItem = { label: string; icon: LucideIcon; path?: string };

// `path` is relative to /w/[ws]; items without one are not built yet.
export const NAV: NavItem[] = [
  { label: t.nav.claims, icon: ListChecks, path: "affirmations" },
  { label: t.nav.check, icon: Search },
  { label: t.nav.sources, icon: Library, path: "sources" },
  { label: t.nav.transcriptions, icon: AudioLines, path: "transcriptions" },
  { label: t.nav.members, icon: Users, path: "membres" },
  { label: t.nav.settings, icon: Settings, path: "parametres" },
];
