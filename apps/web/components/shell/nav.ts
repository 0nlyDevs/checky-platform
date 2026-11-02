import { IconAddressBook, IconFolderOpen, IconGear, IconNewspaper, IconRadio, IconScan, type Icon } from "@/lib/icons";
import { t } from "@/lib/i18n/fr";

export type NavItem = {
  label: string;
  short?: string;
  icon: Icon;
  path?: string;
  /** Other sections under this tab (their address lights it). */
  also?: string[];
};

// `path` is relative to /w/[ws]. Five places, in the order of a journalist's morning: my page,
// check what came in, the dossiers, what circulates (radio, press, tips, SMS), who and what to
// consult (contacts, official documents, registered communiqués, official figures).
export const NAV: NavItem[] = [
  { label: t.nav.rubrique, short: t.nav.rubriqueShort, icon: IconNewspaper, path: "rubrique", also: ["angles"] },
  { label: t.nav.check, icon: IconScan, path: "verifier", also: ["analyser"] },
  { label: t.nav.claims, icon: IconFolderOpen, path: "affirmations", also: ["sources", "transcriptions"] },
  { label: t.nav.veille, icon: IconRadio, path: "veille" },
  { label: t.nav.annuaire, icon: IconAddressBook, path: "annuaire", also: ["documents", "registre", "chiffres"] },
];

// Réglages holds the newsroom's rules and its team.
export const WORKSPACE_NAV: NavItem[] = [{ label: t.nav.settings, icon: IconGear, path: "parametres", also: ["membres"] }];

// The phone bar keeps the four daily sections beside the assistant; Annuaire folds into « Plus ».
export const BAR_NAV: NavItem[] = NAV.slice(0, 4);

/** The sections grouped under one tab, shown as a strip at the top of each of them. */
export const SECTIONS: Record<string, { path: string; label: string }[]> = {
  annuaire: [
    { path: "annuaire", label: t.nav.annuaire },
    { path: "documents", label: t.nav.documents },
    { path: "registre", label: t.nav.registre },
    { path: "chiffres", label: t.nav.chiffres },
  ],
  affirmations: [
    { path: "affirmations", label: t.nav.claims },
    { path: "sources", label: t.nav.sources },
  ],
};
