// Everything the pitch deck says, in one place. Edit this file, then `node build.js`.
//
// Anything between {{double braces}} is a hole to fill. `node build.js` lists the holes that are
// left; the checklist refuses a deck that still has one.
//
// The pitch follows ONE rumour from start to end: it arrives at 23:47 (cover), the need is said in
// the jury's own words, the stance (a rumour travels, the truth must catch up; a machine does not
// sign a verdict), the demo shows that same rumour from arrival to the truth sent back down its
// road, and the close returns to it (« 23 h 47, une rumeur. 6 h 41, vérifiée, et revenue par toutes
// ses routes. »). The example running through the file (FAN-0145, « 72 heures de délestage ») is a
// fictional affair seeded by the demo reset (apps/api/app/modules/demo.py): the pasted text is
// DEMO_RUMOUR_TEXT, the registered original is communiqué N° 2026-118 (4 h/jour), the official
// figure is +12 %, the video dates from 14 March 2023.
//
// One idea per slide. The screen carries a title and a few words; what the speaker says lives in
// `notes`. Slide titles fit one line under about 50 characters, card titles under about 30.
//
// Timing adds up to 3:00, the jury's hard limit (rules, article 4). The pitch must let the jury
// understand the need, the solution and how it works, its value for journalists and its potential
// (article 4); the jury scores relevance, usability, contribution to information resilience,
// technical quality, potential and the pitch itself (article 5). Each slide says which it serves.
//
// The full spoken script, the selling points and the jury's likely questions live in the Claude Doc
// « FANILO Hackathon — The brief, decoded, and how we win », tab Pitch.

const team = {
  name: "0nlyDevs",
  members: ["{{Prénom Nom}}", "{{Prénom Nom}}", "{{Prénom Nom}}", "{{Prénom Nom}}"],
  speaker: "{{Qui parle}}",
  driver: "{{Qui tient le clavier}}",
};

const product = {
  name: "Checky", // lib/brand.ts says the same; change both if the name changes
  claim: "Les autres détectent. Checky prouve.",
  url: "fanilo-mg.vercel.app",
  caseRef: "FAN-0145",
};

const event = {
  name: "Hackathon FANILO",
  date: "4 novembre 2026",
};

const slides = [
  {
    kind: "cover",
    t: "0:00–0:15",
    serves: "Article 4 · ouverture : la scène, sans se présenter",
    label: `${event.name} · ${event.date}`,
    title: "Marina sa sandoka ?",
    sub: "Checky, la torche des rédactions.",
    piece: { file: "piece-1.jpg", time: "23:47:12", caption: "Pièce 1 · vidéo + communiqué, groupe WhatsApp" },
    stamp: "Faux",
    fictional: "Exemple fictif.",
    notes: [
      "(Pas de « Bonjour, nous sommes… ». On commence par la scène, téléphone en main.)",
      "23 h 47, Toamasina. Une vidéo circule : « 72 heures de délestage dès demain », avec un communiqué de la JIRAMA. Trois cents partages en dix minutes.",
      "À six heures, une radio la répète. À huit heures, on fait la queue pour des bougies.",
      "Le communiqué était modifié. La vidéo datait de 2023.",
    ],
  },
  {
    kind: "need",
    t: "0:15–0:30",
    serves: "Article 4 · le besoin / Article 5 · pertinence",
    tab: "Le besoin",
    title: "Huit besoins. Nous les avons pris un par un.",
    quote: "Premièrement et le plus essentiel : authentifier les photos et les vidéos.",
    quoteBy: "{{Qui l'a dit, fonction, média — la vidéo du 2 novembre}}",
    timeline: {
      label: "Une nuit · exemple fictif",
      rows: [
        ["23:47", "Une vidéo et un communiqué sur WhatsApp"],
        ["23:57", "300 partages sur Facebook"],
        ["06:00", "Une radio la répète"],
        ["08:00", "La queue pour des bougies"],
        ["08:00", "Marina sa sandoka ?"],
      ],
    },
    notes: [
      "Vous nous l'avez dit : « il est difficile de trouver la source primaire ». « Premièrement et le plus essentiel : authentifier les photos et les vidéos. » « Le niveau de confiance. »",
      "Huit besoins. Nous les avons pris un par un, et chacun a son écran.",
    ],
  },
  {
    kind: "stance",
    t: "0:30–0:55",
    serves: "Article 4 · la solution et son fonctionnement / Article 5 · pertinence",
    tab: "Le parti pris",
    title: "Une rumeur voyage. La vérité doit la rattraper.",
    temptation: { label: "On aurait pu faire", text: "une IA qui dit vrai ou faux en un clic, sur le web" },
    stamp: "Non.",
    report: `Dossier ${product.caseRef}`,
    steps: [
      ["23:47", "La rumeur part : WhatsApp, Facebook"],
      ["06:00", "La radio la répète"],
      ["06:41", "Checky prouve, un journaliste signe"],
      ["06:58", "La vérité revient par la radio et le SMS"],
    ],
    notes: [
      "Une rumeur voyage : Facebook, WhatsApp, la radio, le village. La vérité, elle, reste dans la rédaction. À Madagascar, 65 % des gens s'informent par la radio et 20 % seulement sont en ligne. Un outil qui ne vit que sur le web ne les atteindra jamais.",
      "Checky, la torche des rédactions. Elle éclaire chaque information : d'où elle vient, ce qu'elle vaut, qui peut la prouver, et par où la vérité revient.",
      "Elle répond tout de suite avec des faits ; le verdict, lui, se signe. Une machine ne signe pas un verdict.",
    ],
  },
  {
    kind: "demo",
    t: "0:55–2:10",
    serves: "Article 5 · qualité technique et fonctionnalité",
    tab: "Démo",
    title: "Une rumeur, du partage à la vérité revenue.",
    chapters: ["Les faits, tout de suite", "La lecture, puis la signature", "La vérité revient"],
    notes: [
      "Plan A : démo en direct (onglet déjà ouvert, démo réinitialisée). Plan B : lancer demo.mp4 et commenter par-dessus. Même rumeur que l'ouverture.",
      "1. Partager, Checky. La brigade court : huit vérifications en parallèle, sans IA. La vidéo d'abord : première apparition mars 2023, un autre événement. Vidéo ancienne, nouvelle affirmation.",
      "2. Le communiqué : l'original N° 2026-118 est au registre. « 72 heures » barré, « 4 heures par jour ». Modifié. Le chiffre : +40 % annoncés, +12 % au tarif officiel, source et date.",
      "3. La lecture de Checky, en pointillés : Trompeur. Un pourcentage sorti de la bouche d'une IA ne vaut rien ; le nôtre est calculé à partir des preuves, et voici comment.",
      "4. Qui peut le prouver : une seule personne, la chargée de communication de la JIRAMA, sa page officielle, son numéro, la question déjà écrite.",
      "5. La journaliste signe : savoir ne lui a demandé aucun clic, publier au nom de sa rédaction en demande un. Le verdict devient plein, avec sa signature.",
      "6. Diffuser : la carte en malgache et en français, la ligne radio lue à l'antenne, le SMS sur un téléphone à touches. Le trajet : la rumeur est passée par quatre routes ; la vérité les a toutes reprises.",
      "7. Le public : la même vidéo, demandée sur le site ou par SMS : « Trompeur, vérifié par la rédaction, le 3 novembre ». Jamais la lecture de la machine, jamais le pourcentage.",
    ],
  },
  {
    kind: "value",
    t: "2:10–2:30",
    serves: "Article 4 · intérêt pour les médias / Article 5 · résilience informationnelle, qualité technique",
    tab: "Pourquoi ça gagne",
    title: "Les autres détectent. Checky prouve.",
    cards: [
      ["Le meilleur des outils existants", "Transparence des sources (NewsGuard), diversité et ton (The Factual), explications sourcées (Aletheia), image signal par signal (FauxLens), verdicts de Snopes, PolitiFact, FactCheck.org, AFP Factuel… relayés via Google Fact Check Tools."],
      ["Ce qu'aucun ne fait", "Le trajet de la rumeur et de la correction, la signature du journaliste, le registre des originaux et son sceau hors ligne, la radio, le SMS, Madagascar."],
      ["Une brigade, pas un oracle", "Huit vérifications sans IA, une synthèse, un contradicteur, un journaliste qui signe. Trois appels au modèle, pas plus. Mode sans IA : les faits restent."],
    ],
    notes: [
      "Les autres détectent. Checky prouve : un original, une signature vérifiable sans réseau, une date.",
      "Nous avons pris le meilleur des outils qui existent : la grille de transparence des sources de NewsGuard, la diversité des sources de The Factual, les explications sourcées d'Aletheia, l'examen signal par signal des images de FauxLens, l'humain après la machine de Logically, et les verdicts de Snopes, PolitiFact, FactCheck.org, AFP Factuel ou Africa Check, relayés tels quels par l'API Google Fact Check Tools.",
      "Puis nous avons ajouté ce qu'aucun ne fait : le trajet, la signature, le registre des originaux, la radio, le SMS, Madagascar. Un geste, une carte, un bouton.",
    ],
  },
  {
    kind: "next",
    t: "2:30–2:50",
    serves: "Article 4 · potentiel / Article 5 · potentiel de développement",
    tab: "La valeur et qui paie",
    title: "Gratuit pour les rédactions et le public.",
    items: [
      ["Pour le journaliste", "La preuve en secondes, et un carnet de diligence qui le protège."],
      ["Pour une institution", "Son sceau rend les faux inutiles ; elle est alertée quand on la cite."],
      ["Qui paie", "Les institutions et entreprises dont on usurpe le nom, les agences en crise, les bailleurs des médias. Prochaine étape : la CENI avant 2027."],
    ],
    notes: [
      "Pour le journaliste : la preuve en secondes, et un carnet de diligence qui le protège. Pour la rédaction : une vérification sert à toutes. Pour une institution : son sceau rend les faux inutiles.",
      "Gratuit pour les journalistes et le public. Payé par les institutions et les entreprises dont on usurpe le nom, par les agences qui suivent les rumeurs en crise, par les bailleurs des médias.",
      "L'outil est en ligne, aujourd'hui, à cette adresse. Prochaine étape : la CENI avant 2027.",
    ],
  },
  {
    kind: "end",
    t: "2:50–3:00",
    serves: "Article 5 · qualité du pitch (fin nette)",
    title: product.name,
    sub: product.claim,
    url: product.url,
    stamp: "Vérifié",
    credits: "Photographies : Wikimedia Commons (CC BY-SA, CC0), tramées. Toute rumeur montrée est fictive.",
    notes: [
      "23 h 47, une rumeur. 6 h 41, vérifiée, et revenue par toutes ses routes.",
      `${product.name}. Marina sa sandoka ? Maintenant, on sait.`,
      "Nous sommes 0nlyDevs : {{les quatre prénoms}}. Merci.",
      "(Se taire et rester sur cette slide pour les questions.)",
    ],
  },
];

// Shown only if the jury asks (after the 3 minutes).
const backup = [
  {
    kind: "arch",
    tab: "Réserve",
    title: "Ce qu'on ne voit pas à l'écran.",
    columns: [
      ["La brigade", ["Des agents nommés par métier, pas par persona", "Huit vérifications en code, trois appels au modèle", "Mode sans IA : les faits restent"]],
      ["Les rôles", ["Admin, éditeur, journaliste, veilleur, émetteur", "Double signature : l'un signe, l'autre publie", "Partenaires et citoyens par lien ou SMS, sans compte"]],
      ["Les garde-fous", ["Une citation introuvable dans sa source est écartée", "« Introuvable » n'est jamais « Faux »", "Les dates viennent du code, jamais du modèle"]],
    ],
    footer: "Composants tiers, versions et licences : THIRD_PARTY.md (règlement, article 6).",
  },
  {
    kind: "team",
    tab: "Réserve",
    title: "L'équipe.",
    members: team.members.map((m) => [m, "{{Rôle}}"]),
  },
];

module.exports = { team, product, event, slides, backup };
