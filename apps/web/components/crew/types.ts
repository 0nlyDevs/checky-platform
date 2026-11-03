import type { Verdict } from "@checky/shared";
import type { MatchResult } from "@/components/registre/types";
import { getLang, locale } from "@/lib/i18n/live";

/** One crew member reporting through the `agent` event of `POST /workspaces/{ws}/crew`. */
export type AgentEvent = {
  agent: string;
  stage?: string;
  status: "waiting" | "running" | "done" | "failed" | "timeout" | "skipped" | "no_ai";
  llm?: boolean;
  summary?: string;
  ms?: number;
  count?: number;
};

export type Stance = "supports" | "contradicts" | "context";

/** Every fact as a numbered element (web results, reviews, registry, figures, archives…). */
export type Numbered = {
  n: number;
  kind: string;
  title: string;
  url: string;
  snippet?: string;
  date?: string | null;
  read_status?: string;
  passages?: string[];
  publisher?: string;
  rating?: string | null;
  status?: string;
  claimed?: string;
  verdict?: string;
  source_id?: string;
  item_id?: string | null;
};

export type Provenance = {
  first_seen: string | null;
  first_seen_basis: string | null;
  days_old: number | null;
  signals: { kind: string; detail: string }[];
  reverse_links: { name: string; url: string }[];
  verdict_hint: string | null;
  no_trace: boolean;
};

export type FigureCheck = {
  claimed: string;
  context?: string;
  figure: {
    label: string;
    value: string | number;
    unit?: string | null;
    as_of?: string | null;
    source_name?: string | null;
    source_url?: string | null;
    age_days?: number | null;
    old?: boolean;
  } | null;
  verdict: "matches" | "differs" | "no_figure";
  summary?: string;
};

export type Review = { publisher: string; url: string; rating: string | null; date: string | null; title: string; snippet?: string };

export type Published = {
  id: string;
  ref?: string | null;
  title: string;
  verdict: Verdict;
  reason?: string | null;
  newsroom: string;
  newsroom_slug?: string;
  published_at: string;
};

export type Archive = { source_id: string; item_id: string | null; title: string; text: string; url?: string | null; published_at?: string | null; kind?: string };

export type Confidence = {
  score: number;
  level: "eleve" | "moyen" | "faible";
  direction: "supports" | "contradicts" | "mixed" | "none";
  reasons: string[];
  missing: string[];
  components: { key: string; points: number; maximum: number; detail: string }[];
  computed_at: string;
};

export type Analysis = {
  verdict: Verdict;
  reason: string;
  missing: string;
  evidence: {
    n: number;
    result: number;
    stance: Stance;
    quote: string;
    source_title: string;
    url?: string | null;
    kind?: string;
    source_date: string | null;
    days_before: number | null;
  }[];
  date_check: "downgraded" | "old_evidence" | null;
  first_seen: string;
  confidence?: Confidence;
  [key: string]: unknown;
};

export type Credibility = {
  domain: string;
  host: string;
  url: string;
  platform: string | null;
  known: "fact_checker" | "official" | "press" | null;
  name: string | null;
  signals: { key: string; status: "found" | "missing" | "unknown"; detail?: string | null }[];
};

export type Tone = { level: string; signals: { kind: string; quote: string }[] };
export type Risk = { level: "high" | "medium" | "low"; reasons: { kind: string; quote: string }[] };
export type Framing = { kind: string; quote: string; explanation: string; target: string };
export type Critique = { result: number; quote: string; why: string };

/** The `result` event: the facts, then the reading when there is one. */
export type CrewResult = {
  url: string | null;
  platform: string | null;
  kind?: "page" | "post" | "image" | "text" | "video";
  title?: string;
  site?: string | null;
  author?: string | null;
  published_at?: string | null;
  days_old?: number | null;
  excerpt?: string;
  summary?: string;
  claims?: string[];
  signals?: { type: string; quote: string; why: string }[];
  results?: Numbered[];
  numbered?: Numbered[];
  archives?: Archive[];
  published?: Published[];
  analysis?: Analysis;
  confidence?: Confidence;
  framing?: Framing[];
  registry?: MatchResult;
  figures?: FigureCheck[];
  fact_checks?: Review[];
  provenance?: Provenance;
  credibility?: Credibility;
  tone?: Tone;
  risk?: Risk;
  critique?: Critique[];
  recheck?: { query: string; results: Numbered[] };
  trace?: AgentEvent[];
  reverse_search?: { name: string; url: string }[];
  age?: {
    oldest: { date: string; title: string; url: string; days_before: number | null } | null;
    newest: { date: string; title: string; url: string; days_before: number | null } | null;
    count: number;
    rumour: string;
  };
  gestures?: { kind: string; status: string; text: string; subject: string; proof: Record<string, unknown> }[];
  ai_enabled?: boolean;
  newsroom_ai?: boolean;
  tracked?: { item_id: string; ref: string | null; title: string } | null;
  needs_text?: boolean;
};

/** A date from the API (YYYY-MM-DD or a full ISO moment) in the desk's language, or null. */
export function frDate(value?: string | null): string | null {
  if (!value) return null;
  const d = new Date(value.length === 10 ? `${value}T00:00:00Z` : value);
  if (Number.isNaN(d.getTime())) return null;
  const said = d.toLocaleDateString(locale(), { day: "numeric", month: "long", year: "numeric", timeZone: value.length === 10 ? "UTC" : "Indian/Antananarivo" });
  return getLang() === "fr" ? said.replace(/^1 /, "1er ") : said; // « 1er novembre », as the API's own dates read
}

export function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
