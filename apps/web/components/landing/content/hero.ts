import { ROUTES } from "./site";

/**
 * Tone of a placeholder clip. The room hero highlights tiles by tone while the
 * chat bar cycles prompts, so each prompt below names the tone it lights up.
 */
export type ClipTone = "cool" | "warm" | "mono" | "bright";

export interface HeroClip {
  id: string;
  /** Label painted on the placeholder card. */
  label: string;
  tones: ClipTone[];
  /** Optional real clip, e.g. '/site/landing/videos/delestage.mp4' (h264, muted). Without it a placeholder is drawn. */
  src?: string;
}

/** Clips shared by both heroes (sources and licences: public/videos/CREDITS.md). */
export const HERO_CLIPS: HeroClip[] = [
  { id: "v01", label: "Marché", tones: ["warm"], src: "/site/landing/videos/marche-a.mp4" },
  { id: "v02", label: "Cyclone Freddy", tones: ["cool"], src: "/site/landing/videos/cyclone-freddy.mp4" },
  { id: "v03", label: "Délestage vu du ciel", tones: ["mono"], src: "/site/landing/videos/delestage-satellite.mp4" },
  { id: "v04", label: "Archive", tones: ["mono"], src: "/site/landing/videos/archive-a.mp4" },
  { id: "v05", label: "Reportage TV", tones: ["bright", "cool"], src: "/site/landing/videos/tv-reportage.mp4" },
  { id: "v06", label: "Cyclone Gamane", tones: ["warm", "bright"], src: "/site/landing/videos/cyclone-gamane.mp4" },
  { id: "v07", label: "Route", tones: ["bright"], src: "/site/landing/videos/route.mp4" },
  { id: "v08", label: "Coupure vue du ciel", tones: ["mono", "cool"], src: "/site/landing/videos/coupure-satellite.mp4" },
  { id: "v09", label: "Carte", tones: ["bright", "warm"], src: "/site/landing/videos/carte-madagascar.mp4" },
  { id: "v10", label: "Marché", tones: ["warm"], src: "/site/landing/videos/marche-b.mp4" },
  { id: "v11", label: "Archive", tones: ["mono"], src: "/site/landing/videos/archive-b.mp4" },
  { id: "v12", label: "Studio radio", tones: ["warm", "cool"], src: "/site/landing/videos/studio-radio.mp4" },
];

/**
 * The rumour reel: the card the torch picks out of the galaxy, which then
 * becomes the reel shown at the start of « La rumeur ».
 */
export const REEL_CLIP: HeroClip = { id: "reel", label: "Reel · 72 h de délestage ?", tones: ["warm"], src: "/site/landing/videos/reel-rocade-nuit.mp4" };

/* ---------- Page « / » : hero galaxie ---------- */

export const GALAXIE = {
  word: "CHECKY",
  tag: "Fanilo 2026 · Madagascar",
  /** Rumours typed in the bar, one after the other; sending one stirs the galaxy. */
  prompts: [
    "« 72 heures de délestage dès demain » : c’est vrai ?",
    "Cette vidéo de Toamasina date de quand ?",
    "Qui a vraiment publié ce communiqué ?",
    "Ce SMS de la JIRAMA est-il authentique ?",
  ],
  bar: {
    label: "Collez une info reçue : Checky regarde si elle est déjà vérifiée",
    submit: "Vérifier",
  },
  title: "La torche",
  titleEm: "du journaliste.",
  lead: "Vérifiez la rumeur avant qu’elle ne devienne une nouvelle. En malagasy, en français, en anglais, même sans réseau.",
  primary: { label: "Ouvrir Checky", href: ROUTES.signIn },
  /** Hackathon partners, shown beside the main button. Paper-ink cut-outs of their logos. */
  partners: {
    label: "Avec",
    logos: [
      {
        name: "Institut français de Madagascar",
        href: "https://institutfrancais-madagascar.com/",
        src: "/site/landing/sponsors/institut-francais.png",
        width: 282,
        height: 189,
      },
      { name: "42 Antananarivo, Axian Group", href: "https://42antananarivo.mg/", src: "/site/landing/sponsors/42-antananarivo.png", width: 330, height: 189 },
    ],
  },
};
