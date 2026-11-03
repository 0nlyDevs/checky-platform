import type { Item, Verdict } from "@checky/shared";

// Shapes of the rubrique and veille routes (apps/api/app/modules/{rubrique,veille}.py), kept here
// until packages/shared is regenerated with them.

export type Place = { name: string | null; region: string | null; country: string | null; lat: number | null; lng: number | null };

export type Prefs = {
  beats: string[];
  regions: string[];
  language: "fr" | "mg" | "en";
  station: string | null;
  beats_offered: string[];
  regions_offered: string[];
};

export type Checked = { id: string; title: string; verdict: Verdict; newsroom: string; mine: boolean };

export type Kind = "item" | "tip" | "sms" | "clip" | "press";

export type Circulating = {
  id: string;
  kind: Kind;
  title: string;
  at: string;
  place: Place | null;
  station: string | null;
  url: string | null;
  beats: string[];
  item: Item | null;
  item_id: string | null;
  already_checked: Checked | null;
  seasons: string[];
  demo: boolean;
};

export type Season = { name: string; topic: string; note: string; keywords: string[]; until: string; days_to: number | null };

export type Returning = {
  id: string;
  ref: string | null;
  title: string;
  verdict: Verdict;
  year: number;
  seen_on: string;
  newsroom: string;
  mine: boolean;
  public: boolean;
  demo: boolean;
};

export type Meteo = { today: string; today_label: string; country: string; region: string | null; seasons: Season[]; returning: Returning[] };

export type AntenneClip = {
  id: string;
  station: string;
  recorded_at: string;
  source_id: string | null;
  clip_at_s: number | null;
  heard_text: string;
  language: string | null;
  text_from: "veilleur" | "transcript" | "pending";
  demo: boolean;
};

export type AntenneRow = {
  claim: string;
  item_id: string | null;
  ref: string | null;
  status: "new" | "followed" | "checked";
  verdict: Verdict | null;
  reports: number;
  stations: string[];
  regions: string[];
  regions_24h: string[];
  first_at: string;
  latest: AntenneClip;
  clip_ids: string[];
  demo: boolean;
  alert?: AlertRef | null;
  /** « RNA, 07:42, 0:18 »: the station, the time and where the passage starts. */
  credit?: string | null;
  audio_url?: string | null;
};

/** The open alert a rumour's reports belong to (app/modules/alerts.py). */
export type AlertRef = { id: string; ref: string | null; level: string; reports: number };

export type AlertMember = {
  key: string;
  kind: string;
  title: string;
  excerpt: string;
  at: string;
  region: string | null;
  place: string | null;
  station: string | null;
  item_id: string | null;
  url: string | null;
  risk: string;
  demo: boolean;
};

export type Alert = {
  id: string;
  ref: string | null;
  title: string;
  state: "open" | "closed";
  level: string;
  code_level: string | null;
  override: { level: string; reason: string; by: string; at: string } | null;
  reasons: { kind: string; quote: string }[];
  facts: { reports: number; kinds: Record<string, number>; stations: string[]; regions: string[]; first_at: string | null; last_at: string | null; hours: number | null };
  members: AlertMember[];
  excluded: string[];
  closed: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  demo: boolean;
};

export type ContactCard = {
  id: string;
  name: string;
  role: string;
  institution: string;
  topics: string[];
  phone: string | null;
  whatsapp: string | null;
  email: string | null;
  website: string | null;
  region: string | null;
  verified: boolean;
  is_demo: boolean;
};

export type FigureCard = {
  id: string;
  topic: string;
  label: string;
  value: string;
  unit: string | null;
  as_of: string | null;
  source_name: string;
  source_url: string | null;
  age_days: number | null;
  old: boolean;
  is_demo: boolean;
};

export type FactKind = "claim" | "verdict" | "season" | "question" | "figure" | "missing";
export type Fact = { n?: number; kind: FactKind; label: string; item_id?: string | null };

export type AngleCard = {
  title: string;
  why: string;
  rests_on: Fact[];
  missing_figure: string | null;
  item_id: string | null;
  ref: string | null;
  kind: "kept" | "piste";
};

export type Rubrique = {
  today: string;
  today_label: string;
  beats: string[];
  regions: string[];
  prefs: Prefs;
  circulating: Circulating[];
  mine: Item[];
  to_sign: Item[];
  contacts: ContactCard[];
  figures: FigureCard[];
  angles: AngleCard[];
  meteo: Meteo;
  antenne: AntenneRow[];
};

export type Angle = { title: string; why: string; rests_on: Fact[]; missing_figure: string | null };
export type AnglesOut = { topic: string; angles: Angle[]; facts: Fact[]; dropped: number; model: string | null };

export type DocumentRow = {
  id: string;
  title: string;
  kind: string;
  status: string;
  doc_type: string;
  issuer: string | null;
  url: string | null;
  published_at: string | null;
  created_at: string;
  item_id: string | null;
  excerpt: string;
  beats: string[];
  communique: { id: string; issuer: string; number: string | null; issued_on: string | null } | null;
  demo: boolean;
};

export type Signal = { id: string; word: string; active: boolean; hits: number; created_at: string };

export type FeedEntry = {
  id: string;
  kind: Exclude<Kind, "item">;
  title: string;
  text: string;
  at: string;
  place: Place | null;
  station: string | null;
  url: string | null;
  item_id: string | null;
  ref: string | null;
  status: string;
  beats: string[];
  risk: string | null;
  already_checked: Checked | null;
  demo: boolean;
};

export type FeedOut = { entries: FeedEntry[]; counts: Partial<Record<FeedEntry["kind"], number>>; since: string; feeds_configured: boolean; streams_configured: boolean };

export type RegionCount = { region: string; country?: string | null; lat: number | null; lng: number | null; last_24h: number; last_7d: number; high_risk: number; kinds: Record<string, number> };
export type MapOut = { regions: RegionCount[]; unplaced: number; total: number; country: string; home: string; countries: { country: string; last_7d: number }[] };

export type Served = { item_id: string; ref: string | null; title: string; status: string; verdict: Verdict | null; signed_at: string | null; truth_routes: number };

export type Clip = {
  id: string;
  station: string;
  heard_text: string;
  text_from: "veilleur" | "transcript" | "pending";
  language: string | null;
  recorded_at: string;
  source_id: string | null;
  item_id: string | null;
  location: Record<string, unknown> | null;
  origin: string;
  status: string;
  clip_at_s: number | null;
  created_by: string;
  created_at: string;
  demo: boolean;
  served: Served | null;
};

export type FollowOut = { item_id: string; ref: string | null; created: boolean; clip_ids: string[] };
