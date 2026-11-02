// Everything the pitch deck says, in one place. Edit this file, then `node build.js`.
//
// Anything between {{double braces}} is a hole to fill. `node build.js` lists the holes that are
// left; the checklist refuses a deck that still has one.
//
// The pitch follows ONE rumour from start to end: it arrives at 23:47 (cover), the need is said in
// the jury's own words, the stance (a machine does not sign a verdict), the demo shows that same
// rumour from arrival to the public, and the close returns to it (« 23 h 47, une rumeur. 6 h 41,
// vérifié. »). The example running through the file (FAN-0138, « Analakely sous l'eau ») is a
// fictional affair: replace it with the real story everywhere at once (here and video/scenes.json).
//
// One idea per slide. The screen carries a title and a few words; what the speaker says lives in
// `notes`. Slide titles fit one line under about 50 characters, card titles under about 30.
//
// Timing adds up to 3:00, the jury's hard limit (rules, article 4). The pitch must let the jury
// understand the need, the solution and how it works, its value for journalists and its potential
// (article 4); the jury scores relevance, usability, contribution to information resilience,
// technical quality, potential and the pitch itself (article 5). Each slide says which it serves.

const team = {
  name: "0nlyDevs",
  members: ["{{Prénom Nom}}", "{{Prénom Nom}}", "{{Prénom Nom}}", "{{Prénom Nom}}"],
  speaker: "{{Qui parle}}",
  driver: "{{Qui tient le clavier}}",
};

const product = {
  name: "Checky", // lib/brand.ts says the same; change both if the name changes
  claim: "Les autres détectent. Checky prouve.",
  url: "{{fanilo.example}}",
  caseRef: "FAN-0138",
};

const event = {
  name: "Hackathon FANILO",
  date: "4 novembre 2026",
};

const slides = [
  {
    kind: "cover",
    t: "0:00–0:20",
    serves: "Article 4 · ouverture : la scène, sans se présenter",
    label: `${event.name} · ${event.date}`,
    title: product.claim,
    sub: "L'outil de vérification des rédactions de Madagascar.",
    piece: { file: "piece-1.jpg", time: "23:47:12", caption: "Pièce 1 · vidéo, groupe WhatsApp" },
    stamp: "Faux",
    fictional: "Exemple fictif.",
    notes: [
      "(Pas de « Bonjour, nous sommes… ». On commence par la scène.)",
      "23 h 47. Une vidéo arrive dans un groupe WhatsApp : « Analakely sous l'eau ce matin, partagez ! »",
      "À minuit, 2 300 partages. À 7 h, la radio doit dire si c'est vrai.",
      "{{La même scène, avec la vraie rumeur du sujet.}}",
    ],
  },
  {
    kind: "need",
    t: "0:20–0:40",
    serves: "Article 4 · le besoin / Article 5 · pertinence",
    tab: "Le besoin",
    title: "{{Le besoin, en une phrase}}",
    quote: "{{Une phrase entendue dans la vidéo, citée mot pour mot}}",
    quoteBy: "{{Qui l'a dite, fonction, média}}",
    timeline: {
      label: "Une nuit · exemple fictif",
      rows: [
        ["23:47", "Une vidéo sur WhatsApp"],
        ["00:31", "2 300 partages sur Facebook"],
        ["04:50", "« Je l'ai déjà vue l'an dernier »"],
        ["06:05", "La radio en parle"],
        ["07:00", "Vrai ou faux ?"],
      ],
    },
    notes: [
      "Ce problème, ce n'est pas nous qui le disons. C'est {{qui}} : « {{la citation, mot pour mot}} ».",
      "{{Ce qui se passe aujourd'hui sans l'outil : ce que le journaliste fait à la main, combien de temps il y passe, ce qu'il risque.}}",
      "{{Le chiffre qui prouve que le besoin est réel, s'il y en a un.}}",
    ],
  },
  {
    kind: "stance",
    t: "0:40–0:55",
    serves: "Article 4 · la solution et son fonctionnement / Article 5 · pertinence",
    tab: "Le parti pris",
    title: "Une machine ne signe pas un verdict.",
    temptation: { label: "On aurait pu faire", text: "{{une IA qui dit vrai ou faux en un clic}}" },
    stamp: "Non.",
    report: `Dossier ${product.caseRef}`,
    steps: [
      ["23:47", "La rumeur arrive"],
      ["06:12", "On réunit les preuves"],
      ["06:30", "L'IA lit et propose"],
      ["06:41", "Un journaliste signe"],
    ],
    notes: [
      "On aurait pu faire {{une IA qui dit vrai ou faux}}. Non : une machine ne signe pas un verdict.",
      "Alors chaque rumeur devient un dossier. On y verse les preuves ; l'IA les lit et propose, en citant mot pour mot. Une citation introuvable dans sa source est écartée ; sans preuve, elle répond « invérifiable ».",
      "Et c'est un journaliste qui signe. Jamais la machine.",
    ],
  },
  {
    kind: "demo",
    t: "0:55–2:05",
    serves: "Article 5 · qualité technique et fonctionnalité",
    tab: "Démo",
    title: "{{Titre de la démo, en une ligne}}",
    chapters: ["La rumeur arrive", "L'IA lit, le journaliste signe", "Le public la retrouve"],
    notes: [
      "Plan A : démo en direct (onglet déjà ouvert, démo réinitialisée). Plan B : lancer demo.mp4 et commenter par-dessus. Même rumeur que l'ouverture.",
      "1. Voilà la vidéo de 23 h 47 dans la grille du desk : son heure, son origine. Elle devient un dossier, avec ses preuves.",
      "2. L'IA a lu les preuves et propose « Faux », citation par citation. Le journaliste vérifie, et il signe.",
      "3. Le lendemain, quelqu'un reçoit la même vidéo. Il demande si c'est vérifié : l'assistant retrouve le dossier et cite le verdict.",
    ],
  },
  {
    kind: "value",
    t: "2:05–2:30",
    serves: "Article 4 · intérêt pour les médias / Article 5 · utilité, résilience informationnelle",
    tab: "Pour les journalistes",
    title: "Rien ne part sans une personne.",
    cards: [
      ["Sur le terrain", "{{Depuis un téléphone, en 3G : ce que fait le journaliste.}}"],
      ["En deux langues", "Français et malagasy, de la note vocale à la carte publiée."],
      ["Des preuves, pas un avis", "Chaque citation est retrouvée mot pour mot dans sa source."],
    ],
    notes: [
      "Pour un journaliste, ça change trois choses. {{Les trois, en une phrase chacune, et un chiffre si on en a un (« de 2 heures à 20 minutes »).}}",
      "Et une règle : l'IA ne publie jamais. Elle propose, une personne signe.",
    ],
  },
  {
    kind: "next",
    t: "2:30–2:50",
    serves: "Article 4 · potentiel / Article 5 · potentiel de développement",
    tab: "Et après",
    title: "{{Une rédaction, puis toutes.}}",
    items: [
      ["En ligne", product.url],
      ["Ouvert au public", "Les verdicts publiés se consultent sans compte."],
      ["Ensuite", "{{Ce qu'on ferait avec un mois, en une ligne.}}"],
    ],
    notes: [
      "L'outil est en ligne, aujourd'hui, à cette adresse. Une rédaction y ouvre son espace en deux minutes.",
      "Le public peut demander si une rumeur est déjà vérifiée, et en signaler une nouvelle.",
      "{{La suite, en une phrase : avec qui, et pour quoi.}}",
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
      "23 h 47, une rumeur. 6 h 41, vérifié.",
      `${product.name}. Chaque rumeur a son dossier.`,
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
      ["L'application", ["Installable sur téléphone", "Mise à jour en direct pour toute la rédaction"]],
      ["L'IA", ["Plusieurs fournisseurs : si l'un tombe, l'autre répond", "Transcription et recherche avec citations"]],
      ["Les garde-fous", ["Une citation introuvable est écartée", "{{N}} tests à chaque modification"]],
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
