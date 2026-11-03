import { IconAddressBook, IconFolderOpen, IconGear, IconNewspaper, IconRadio, IconScan, type Icon } from "@/lib/icons";
import { t } from "@/lib/i18n/live";

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
  { get label() { return t.nav.rubrique; }, get short() { return t.nav.rubriqueShort; }, icon: IconNewspaper, path: "rubrique", also: ["angles"] },
  { get label() { return t.nav.check; }, icon: IconScan, path: "verifier", also: ["analyser", "scanner"] },
  { get label() { return t.nav.claims; }, icon: IconFolderOpen, path: "affirmations", also: ["sources", "transcriptions"] },
  { get label() { return t.nav.veille; }, icon: IconRadio, path: "veille", also: ["studio"] },
  { get label() { return t.nav.annuaire; }, icon: IconAddressBook, path: "annuaire", also: ["documents", "registre", "chiffres"] },
];

// Réglages holds the newsroom's rules and its team.
export const WORKSPACE_NAV: NavItem[] = [{ get label() { return t.nav.settings; }, icon: IconGear, path: "parametres", also: ["membres"] }];

// The phone bar keeps the four daily sections beside the assistant; Annuaire folds into « Plus ».
export const BAR_NAV: NavItem[] = NAV.slice(0, 4);

/** The sections grouped under one tab, shown as a strip at the top of each of them. */
export const SECTIONS: Record<string, { path: string; label: string }[]> = {
  annuaire: [
    { path: "annuaire", get label() { return t.nav.annuaire; } },
    { path: "documents", get label() { return t.nav.documents; } },
    { path: "registre", get label() { return t.nav.registre; } },
    { path: "chiffres", get label() { return t.nav.chiffres; } },
  ],
  affirmations: [
    { path: "affirmations", get label() { return t.nav.claims; } },
    { path: "sources", get label() { return t.nav.sources; } },
  ],
  // Studio lives inside Veille: a show is checked while it airs, then its claims join the watching.
  veille: [
    { path: "veille", get label() { return t.nav.veille; } },
    { path: "studio", get label() { return t.studio.nav; } },
  ],
};
