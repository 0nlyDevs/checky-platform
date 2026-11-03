// Checky strings for the crew on Vérifier. Spread into `fr` by lib/i18n/fr.ts (t.crew).

const days = (n: number) => (n === 1 ? "1 jour" : `${n} jours`);
const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

export const crew = {
  // the live log: the crew racing
  live: {
    title: "L'équipe de Checky",
    running: "En direct",
    done: "Terminé",
    legend: "Trait plein : un fait retrouvé par le code. Pointillé : une lecture d'un modèle d'IA.",
    fact: "fait",
    model: "IA",
    again: "relancé",
    seconds: (ms: number) => `${(ms / 1000).toFixed(1).replace(".", ",")} s`,
    stages: { read: "Lecture", facts: "Les faits, en parallèle", reading: "La lecture" } as Record<string, string>,
    status: {
      waiting: "En attente",
      running: "En cours",
      done: "Fait",
      failed: "Échec",
      timeout: "Délai dépassé",
      skipped: "Non applicable",
      no_ai: "IA coupée",
    } as Record<string, string>,
    // The crew's names as shown (the keys are the API's agent names).
    names: {
      Lecteur: "Lecteur",
      Provenance: "Provenance",
      Registre: "Registre",
      Chiffres: "Chiffres",
      "Fact-checkers": "Fact-checkers",
      Web: "Web",
      Archives: "Archives",
      Fiabilité: "Fiabilité",
      Ton: "Ton",
      Éléments: "Éléments",
      Synthèse: "Synthèse",
      Contradicteur: "Contradicteur",
      Confiance: "Confiance",
    } as Record<string, string>,
    roles: {
      Lecteur: "Relève les affirmations, les chiffres et les lieux",
      Provenance: "Date l'image, la vidéo ou la page",
      Registre: "Compare au communiqué original",
      Chiffres: "Compare aux chiffres officiels",
      "Fact-checkers": "Cherche les avis déjà publiés",
      Web: "Cherche et lit des pages",
      Archives: "Fouille les sources de la rédaction",
      Fiabilité: "Regarde ce que le site dit de lui",
      Ton: "Mesure le ton du message",
      Éléments: "Numérote ce qui a été trouvé",
      Synthèse: "Propose une lecture",
      Contradicteur: "Cherche la faille",
      Confiance: "Calcule la solidité",
    } as Record<string, string>,
  },
  noLecture: {
    no_ai: "Sans IA : pas de lecture",
    no_evidence: "Pas de lecture : trop peu d'éléments lus",
    ai_failed: "Pas de lecture : les modèles d'IA n'ont pas répondu",
  } as Record<string, string>,

  // « Sans IA » for one run
  noAi: {
    label: "Sans IA",
    hint: "Pour cette vérification : les faits seulement, aucune lecture d'un modèle.",
    newsroomOff: "L'IA est coupée pour toute la rédaction (Réglages) : les faits seulement.",
  },

  // the facts, first
  facts: {
    title: "Les faits",
    lead: "Ce que le code a retrouvé, sans interprétation. À lire avant la lecture de Checky.",
    none: "Aucun fait retrouvé pour ce message. La lecture, s'il y en a une, repose sur le web.",
    notChecked: "Non vérifié cette fois",
  },
  provenance: {
    title: "Provenance",
    first: (date: string) => `Première trace datée : ${date}`,
    basis: {
      exif: "date de prise de vue (EXIF)",
      video: "date de création de la vidéo",
      published: "date de publication",
    } as Record<string, string>,
    ago: (n: number) => (n === 0 ? "aujourd'hui" : `il y a ${days(n)}`),
    hint: "Image ancienne, légende récente : le contenu circule de nouveau, présenté comme actuel.",
    noTrace: "Aucune trace de générateur d'IA dans le fichier : cela ne prouve rien.",
    reverse: "Recherche inversée",
  },
  registry: {
    title: "Registre des originaux",
    contacts: "Peut confirmer",
    open: "Voir l'original",
  },
  figures: {
    title: "Chiffres officiels",
    claimed: "Annoncé",
    official: "Chiffre officiel",
    verdict: { matches: "Concorde", differs: "Diffère", no_figure: "Aucun chiffre officiel" } as Record<string, string>,
    asOf: (date: string) => `au ${date}`,
    old: "chiffre ancien",
  },
  factChecks: {
    title: "Fact-checkeurs",
    by: (who: string, date?: string | null) => (date ? `Vérifié par ${who}, le ${date}` : `Vérifié par ${who}`),
    rating: (rating: string) => `Leur conclusion : « ${rating} »`,
    note: "Leur avis, relayé tel quel, avec son lien.",
  },
  published: {
    title: "Déjà vérifié",
    by: (newsroom: string) => `Déjà vérifié par ${newsroom}`,
    open: "Voir le verdict",
  },
  archives: {
    title: "Dans nos archives",
    open: "Ouvrir le dossier",
  },
  undated: "date inconnue",
  recheck: "Recherche ciblée",

  // the reading, dashed
  lecture: {
    title: "Lecture de Checky",
    by: "Proposée par l'IA à partir des éléments numérotés, à confirmer par la rédaction.",
    level: { eleve: "Élevé", moyen: "Moyen", faible: "Faible" } as Record<string, string>,
    score: (score: number, level: string) => `${score} % · ${level}`,
    scoreLabel: "Solidité des éléments",
    meaning: "Ce pourcentage mesure la solidité des éléments, pas la probabilité que l'affirmation soit vraie. Il est calculé par le code, jamais par le modèle.",
    reasons: "Pourquoi",
    missing: "Il manque",
    restsOn: "Elle cite",
    dates: "Les dates",
    rumour: (date: string) => `Rumeur datée du ${date}`,
    before: (n: number) => (n <= 0 ? "le jour même ou après" : `${days(n)} avant la rumeur`),
    downgraded: "Les seules confirmations datent de plus de 30 jours avant la rumeur : la lecture passe à « Invérifiable ».",
    oldEvidence: "Tous les éléments qui tranchent datent de plus de 30 jours avant la rumeur.",
    how: "Comment c'est calculé",
    howLead: "Six critères, 100 points. Chaque limite citée par le Contradicteur retire 5 points (15 au plus).",
    components: {
      agreement: "Accord des sources",
      official: "Source officielle",
      dates: "Dates",
      outside: "Source extérieure",
      attached: "Gardées par la rédaction",
      hosts: "Origines distinctes",
      critique: "Contradicteur",
    } as Record<string, string>,
    points: (points: number, maximum: number) => (maximum ? `${points} / ${maximum}` : `${points}`),
    critique: "Le Contradicteur relève",
    recheck: (query: string, n: number) => `Recherche ciblée relancée : « ${query} » · ${plural(n, "résultat", "résultats")}`,
    noCritic: "La relecture critique n'a pas abouti : lisez les éléments avant d'utiliser cette lecture.",
    factsOnly: "Solidité des éléments, sans IA",
    factsOnlyLead: "Calculée par le code à partir des faits ci-dessus. Ce n'est pas une conclusion : elle revient au journaliste.",
    direction: {
      supports: "Les éléments confirment l'affirmation",
      contradicts: "Les éléments contredisent l'affirmation",
      mixed: "Les éléments se contredisent",
      none: "Aucun élément ne tranche",
    } as Record<string, string>,
  },

  // what the site says about itself
  reliability: {
    title: "Fiabilité de la source",
    lead: "Ce que le site montre de lui-même : des signaux, jamais une note.",
    status: { found: "Trouvé", missing: "Non trouvé", unknown: "Inconnu" } as Record<string, string>,
    keys: {
      author: "Auteur",
      date: "Date",
      about: "Page « À propos »",
      contact: "Contact",
      legal: "Mentions légales",
      corrections: "Politique de correction",
      https: "Connexion chiffrée",
      domain_age: "Âge du domaine",
      fact_checker: "Fact-checkeur reconnu",
      official: "Site officiel",
      press: "Média déclaré",
    } as Record<string, string>,
    known: { fact_checker: "Fact-checkeur reconnu", official: "Site officiel", press: "Média connu" } as Record<string, string>,
    platform: (name: string) => `Publication sur ${name} : le réseau ne dit rien de la source, seul l'auteur affiché compte.`,
  },

  // how it is written, and how urgent it is to check
  tone: {
    title: "Ton du message",
    level: { sensationnaliste: "Sensationnaliste", marqué: "Marqué", neutre: "Neutre" } as Record<string, string>,
    kinds: {
      urgency: "Urgence",
      share: "Appel à partager",
      emotive: "Mot chargé",
      hidden: "« On vous cache »",
      caps: "Majuscules",
      exclamations: "Points d'exclamation",
      emoji: "Émoji d'alerte",
    } as Record<string, string>,
    note: "Le ton ne dit pas si c'est vrai : il dit comment le message cherche à circuler.",
    framing: "Cadrage relevé par l'IA",
    framingKinds: {
      political_framing: "Cadrage politique",
      loaded_language: "Vocabulaire chargé",
      clickbait: "Accroche sensationnaliste",
      opinion_as_fact: "Opinion présentée comme un fait",
    } as Record<string, string>,
  },
  risk: {
    label: { high: "Risque élevé", medium: "Risque moyen", low: "Risque faible" } as Record<string, string>,
    kinds: {
      violence: "Appel à la violence",
      accusation: "Accusation contre une personne",
      panic: "Peut créer la panique",
      fake_order: "Se présente comme un ordre officiel",
    } as Record<string, string>,
    note: "Le risque dit l'urgence de vérifier, pas la vérité.",
  },

  // who sees what
  strip: {
    label: "Ce que voit le public",
    already: "Déjà visible du public",
    alreadyValue: (checks: number, verdicts: number) =>
      [checks ? plural(checks, "avis de fact-checkeur", "avis de fact-checkeurs") : "", verdicts ? plural(verdicts, "verdict publié", "verdicts publiés") : ""]
        .filter(Boolean)
        .join(", ") || "rien de ce qui a été trouvé ici",
    after: "Après votre signature",
    afterValue: "le verdict, sa raison et ses sources",
    never: "Jamais",
    neverValue: "la lecture, le pourcentage, ce dossier",
  },

  contact: "Qui peut le prouver ?",
  contactHelp: "Les contacts de la rédaction et leur domaine d'expertise.",
  openDirectory: "Ouvrir l'annuaire",
} as const;
