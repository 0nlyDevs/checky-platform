// What the Studio routes return (app/modules/studio.py). Kept beside the screens that read them.
import type { FlagKind } from "./flag";
import type { Verdict } from "@checky/shared";

export type Speaker = { id: string; name: string; camp: string | null };

export type ShowBrief = {
  id: string;
  title: string;
  station: string | null;
  topics: string[];
  language: "fr" | "mg";
  status: "draft" | "live" | "ended";
  started_at: string | null;
  ended_at: string | null;
  created_at: string;
  claims: number;
  sent: number;
  is_demo: boolean;
};

export type ClaimOut = {
  id: string;
  at_s: number;
  end_s: number | null;
  text: string;
  speaker_id: string | null;
  origin: "code" | "model" | "typed";
  spotted: Record<string, unknown>;
  flag: { kind?: FlagKind; evidence?: unknown[] };
  status: "pending" | "sent" | "dismissed";
  question: string | null;
  sent_at: string | null;
  item_id: string | null;
  ref: string | null;
  clip: { url?: string | null; offset_s?: number | null; seconds?: number | null } | null;
};

export type SpeakerCount = {
  speaker_id: string | null;
  name: string | null;
  camp: string | null;
  claims: number;
  contradicted: number;
  contradicted_official: number;
  consistent: number;
  no_source: number;
};

export type ShowOut = ShowBrief & {
  input: "microphone" | "stream";
  mode: string;
  speakers: Speaker[];
  turns: { at_s: number; speaker_id: string }[];
  current_speaker_id: string | null;
  camps: string[];
  ai_enabled: boolean;
  segments: { start: number; end: number; text: string; chunk?: number }[];
  chunks: number;
  duration_s: number;
  claim_list: ClaimOut[];
  by_speaker: SpeakerCount[];
};

export type ChunkResult = {
  stored: boolean;
  transcribed: boolean;
  segments: { start: number; end: number; text: string }[];
  claims: ClaimOut[];
  error?: string | null;
};

export type Pack = {
  show_id: string;
  topics: string[];
  prepared_at: string;
  verdicts: { id: string; ref: string | null; title: string; verdict: Verdict; newsroom: string; own: boolean }[];
  figures: { label: string; value: string; unit: string | null; source_name: string }[];
  registry: { id: string; issuer: string; number: string | null; title: string }[];
};

export type Presenter = {
  show: { id: string; title: string; status: string };
  speakers: Speaker[];
  flags: ClaimOut[];
};
