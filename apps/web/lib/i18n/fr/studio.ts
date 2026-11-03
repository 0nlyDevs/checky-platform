// Checky strings for Studio (slice « studio »). Spread into `fr` by lib/i18n/fr.ts.
// Mode direct (producer and presenter screens), Mode débat and the Bilan de l'émission.

const plural = (n: number, one: string, many: string) => `${n} ${n > 1 ? many : one}`;

/** 0:42, 12:05, 1:02:09 */
export const clock = (seconds: number) => {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
};

export const studio = {
  nav: "Studio",
  demo: "démo",
  loadFailed: "Impossible de charger le studio.",
  retry: "Réessayer",

  list: {
    title: "Studio",
    lead: "Vérifiez une émission pendant qu'elle passe à l'antenne : Checky écoute, repère les affirmations et les compare aux chiffres officiels, au registre et à vos verdicts signés.",
    newShow: "Préparer une émission",
    empty: "Aucune émission pour l'instant.",
    emptyHint: "Préparez la première : un nom, les thèmes, la source du son.",
    status: { draft: "En préparation", live: "À l'antenne", ended: "Terminée" } as Record<string, string>,
    claims: (n: number) => plural(n, "affirmation", "affirmations"),
    sent: (n: number) => (n ? `${plural(n, "envoyée", "envoyées")} au présentateur` : "rien envoyé au présentateur"),
    open: "Ouvrir",
    bilan: "Voir le bilan",
  },

  form: {
    title: "Préparer une émission",
    name: "Nom de l'émission",
    namePlaceholder: "Le débat du soir",
    station: "Radio ou chaîne",
    stationPlaceholder: "Radio Fanalana",
    topics: "Thèmes",
    topicsLead: "Checky prépare les verdicts, les chiffres officiels et les communiqués de ces thèmes avant l'antenne.",
    language: "Langue de l'émission",
    languages: { fr: "Français", mg: "Malgache" } as Record<string, string>,
    mgNote: "En malgache, rien n'est transcrit par une machine : vous écrivez ou dictez ce qui a été dit, en une phrase.",
    frNote: "En français, le son est transcrit au fil de l'émission.",
    input: "Source du son",
    inputs: { microphone: "Micro ou table de mixage", stream: "Son d'un onglet (flux web)" } as Record<string, string>,
    debate: "Mode débat",
    debateLead: "Ajoutez les intervenants : pendant l'émission, vous marquez qui parle et Checky compte les affirmations de chacun. Jamais de note, jamais de classement.",
    speakerName: (n: number) => `Intervenant ${n}`,
    speakerPlaceholder: "Nom affiché",
    camp: "Camp (facultatif)",
    noCamp: "Non classé",
    addSpeaker: "Ajouter un intervenant",
    removeSpeaker: (name: string) => `Retirer ${name}`,
    create: "Préparer l'émission",
    creating: "Préparation…",
    cancel: "Annuler",
    failed: "Impossible de créer l'émission.",
  },

  prep: {
    title: "Avant l'antenne",
    pack: "Fiches prêtes, même sans réseau",
    packing: "Préparation des fiches…",
    packFailed: "Fiches non chargées : le direct marchera, mais pas hors connexion.",
    packCounts: (v: number, f: number, r: number) =>
      `${plural(v, "verdict signé", "verdicts signés")} · ${plural(f, "chiffre officiel", "chiffres officiels")} · ${plural(r, "communiqué", "communiqués")}`,
    savedOffline: "Gardées dans ce navigateur.",
    device: "Entrée audio",
    defaultDevice: "Entrée par défaut",
    test: "Tester le son",
    testing: "Écoute…",
    tabHint: "Au démarrage, choisissez l'onglet qui diffuse l'émission et cochez « Partager l'audio ».",
    level: "Niveau du son",
    start: "Prendre l'antenne",
    starting: "Démarrage…",
    micDenied: "Micro refusé : autorisez-le dans le navigateur, ou tapez les affirmations à la main.",
    tabDenied: "Aucun son d'onglet partagé.",
    presenterLink: "Écran du présentateur",
    presenterHint: "À ouvrir sur la tablette ou l'écran du plateau.",
  },

  live: {
    onAir: "À l'antenne",
    paused: "Son coupé",
    elapsed: "Durée",
    queue: (n: number) => (n ? `${plural(n, "extrait", "extraits")} en attente d'envoi` : "Tout est envoyé"),
    offline: "Hors connexion : les extraits attendent le réseau, les fiches restent consultables.",
    sttDown: "Transcription indisponible : tapez les affirmations que vous entendez.",
    end: "Terminer l'émission",
    ending: "Fin…",
    endConfirm: "Terminer l'émission ? L'enregistrement s'arrête et le bilan s'ouvre.",
    reconnect: "Reprendre le son",
    transcript: "Ce qui est dit",
    transcriptEmpty: "La transcription apparaît ici toutes les dix secondes.",
    transcriptMg: "Émission en malgache : pas de transcription automatique.",
    flags: "Affirmations repérées",
    flagsEmpty: "Aucune affirmation vérifiable repérée pour l'instant.",
    pending: (n: number) => plural(n, "à décider", "à décider"),
    speakers: "Qui parle ?",
    nobody: "Personne en particulier",
    speaking: "parle",
    type: "Ce qui vient d'être dit",
    typeLead: "Une phrase, comme un veilleur : Checky la compare aux sources.",
    typePlaceholder: "Il affirme que le tarif augmentera de 40 % en décembre",
    typeMgPlaceholder: "Hoy izy : hiakatra 40 % ny saran-jiro amin'ny desambra",
    dictate: "Dicter",
    dictating: "J'écoute…",
    transcribing: "Transcription…",
    add: "Comparer",
    adding: "Comparaison…",
    queued: "Gardée hors connexion, envoyée au retour du réseau.",
    nearby: "Fiches proches dans ce navigateur (hors connexion)",
    nearbyNone: "Aucune fiche proche dans ce navigateur.",
    watched: (w: string) => `Mot surveillé à l'antenne : ${w}`,
    modeCautious: "Mode prudent : rien n'arrive au présentateur sans vous.",
  },

  flag: {
    kinds: {
      consistent: "Conforme",
      contradicted: "Contredit",
      no_source: "Aucune source trouvée",
    } as Record<string, string>,
    noSourceNote: "Ce n'est pas un verdict : rien de ce que la rédaction a sous la main n'en parle.",
    figureConsistent: (title: string, official: string) => `Conforme à « ${title} » : ${official}`,
    figureContradicted: (title: string, official: string) => `Contredit par « ${title} » : ${official}`,
    registryConsistent: (who: string, n: string | null) => `Conforme au communiqué ${n ? `N° ${n} ` : ""}de ${who}`,
    registryContradicted: (who: string, n: string | null) => `Contredit par le communiqué ${n ? `N° ${n} ` : ""}de ${who}`,
    registryRelated: (who: string, n: string | null) => `À lire : le communiqué ${n ? `N° ${n} ` : ""}de ${who}`,
    registryNone: "Rien au registre",
    changed: (a: string, b: string) => `« ${a} » au registre, « ${b} » à l'antenne`,
    verdictConsistent: (ref: string) => `Conforme au verdict signé ${ref}`,
    verdictContradicted: (ref: string) => `Contredit par le verdict signé ${ref}`,
    verdictNoted: (ref: string) => `Déjà vérifié : ${ref}`,
    source: (name: string, date: string) => (date ? `${name}, ${date}` : name),
    old: "chiffre de plus de deux ans",
    origin: { code: "repérée par Checky", model: "repérée par la lecture de Checky", typed: "tapée par la régie" } as Record<string, string>,
    status: { pending: "À décider", sent: "Envoyée au présentateur", dismissed: "Écartée" } as Record<string, string>,
    send: "Envoyer au présentateur",
    sending: "Envoi…",
    dismiss: "Écarter",
    question: "Question de relance",
    questionLead: "Le présentateur la voit en grand, sous l'affirmation.",
    confirmSend: "Envoyer",
    sent: "Envoyée au présentateur.",
    failed: "Action impossible. Réessayez.",
    speaker: "Intervenant",
    moveTo: "Attribuer à",
  },

  // Follow-up questions written by code from the flag (the producer edits them before sending).
  questions: {
    figure: (official: string, source: string, claimed: string) =>
      `Le chiffre officiel est ${official} (${source}). D'où vient le chiffre de ${claimed} ?`,
    registry: (who: string) => `Le communiqué de ${who} dit autre chose : pouvez-vous préciser votre source ?`,
    verdict: (ref: string) => `Cette information a été vérifiée (${ref}). Sur quoi vous appuyez-vous ?`,
    consistent: (source: string) => `${source} le confirme : à partir de quand cela s'applique-t-il ?`,
    noSource: "Sur quelle source vous appuyez-vous ?",
  },

  presenter: {
    title: "Écran du présentateur",
    waiting: "Rien pour l'instant. La régie vous envoie les points à relancer.",
    ask: "Relancer",
    back: "Retour à la régie",
    ended: "Émission terminée.",
    live: "Direct",
  },

  debate: {
    title: "Mode débat",
    lead: "Affirmations vérifiables par intervenant. Des comptes, jamais une note ni un classement.",
    line: (n: number, c: number) =>
      `${plural(n, "affirmation vérifiable", "affirmations vérifiables")}, ${plural(c, "contredite par une source officielle", "contredites par une source officielle")}`,
    consistent: (n: number) => plural(n, "conforme", "conformes"),
    noSource: (n: number) => `${n} sans source trouvée`,
    unassigned: "Non attribuées",
  },

  bilan: {
    title: "Bilan de l'émission",
    lead: (n: number, sent: number) =>
      `${plural(n, "affirmation repérée", "affirmations repérées")}, ${plural(sent, "envoyée", "envoyées")} au présentateur.`,
    aired: (date: string, duration: string) => `Diffusée le ${date}, ${duration}`,
    listen: (at: string) => `Écouter à ${at}`,
    noClip: "Pas d'extrait sonore gardé",
    follow: "Suivre dans le desk",
    following: "Création du dossier…",
    followed: (ref: string) => `Dossier ${ref} ouvert, l'extrait en première source.`,
    openDossier: (ref: string) => `Ouvrir ${ref}`,
    followFailed: "Impossible d'ouvrir le dossier.",
    transcript: "Transcription complète",
    noClaims: "Aucune affirmation repérée pendant cette émission.",
    evidence: "Ce qui a été comparé",
  },
};
