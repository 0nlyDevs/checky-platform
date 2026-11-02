import { IconAddressBook, IconBooks, IconCalculator, IconCompass, IconFileText, IconFolderOpen, IconGear, IconNewspaper, IconRadio, IconScan, IconStamp, IconUsers, type Icon } from "@/lib/icons";
import { t } from "@/lib/i18n/fr";

export type NavItem = { label: string; short?: string; icon: Icon; path?: string };

// `path` is relative to /w/[ws]. The newsroom's sections, in the order of a journalist's morning:
// my page (what circulates for my beats and places), check what came in, follow the dossiers,
// watch what circulates (radio, press, tips, SMS), the registry of originals, the sources.
export const NAV: NavItem[] = [
  { label: t.nav.rubrique, short: t.nav.rubriqueShort, icon: IconNewspaper, path: "rubrique" },
  { label: t.nav.check, icon: IconScan, path: "verifier" },
  { label: t.nav.claims, icon: IconFolderOpen, path: "affirmations" },
  { label: t.nav.veille, icon: IconRadio, path: "veille" },
  { label: t.nav.registre, icon: IconStamp, path: "registre" },
  { label: t.nav.sources, icon: IconBooks, path: "sources" },
];

// « Le carnet »: the reference shelves a journalist opens and closes (who to call, the documents,
// the official figures, story angles).
export const CARNET_NAV: NavItem[] = [
  { label: t.nav.annuaire, icon: IconAddressBook, path: "annuaire" },
  { label: t.nav.documents, icon: IconFileText, path: "documents" },
  { label: t.nav.chiffres, icon: IconCalculator, path: "chiffres" },
  { label: t.nav.angles, icon: IconCompass, path: "angles" },
];

export const WORKSPACE_NAV: NavItem[] = [
  { label: t.nav.members, icon: IconUsers, path: "membres" },
  { label: t.nav.settings, icon: IconGear, path: "parametres" },
];

// The phone bar keeps the four daily sections beside the assistant.
export const BAR_NAV: NavItem[] = NAV.slice(0, 4);
