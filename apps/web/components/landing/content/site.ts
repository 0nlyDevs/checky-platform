/** Where the landing leads: pages of this app, and the Android build. */
export const ROUTES = {
  signIn: "/sign-in",
  signUp: "/sign-up",
  verified: "/verdicts",
  report: "/report",
  /** « Est-ce déjà vérifié ? » with the visitor's text, checked as soon as the page opens. */
  check: (text: string) => `/verdicts?q=${encodeURIComponent(text)}`,
  /** Preview APK of the phone app (EAS build, profile `preview`). */
  android: "https://expo.dev/artifacts/eas/oR4NkynNFr1zEdrw2DaLCgjHVVnmnSNb7cRhdX8lpcQ.apk",
};

export const SECTIONS = [
  { id: "checky", label: "Checky" },
  { id: "rumeur", label: "La rumeur" },
  { id: "besoins", label: "Vos besoins" },
  { id: "verdict", label: "Le verdict" },
  { id: "preuve", label: "La preuve" },
  { id: "trajet", label: "Le trajet" },
  { id: "partout", label: "Partout" },
  { id: "fin", label: "Commencer" },
] as const;

export type SectionId = (typeof SECTIONS)[number]["id"];

export const TONES = {
  vrai: "#3ddc84",
  faux: "#ff4a3d",
  trompeur: "#ffb224",
  inverif: "#3b8cff",
} as const;

export type Tone = keyof typeof TONES;

export const VERDICTS: {
  key: Tone;
  word: string;
  wash: string;
  line: string;
  rule: string;
}[] = [
  {
    key: "vrai",
    word: "Vrai",
    wash: "#0f2219",
    line: "Quatre sources concordantes, deux officielles, datées de cette semaine.",
    rule: "Le pourcentage vient des preuves, jamais du modèle.",
  },
  {
    key: "faux",
    word: "Faux",
    wash: "#2a1311",
    line: "Le vrai communiqué N° 045 dit quatre heures, pas soixante-douze.",
    rule: "Le faux et l’original côte à côte, les mots changés barrés.",
  },
  {
    key: "trompeur",
    word: "Trompeur",
    wash: "#29200c",
    line: "Vidéo ancienne, nouvelle affirmation. Aucun montage nécessaire pour tromper.",
    rule: "La première apparition compte plus qu’un détecteur de pixels.",
  },
  {
    key: "inverif",
    word: "Invérifiable",
    wash: "#101a2b",
    line: "Rien trouvé ne prouve rien. « Introuvable » n’est jamais « Faux ».",
    rule: "La carte nomme ce qui manque, et qui peut le confirmer.",
  },
];

export const NEEDS: { n: string; title: string; quote: string; answer: string }[] = [
  {
    n: "01",
    title: "Vérification des sources",
    quote: "Il est difficile de trouver la source primaire ou la source de l’information.",
    answer: "La source d’origine, datée, nommée en premier. Ce que disent les sources officielles, badgées.",
  },
  {
    n: "02",
    title: "Authentification des images",
    quote: "Premièrement et le plus essentiel : l’authentification des photos et des vidéos.",
    answer: "La photo ou la vidéo d’abord : première apparition, traces de génération, transcription.",
  },
  {
    n: "03",
    title: "Veille nationale",
    quote: "Suivre les actualités dans tout Madagascar et dans les différentes régions.",
    answer: "Ce qui circule, par région : radio, presse, signalements, SMS. La carte des 24 régions.",
  },
  {
    n: "04",
    title: "Multilinguisme",
    quote: "La langue malagasy bien sûr, le français et puis l’anglais.",
    answer: "Interface en malagasy, français et anglais. Le malgache parlé reste aux humains.",
  },
  {
    n: "05",
    title: "Accès hors connexion",
    quote: "Accessible même dans les zones reculées, si possible sans internet.",
    answer: "L’appli s’ouvre sans réseau. Le sceau se vérifie en mode avion. Un SMS suffit.",
  },
  {
    n: "06",
    title: "Annuaire des personnes-ressources",
    quote: "Quel département appeler, quel expert, quel dossier consulter.",
    answer: "Qui appeler, quel document ouvrir, et « Demander confirmation » en un tap.",
  },
  {
    n: "07",
    title: "Statistiques actualisées",
    quote: "L’accès aux données statistiques à jour reste un dilemme à Madagascar.",
    answer: "Le chiffre officiel, sa date, sa source, à côté de chaque nombre d’une rumeur.",
  },
  {
    n: "08",
    title: "Inspiration éditoriale",
    quote: "Nous aider à voir les angles de reportage pour chaque thème.",
    answer: "Trois à cinq angles tirés de ce qui circule, de ce qui revient, de ce qu’on demande.",
  },
];

export const ROUTE = {
  rumeur: [
    { label: "Facebook", time: "23:47" },
    { label: "WhatsApp", time: "00:10" },
    { label: "Radio, Atsinanana", time: "06:00" },
    { label: "SMS, Atsimo-Andrefana", time: "08:15" },
  ],
  verite: [
    { label: "Carte WhatsApp", time: "06:41" },
    { label: "Ligne radio lue", time: "07:42" },
    { label: "SMS aux abonnés", time: "07:50" },
    { label: "Affiche fokontany", time: "09:30" },
  ],
};

export const PHONE_GESTURES: { title: string; body: string; tag: string }[] = [
  { title: "Partager vers Checky", body: "Depuis Facebook, WhatsApp, TikTok ou la galerie : un post, un reel, une capture, un PDF.", tag: "Android" },
  {
    title: "La bulle sur les reels",
    body: "Un disque au bord de l’écran. Un tap : Checky écoute quinze secondes et répond par-dessus la vidéo.",
    tag: "Android",
  },
  {
    title: "Enregistrer la radio",
    body: "Soixante secondes près du poste, une phrase dite par un veilleur. Le malgache parlé reste aux humains.",
    tag: "Radio",
  },
  { title: "Scanner le sceau", body: "Le QR d’un communiqué se vérifie en mode avion. Un vrai QR collé sur un faux ne passe pas.", tag: "Hors ligne" },
  {
    title: "SMS 142",
    body: "Textez la rumeur au numéro entendu à l’antenne. Le verdict revient sans data, sur un téléphone à touches.",
    tag: "Tout téléphone",
  },
];

export const EXTENSION_GESTURES: { title: string; body: string; tag: string }[] = [
  {
    title: "Réponse sur place",
    body: "Sélectionnez une phrase, clic droit : la réponse apparaît sous la phrase, dans la page, comme une note.",
    tag: "Chrome, Edge, Brave",
  },
  {
    title: "Veille sur la page",
    body: "Sur Facebook ou TikTok, les posts qui recoupent un mot surveillé ou un verdict reçoivent un badge.",
    tag: "Facebook, TikTok",
  },
  {
    title: "Répondre avec le démenti",
    body: "Sous le post vérifié, la zone de commentaire se remplit avec le démenti et son lien. Vous appuyez sur envoyer.",
    tag: "Facebook",
  },
  {
    title: "Rien lu sans vous",
    body: "Aucun script sur les sites, aucune permission globale. La page n’est lue qu’au moment du clic droit.",
    tag: "Vie privée",
  },
];
