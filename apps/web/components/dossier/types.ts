import type { Item, Verdict } from "@fanilo/shared";
import { dateFormat } from "@/lib/i18n/live";

// Everything the crew stores on an item is optional: older dossiers, Mode sans IA and partial runs
// leave fields out. These readers turn `item.data` into typed values without ever throwing.

type Obj = Record<string, unknown>;

export const obj = (v: unknown): Obj | null => (v && typeof v === "object" && !Array.isArray(v) ? (v as Obj) : null);
export const str = (v: unknown): string | null => (typeof v === "string" && v.trim() ? v : null);
export const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
export const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const objs = (v: unknown): Obj[] => list(v).map(obj).filter((x): x is Obj => x !== null);

const VERDICTS = ["true", "misleading", "false", "unverifiable"] as const;
export const asVerdict = (v: unknown): Verdict | null => (VERDICTS.includes(v as Verdict) ? (v as Verdict) : null);

export type Link = { name: string; url: string };

export type Provenance = {
  firstSeen: string | null;
  daysOld: number | null;
  signals: string[];
  reverse: Link[];
  oldMedia: boolean;
};

export type DiffPart = { op: string; a: string; b: string };
export type Registry = { status: string; issuer: string | null; number: string | null; summary: string | null; diff: DiffPart[]; url: string | null };

export type Figure = {
  claimed: string;
  context: string | null;
  verdict: string;
  official: { label: string; value: string; asOf: string | null; source: string | null; url: string | null; old: boolean } | null;
};

export type Review = { publisher: string; url: string; rating: string | null; date: string | null; title: string | null };
export type Published = { id: string | null; ref: string | null; title: string; verdict: Verdict | null; newsroom: string; at: string | null };
export type Tone = { level: string; signals: { kind: string; quote: string }[] };
export type Credibility = { domain: string | null; name: string | null; signals: { key: string; status: string; detail: string | null }[] };

export type Research = {
  provenance: Provenance | null;
  registry: Registry | null;
  figures: Figure[];
  reviews: Review[];
  published: Published[];
  tone: Tone | null;
  credibility: Credibility | null;
};

function links(v: unknown): Link[] {
  return objs(v)
    .map((l) => ({ name: str(l.name) ?? str(l.label) ?? "", url: str(l.url) ?? "" }))
    .filter((l) => l.name && /^https?:\/\//.test(l.url));
}

function provenance(v: unknown): Provenance | null {
  const p = obj(v);
  if (!p) return null;
  const signals = list(p.signals)
    .map((s) => (typeof s === "string" ? s : str(obj(s)?.detail)))
    .filter((s): s is string => Boolean(s));
  const out = {
    firstSeen: str(p.first_seen),
    daysOld: num(p.days_old),
    signals,
    reverse: links(p.reverse_links),
    oldMedia: p.verdict_hint === "old_media_new_caption",
  };
  return out.firstSeen || out.signals.length || out.reverse.length || out.oldMedia ? out : null;
}

function registry(v: unknown): Registry | null {
  const r = obj(v);
  const status = str(r?.status);
  // « none »: no institution was named, nothing to compare.
  if (!r || !status || status === "none") return null;
  const communique = obj(r.communique);
  return {
    status,
    issuer: str(r.issuer),
    number: str(r.number),
    summary: str(r.summary),
    diff: objs(r.diff).map((d) => ({ op: str(d.op) ?? "equal", a: typeof d.a === "string" ? d.a : "", b: typeof d.b === "string" ? d.b : "" })),
    url: str(communique?.url) ?? str(communique?.public_url),
  };
}

function figures(v: unknown): Figure[] {
  return objs(v)
    .filter((f) => str(f.claimed))
    .map((f) => {
      const o = obj(f.figure);
      const value = o ? [o.value, o.unit].filter((x) => x !== null && x !== undefined && x !== "").join(" ") : "";
      return {
        claimed: String(f.claimed),
        context: str(f.context),
        verdict: str(f.verdict) ?? "no_figure",
        official: o
          ? {
              label: str(o.label) ?? "",
              value,
              asOf: str(o.as_of),
              source: str(o.source_name),
              url: str(o.source_url),
              old: o.old === true,
            }
          : null,
      };
    });
}

export function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function reviews(v: unknown): Review[] {
  return objs(v)
    .filter((r) => /^https?:\/\//.test(str(r.url) ?? ""))
    .map((r) => ({
      publisher: str(r.publisher) ?? hostOf(String(r.url)),
      url: String(r.url),
      rating: str(r.rating),
      date: str(r.date),
      title: str(r.title),
    }));
}

function published(...sources: unknown[]): Published[] {
  const seen = new Set<string>();
  const out: Published[] = [];
  for (const source of sources) {
    for (const p of objs(source)) {
      const newsroom = str(p.newsroom) ?? str(obj(p.newsroom)?.name);
      const title = str(p.title);
      if (!newsroom || !title) continue;
      const key = `${newsroom}|${title}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ id: str(p.id), ref: str(p.ref), title, verdict: asVerdict(p.verdict), newsroom, at: str(p.published_at) });
    }
  }
  return out;
}

function tone(v: unknown): Tone | null {
  const t = obj(v);
  const level = str(t?.level);
  if (!t || !level) return null;
  return {
    level,
    signals: objs(t.signals)
      .filter((s) => str(s.quote))
      .map((s) => ({ kind: str(s.kind) ?? "", quote: String(s.quote) })),
  };
}

function credibility(v: unknown): Credibility | null {
  const c = obj(v);
  const signals = objs(c?.signals)
    .filter((s) => str(s.key))
    .map((s) => ({ key: String(s.key), status: str(s.status) ?? "unknown", detail: str(s.detail) }));
  if (!c || !signals.length) return null;
  return { domain: str(c.domain), name: str(c.name), signals };
}

export function readResearch(item: Item): Research {
  const r = obj(item.data.research) ?? {};
  return {
    provenance: provenance(r.provenance),
    registry: registry(r.registry),
    figures: figures(r.figures),
    reviews: reviews(r.fact_checks),
    published: published(r.published, r.archives),
    tone: tone(r.tone),
    credibility: credibility(r.credibility),
  };
}

export const hasResearch = (r: Research) =>
  Boolean(r.provenance || r.registry || r.figures.length || r.reviews.length || r.published.length || r.tone || r.credibility);

type Level = "high" | "medium" | "low";
const isLevel = (v: unknown): v is Level => v === "high" || v === "medium" || v === "low";

export type Risk = {
  level: Level;
  reasons: { kind: string; quote: string | null }[];
  /** Checky's own level when a journalist adjusted it (`data.risk_override`). */
  code: Level | null;
  override: { level: Level; reason: string; by: string | null } | null;
};

/** The danger level: a journalist's adjustment wins over Checky's (app/modules/alerts.py). */
export function readRisk(item: Item): Risk | null {
  const r = obj(item.data.risk);
  const o = obj(item.data.risk_override);
  const code = isLevel(r?.level) ? r.level : null;
  const override = o && isLevel(o.level) ? { level: o.level, reason: str(o.reason) ?? "", by: str(o.by) } : null;
  const level = override?.level ?? code;
  if (!level) return null;
  return {
    level,
    code,
    override,
    reasons: list(r?.reasons)
      .map((x) => (typeof x === "string" ? { kind: "", quote: x } : { kind: str(obj(x)?.kind) ?? "", quote: str(obj(x)?.quote) }))
      .filter((x) => x.kind || x.quote),
  };
}

export type Evidence = { n: number | null; title: string; stance: string; quote: string; explanation: string | null; date: string | null };
export type Component = { key: string; points: number; maximum: number; detail: string | null };
export type Confidence = { score: number; level: string; reasons: string[]; missing: string[]; components: Component[] };
export type Reading = {
  verdict: Verdict | null;
  reason: string | null;
  evidence: Evidence[];
  missing: string[];
  confidence: Confidence | null;
  at: string | null;
};

const texts = (v: unknown): string[] =>
  typeof v === "string" ? (v.trim() ? [v.trim()] : []) : list(v).filter((x): x is string => typeof x === "string" && x.trim() !== "");

/** « Lecture de Checky »: the suggested verdict, its reason, the quotes it rests on, the confidence. */
export function readReading(item: Item): Reading | null {
  const a = obj(item.data.analysis);
  const verdict = asVerdict(item.data.verdict_suggested) ?? asVerdict(a?.verdict);
  if (!a && !verdict) return null;
  const c = obj(a?.confidence);
  const score = num(c?.score);
  return {
    verdict,
    reason: str(a?.reason),
    evidence: objs(a?.evidence)
      .filter((e) => str(e.quote))
      .map((e) => ({
        n: num(e.n),
        title: str(e.source_title) ?? str(e.title) ?? "",
        stance: str(e.stance) ?? "context",
        quote: String(e.quote),
        explanation: str(e.explanation),
        date: str(e.source_date),
      })),
    missing: texts(a?.missing),
    confidence:
      c && score !== null
        ? {
            score: Math.round(score),
            level: str(c.level) ?? "",
            reasons: texts(c.reasons),
            missing: texts(c.missing),
            components: objs(c.components)
              .filter((x) => str(x.key))
              .map((x) => ({ key: String(x.key), points: num(x.points) ?? 0, maximum: num(x.maximum) ?? 0, detail: str(x.detail) })),
          }
        : null,
    at: str(a?.at),
  };
}

export type Byline = { newsroom: string; journalist: string; signedAt: string };

export function readByline(item: Item): Byline | null {
  const b = obj(item.data.byline);
  const newsroom = str(b?.newsroom);
  const journalist = str(b?.journalist);
  const signedAt = str(b?.signed_at) ?? str(item.data.signed_at);
  return newsroom && journalist && signedAt ? { newsroom, journalist, signedAt } : null;
}

// --- API shapes (slice B routes) -----------------------------------------------------------

export type Stop = {
  id: string | null;
  side: "rumour" | "truth";
  channel: string;
  place: string;
  location: { region?: string | null; name?: string | null; scope?: string | null } & Obj;
  status: string;
  proof: Obj;
  at: string;
  auto: boolean;
  added_by: string;
  derived: boolean;
};
export type Gap = { channel: string; place: string; location: Obj; rumour_stop_id: string | null };
export type Trajet = { rumour: Stop[]; truth: Stop[]; gaps: Gap[]; covered: number; summary: string };

export type Formats = {
  card: { fr: string | null; mg: string | null };
  radio_line: string;
  flash: string;
  sms: string;
  text: string;
  institution_alert: string;
  permalink: string;
  short_link: string | null;
  poster: {
    title: string;
    verdict: Verdict;
    verdict_word: string;
    verdict_word_mg: string;
    reason: string;
    newsroom: string;
    ref: string | null;
    date: string | null;
    qr_url: string;
    short_link: string | null;
    number?: number | null;
    /** « vérification 145 »: the same number on the card, the radio line, the SMS and /v/145. */
    check_label?: string | null;
    sealed?: boolean;
  };
  number?: number | null;
  check_label?: string | null;
  mg: Record<string, string> | null;
  written_by: "ai" | "template";
  gaps: Gap[];
  /** Fingerprint of the Malagasy strings shown: « Relu en malgache » vouches for these exactly. */
  mg_hash: string | null;
  relu_mg: { by: string; name: string; at: string; mg_hash: string | null; current: boolean } | null;
};

export type Contact = {
  id: string;
  name: string;
  kind: string;
  role: string;
  institution: string;
  topics: string[];
  languages: string[];
  location: Obj;
  phone: string | null;
  whatsapp: string | null;
  email: string | null;
  website: string | null;
  official_pages: { kind?: string; url: string; verified?: boolean }[];
  hours: string | null;
  shared: boolean;
  verified_at: string | null;
  verified_by: string | null;
  stats: { asked?: number; answered?: number; last_answer_hours?: number } & Obj;
  is_demo: boolean;
  own: boolean;
};

export type Question = {
  id: string;
  contact_id: string | null;
  contact: string | null;
  institution: string | null;
  channel: string;
  question: string;
  answer_url: string;
  message: string;
  links: Record<string, string>;
  sent_at: string | null;
  answered_at: string | null;
  answer: { stance?: string; text?: string; name?: string } | null;
  source_id: string | null;
};

export type Who = {
  points: { point: string | null; contacts: { contact: Contact; why: string[]; track: string | null; question: string; score: number }[] }[];
  beats: string[];
  place: Obj | null;
  questions: Question[];
};

export type Carnet = {
  newsroom: string;
  item_id: string;
  ref: string | null;
  title: string;
  status: string;
  first_seen_at: string | null;
  verdict: Verdict | null;
  verdict_suggested: Verdict | null;
  reason: string | null;
  byline: { newsroom?: string; journalist?: string; signed_at?: string } | null;
  generated_at: string;
  entries: { at: string; kind: string; actor: string; text: string }[];
  sources: { id: string; title: string; kind: string; url: string | null; published_at: string | null; added_at: string; added_by: string }[];
  questions: { contact: string | null; institution: string | null; channel: string; sent_at: string | null; answered_at: string | null; stance: string | null }[];
  checks: number;
  routes: Record<string, number>;
};

export type Attestation = {
  summary: string;
  payload: Obj;
  sha256: string;
  signature: string;
  key_id: string;
  public_key: string;
  issued_at: string;
};

export type NewsroomSettings = { id: string; name: string; slug: string; is_public: boolean; settings?: { ai_enabled: boolean } };

// --- dates, in French, on the reader's clock -------------------------------------------------

const dayFmt = dateFormat({ day: "numeric", month: "long", year: "numeric" });
const dayTimeFmt = dateFormat({ day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });
const shortFmt = dateFormat({ day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

function parse(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  // A bare calendar day is a day, not midnight UTC.
  const d = new Date(/^\d{4}-\d{2}-\d{2}$/.test(iso) ? `${iso}T12:00:00` : iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

export const fmtDay = (iso: string | null | undefined) => {
  const d = parse(iso);
  return d ? dayFmt.format(d) : null;
};
export const fmtWhen = (iso: string | null | undefined) => {
  const d = parse(iso);
  return d ? dayTimeFmt.format(d) : null;
};
export const fmtShort = (iso: string | null | undefined) => {
  const d = parse(iso);
  return d ? shortFmt.format(d) : null;
};
