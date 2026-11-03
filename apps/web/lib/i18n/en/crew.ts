// English for the crew slice on Check (mirrors fr/crew.ts). Machine-drafted, to be reread.
import type { Overrides } from "../index";

const days = (n: number) => (n === 1 ? "1 day" : `${n} days`);
const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

export const crew: NonNullable<Overrides["crew"]> = {
  // the live log: the crew racing
  live: {
    title: "Checky's crew",
    running: "Live",
    done: "Finished",
    legend: "Solid line: a fact found by the code. Dotted: a reading by an AI model.",
    fact: "fact",
    model: "AI",
    again: "rerun",
    seconds: (ms: number) => `${(ms / 1000).toFixed(1)} s`,
    stages: { read: "Reading", facts: "The facts, in parallel", reading: "The reading" } as Record<string, string>,
    status: {
      waiting: "Waiting",
      running: "Running",
      done: "Done",
      failed: "Failed",
      timeout: "Timed out",
      skipped: "Not applicable",
      no_ai: "AI off",
    } as Record<string, string>,
    names: {
      Lecteur: "Reader",
      Provenance: "Provenance",
      Registre: "Registry",
      Chiffres: "Figures",
      "Fact-checkers": "Fact-checkers",
      Web: "Web",
      Archives: "Archives",
      Fiabilité: "Reliability",
      Ton: "Tone",
      Éléments: "Evidence",
      Synthèse: "Synthesis",
      Contradicteur: "Challenger",
      Confiance: "Confidence",
    } as Record<string, string>,
    roles: {
      Lecteur: "Picks out the claims, figures and places",
      Provenance: "Dates the image, video or page",
      Registre: "Compares with the original statement",
      Chiffres: "Compares with the official figures",
      "Fact-checkers": "Looks for verdicts already published",
      Web: "Searches and reads pages",
      Archives: "Searches the newsroom's sources",
      Fiabilité: "Looks at what the site says about itself",
      Ton: "Measures the message's tone",
      Éléments: "Numbers what was found",
      Synthèse: "Suggests a reading",
      Contradicteur: "Looks for the flaw",
      Confiance: "Works out how solid it is",
    } as Record<string, string>,
  },
  noLecture: {
    no_ai: "No AI: no reading",
    no_evidence: "No reading: too little evidence read",
    ai_failed: "No reading: the AI models did not answer",
  } as Record<string, string>,

  // "No AI" for one run
  noAi: {
    label: "No AI",
    hint: "For this check: facts only, no reading by a model.",
    newsroomOff: "AI is off for the whole newsroom (Settings): facts only.",
  },

  // the facts, first
  facts: {
    title: "The facts",
    lead: "What the code found, with no interpretation. Read this before Checky's reading.",
    none: "No facts found for this message. The reading, if there is one, rests on the web.",
    notChecked: "Not checked this time",
  },
  provenance: {
    title: "Provenance",
    first: (date: string) => `Earliest dated trace: ${date}`,
    basis: {
      exif: "date taken (EXIF)",
      video: "video creation date",
      published: "publication date",
    } as Record<string, string>,
    ago: (n: number) => (n === 0 ? "today" : `${days(n)} ago`),
    hint: "Old image, new caption: the content is circulating again, presented as current.",
    noTrace: "No trace of an AI generator in the file: that proves nothing.",
    reverse: "Reverse search",
  },
  registry: {
    title: "Registry of originals",
    contacts: "Can confirm",
    open: "See the original",
  },
  figures: {
    title: "Official figures",
    claimed: "Claimed",
    official: "Official figure",
    verdict: { matches: "Matches", differs: "Differs", no_figure: "No official figure" } as Record<string, string>,
    asOf: (date: string) => `as of ${date}`,
    old: "old figure",
  },
  factChecks: {
    title: "Fact-checkers",
    by: (who: string, date?: string | null) => (date ? `Checked by ${who} on ${date}` : `Checked by ${who}`),
    rating: (rating: string) => `Their conclusion: “${rating}”`,
    note: "Their verdict, passed on as is, with its link.",
  },
  published: {
    title: "Already checked",
    by: (newsroom: string) => `Already checked by ${newsroom}`,
    open: "See the verdict",
  },
  archives: {
    title: "In our archives",
    open: "Open the case",
  },
  undated: "unknown date",
  recheck: "Targeted search",

  // the reading, dashed
  lecture: {
    title: "Checky's reading",
    by: "Suggested by AI from the numbered evidence, for the newsroom to confirm.",
    level: { eleve: "High", moyen: "Medium", faible: "Low" } as Record<string, string>,
    score: (score: number, level: string) => `${score}% · ${level}`,
    scoreLabel: "Strength of the evidence",
    meaning: "This percentage measures how solid the evidence is, not how likely the claim is to be true. It is worked out by the code, never by the model.",
    reasons: "Why",
    missing: "Missing",
    restsOn: "It cites",
    dates: "The dates",
    rumour: (date: string) => `Rumour dated ${date}`,
    before: (n: number) => (n <= 0 ? "same day or later" : `${days(n)} before the rumour`),
    downgraded: "The only confirmations are more than 30 days older than the rumour: the reading becomes “Unverifiable”.",
    oldEvidence: "All the deciding evidence is more than 30 days older than the rumour.",
    how: "How it is worked out",
    howLead: "Six criteria, 100 points. Each limit the Challenger raises takes off 5 points (15 at most).",
    components: {
      agreement: "Sources agree",
      official: "Official source",
      dates: "Dates",
      outside: "Outside source",
      attached: "Kept by the newsroom",
      hosts: "Separate origins",
      critique: "Challenger",
    } as Record<string, string>,
    points: (points: number, maximum: number) => (maximum ? `${points} / ${maximum}` : `${points}`),
    critique: "The Challenger notes",
    recheck: (query: string, n: number) => `Targeted search rerun: “${query}” · ${plural(n, "result", "results")}`,
    noCritic: "The critical review did not finish: read the evidence before using this reading.",
    factsOnly: "Strength of the evidence, no AI",
    factsOnlyLead: "Worked out by the code from the facts above. It is not a conclusion: that is the journalist's call.",
    direction: {
      supports: "The evidence supports the claim",
      contradicts: "The evidence contradicts the claim",
      mixed: "The evidence conflicts",
      none: "No evidence settles it",
    } as Record<string, string>,
  },

  // what the site says about itself
  reliability: {
    title: "Source reliability",
    lead: "What the site shows about itself: signals, never a score.",
    status: { found: "Found", missing: "Not found", unknown: "Unknown" } as Record<string, string>,
    keys: {
      author: "Author",
      date: "Date",
      about: "“About” page",
      contact: "Contact",
      legal: "Legal notice",
      corrections: "Corrections policy",
      https: "Encrypted connection",
      domain_age: "Domain age",
      fact_checker: "Recognised fact-checker",
      official: "Official site",
      press: "Declared media outlet",
    } as Record<string, string>,
    known: { fact_checker: "Recognised fact-checker", official: "Official site", press: "Known media outlet" } as Record<string, string>,
    platform: (name: string) => `Posted on ${name}: the network says nothing about the source, only the displayed author counts.`,
  },

  // how it is written, and how urgent it is to check
  tone: {
    title: "Message tone",
    level: { sensationnaliste: "Sensationalist", marqué: "Loaded", neutre: "Neutral" } as Record<string, string>,
    kinds: {
      urgency: "Urgency",
      share: "Call to share",
      emotive: "Loaded word",
      hidden: "“They're hiding it from you”",
      caps: "Capitals",
      exclamations: "Exclamation marks",
      emoji: "Alarm emoji",
    } as Record<string, string>,
    note: "Tone does not say whether it is true: it says how the message tries to spread.",
    framing: "Framing spotted by AI",
    framingKinds: {
      political_framing: "Political framing",
      loaded_language: "Loaded language",
      clickbait: "Clickbait hook",
      opinion_as_fact: "Opinion presented as fact",
    } as Record<string, string>,
  },
  risk: {
    label: { high: "High risk", medium: "Medium risk", low: "Low risk" } as Record<string, string>,
    kinds: {
      violence: "Call to violence",
      accusation: "Accusation against a person",
      panic: "Could cause panic",
      fake_order: "Poses as an official order",
    } as Record<string, string>,
    note: "Risk says how urgent the check is, not what is true.",
  },

  // who sees what
  strip: {
    label: "What the public sees",
    already: "Already public",
    alreadyValue: (checks: number, verdicts: number) =>
      [checks ? plural(checks, "fact-checker verdict", "fact-checker verdicts") : "", verdicts ? plural(verdicts, "published verdict", "published verdicts") : ""]
        .filter(Boolean)
        .join(", ") || "nothing found here",
    after: "After you sign",
    afterValue: "the verdict, its reason and its sources",
    never: "Never",
    neverValue: "the reading, the percentage, this case",
  },

  contact: "Who can prove it?",
  contactHelp: "The newsroom's contacts and their fields of expertise.",
  openDirectory: "Open the directory",
};
