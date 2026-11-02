import {
  BookUser,
  Calculator,
  Compass,
  FileText,
  FolderOpen,
  Library,
  Newspaper,
  RadioTower,
  ScanSearch,
  Settings,
  Stamp,
  Users,
  type LucideIcon,
} from "lucide-react";
import { t } from "@/lib/i18n/fr";

export type NavItem = { label: string; short?: string; icon: LucideIcon; path?: string };

// `path` is relative to /w/[ws]. The newsroom's sections, in the order of a journalist's morning:
// my page (what circulates for my beats and places), check what came in, follow the dossiers,
// watch what circulates (radio, press, tips, SMS), the registry of originals, the sources.
export const NAV: NavItem[] = [
  { label: t.nav.rubrique, short: t.nav.rubriqueShort, icon: Newspaper, path: "rubrique" },
  { label: t.nav.check, icon: ScanSearch, path: "verifier" },
  { label: t.nav.claims, icon: FolderOpen, path: "affirmations" },
  { label: t.nav.veille, icon: RadioTower, path: "veille" },
  { label: t.nav.registre, icon: Stamp, path: "registre" },
  { label: t.nav.sources, icon: Library, path: "sources" },
];

// « Le carnet »: the reference shelves a journalist opens and closes (who to call, the documents,
// the official figures, story angles).
export const CARNET_NAV: NavItem[] = [
  { label: t.nav.annuaire, icon: BookUser, path: "annuaire" },
  { label: t.nav.documents, icon: FileText, path: "documents" },
  { label: t.nav.chiffres, icon: Calculator, path: "chiffres" },
  { label: t.nav.angles, icon: Compass, path: "angles" },
];

export const WORKSPACE_NAV: NavItem[] = [
  { label: t.nav.members, icon: Users, path: "membres" },
  { label: t.nav.settings, icon: Settings, path: "parametres" },
];

// The phone bar keeps the four daily sections beside the assistant.
export const BAR_NAV: NavItem[] = NAV.slice(0, 4);
