"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { IconArrowLeft, IconCircleNotch, IconMicrophone, IconPaperclip, IconPaperPlaneTilt, IconSealCheck, IconStop } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { VerdictChip } from "@/components/claims/verdict";
import { DemoTag, when } from "@/components/rubrique/bits";
import type { Clip, Prefs } from "@/components/rubrique/types";
import { useMe } from "@/components/rubrique/use-me";
import { api, API_URL, ApiError, fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/live";
import { cn } from "@/lib/utils";
import { PillTabs } from "@/components/ui/pill-tabs";

const w = t.rubrique.veilleur;
const MAX_SECONDS = 60;
type Lang = "mg" | "fr";
type Upload = { file_id: string; upload_url: string; headers: Record<string, string> };

// Per-device conveniences only: the station and language last used, and the stations typed before.
const STATION = "checky:antenne:station";
const STATIONS = "checky:antenne:stations";
const LANG = "checky:antenne:lang";

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* private mode: nothing remembered */
  }
}

function pickMime() {
  return ["audio/webm;codecs=opus", "audio/webm", "audio/ogg", "audio/mp4"].find((m) => MediaRecorder.isTypeSupported?.(m)) ?? "";
}

/** The passage itself: 60 seconds at most, played back before it is sent. */
function useRecording(onDenied: () => void) {
  const [state, setState] = useState<"idle" | "recording" | "recorded">("idle");
  const [elapsed, setElapsed] = useState(0);
  const [clip, setClip] = useState<{ blob: Blob; url: string; startedAt: Date; seconds: number } | null>(null);
  const rec = useRef<MediaRecorder | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(
    () => () => {
      if (timer.current) clearInterval(timer.current);
      rec.current?.stream.getTracks().forEach((tr) => tr.stop());
    },
    [],
  );

  async function start() {
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      return onDenied();
    }
    const mime = pickMime();
    const mr = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    const chunks: Blob[] = [];
    const startedAt = new Date();
    mr.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    mr.onstop = () => {
      stream.getTracks().forEach((tr) => tr.stop());
      if (timer.current) clearInterval(timer.current);
      const blob = new Blob(chunks, { type: (mr.mimeType || "audio/webm").split(";")[0] });
      const seconds = Math.min(MAX_SECONDS, Math.round((Date.now() - startedAt.getTime()) / 1000));
      setClip({ blob, url: URL.createObjectURL(blob), startedAt, seconds });
      setState("recorded");
    };
    rec.current = mr;
    mr.start(500);
    setElapsed(0);
    setState("recording");
    timer.current = setInterval(() => {
      const s = Math.floor((Date.now() - startedAt.getTime()) / 1000);
      setElapsed(s);
      if (s >= MAX_SECONDS && mr.state === "recording") mr.stop();
    }, 250);
  }

  function stop() {
    if (rec.current?.state === "recording") rec.current.stop();
  }

  function reset() {
    if (clip) URL.revokeObjectURL(clip.url);
    setClip(null);
    setElapsed(0);
    setState("idle");
  }

  return { state, elapsed, clip, start, stop, reset };
}

/** « Qu'avez-vous entendu ? » said aloud: the public transcription fills the box, the veilleur
 *  reads and corrects it before sending. */
function useDictation(lang: Lang, onText: (text: string) => void) {
  const [state, setState] = useState<"idle" | "recording" | "transcribing">("idle");
  const rec = useRef<MediaRecorder | null>(null);

  async function toggle() {
    if (state === "recording") return rec.current?.stop();
    if (state !== "idle") return;
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch {
      return toast.error(w.micDenied);
    }
    const mime = pickMime();
    const mr = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    const chunks: Blob[] = [];
    mr.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    mr.onstop = async () => {
      stream.getTracks().forEach((tr) => tr.stop());
      setState("transcribing");
      try {
        const blob = new Blob(chunks, { type: (mr.mimeType || "audio/webm").split(";")[0] });
        const res = await fetch(`${API_URL}/api/v1/public/transcribe?lang=${lang}`, { method: "POST", headers: { "Content-Type": blob.type }, body: blob });
        if (!res.ok) throw new Error(String(res.status));
        const { text } = (await res.json()) as { text: string };
        if (text.trim()) onText(text.trim());
      } catch {
        toast.error(w.dictationFailed);
      } finally {
        setState("idle");
      }
    };
    rec.current = mr;
    mr.start(250);
    setState("recording");
  }

  return { state, toggle };
}

function put(up: Upload, blob: Blob, onProgress: (f: number) => void) {
  return new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", up.upload_url);
    for (const [k, val] of Object.entries(up.headers)) xhr.setRequestHeader(k, val);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () => (xhr.status < 300 ? resolve() : reject(new Error(`upload ${xhr.status}`)));
    xhr.onerror = () => reject(new Error("upload network"));
    xhr.send(blob);
  });
}

function MyClips({ clips }: { clips: Clip[] }) {
  if (clips.length === 0) return <p className="text-sm text-muted-foreground">{w.mineEmpty}</p>;
  return (
    <ul className="divide-y divide-border">
      {clips.map((c) => (
        <li key={c.id} className="py-3 first:pt-0">
          <p className="flex flex-wrap items-baseline justify-between gap-x-3 text-sm">
            <span className="font-bold">{c.station}</span>
            <span className="text-muted-foreground tabular">{when(c.recorded_at)}</span>
          </p>
          <p className="mt-1 text-pretty">{c.text_from === "pending" ? <span className="text-muted-foreground">{t.rubrique.antenne.pending}</span> : <q className="quote text-lg">{c.heard_text}</q>}</p>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            {w.status[c.served ? "followed" : c.status] ?? c.status}
            {c.demo && <DemoTag />}
          </p>
          {c.served && (
            <div className="mt-2 rounded-md border border-foreground bg-card p-3">
              <p className="inline-flex items-center gap-2 font-bold">
                <IconSealCheck className="size-5" aria-hidden />
                {w.served}
              </p>
              <p className="mt-0.5 text-sm">{w.servedLead(c.served.ref ?? "")}</p>
              {c.served.verdict && <VerdictChip verdict={c.served.verdict} className="mt-2" />}
              {c.served.truth_routes > 0 && <p className="mt-1 text-sm text-muted-foreground">{w.routes(c.served.truth_routes)}</p>}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

type Radio = { id: string; name: string; frequency: string | null };
type Attached = { blob: Blob; url: string; startedAt: Date; seconds: number | null; name: string | null };

const pad = (n: number) => String(n).padStart(2, "0");
const clock = (d: Date) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;

/** « 08:12 » today; a time later than now (by more than 5 minutes) was heard yesterday. */
function heardAt(hhmm: string): Date {
  const [h, m] = hhmm.split(":").map(Number);
  const at = new Date();
  at.setHours(h || 0, m || 0, 0, 0);
  if (at.getTime() - Date.now() > 5 * 60_000) at.setDate(at.getDate() - 1);
  return at;
}

/**
 * « Les dernières minutes »: for partner radios that stream online, Checky will keep the last ten
 * minutes server-side so a journalist can take the passage after hearing it, away from any radio.
 * The buffer is not wired yet: this is the screen, labelled « Aperçu », with nothing pretending.
 */
function Rewind({ radios }: { radios: Radio[] }) {
  const r = w.rewind;
  const [station, setStation] = useState<string | null>(null);
  const [from, setFrom] = useState(270);
  const [to, setTo] = useState(190);
  const start = Math.max(from, to);
  const end = Math.min(from, to);
  const span = (secs: number) => r.ago(Math.floor(secs / 60), secs % 60);
  const pick = station ?? radios[0]?.name ?? null;
  return (
    <section aria-labelledby="rewind" className="mt-10 border-t border-foreground pt-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="rewind" className="font-display text-xl font-bold">
          {r.title}
        </h2>
        <span className="rounded-full border border-dashed border-foreground px-2.5 py-0.5 text-xs font-bold">{r.preview}</span>
      </div>
      <p className="mt-1 text-sm text-pretty text-muted-foreground">{r.lead}</p>
      {radios.length === 0 ? (
        <p className="mt-3 rounded-md border border-dashed border-border p-4 text-sm">{r.noStream}</p>
      ) : (
        <div className="mt-4 space-y-4 rounded-md border border-border bg-card p-4">
          <div role="radiogroup" aria-label={r.pick} className="flex flex-wrap gap-2">
            {radios.map((x) => (
              <button
                key={x.id}
                type="button"
                role="radio"
                aria-checked={pick === x.name}
                onClick={() => setStation(x.name)}
                className={cn(
                  "h-10 rounded-full border px-3.5 text-sm font-bold outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  pick === x.name ? "border-foreground bg-primary text-primary-foreground" : "border-border hover:bg-raised",
                )}
              >
                {x.name}
                {x.frequency && <span className="ml-1 font-normal tabular">{x.frequency}</span>}
              </button>
            ))}
          </div>
          {/* Ten minutes, oldest on the left; the chosen passage is the dark band. */}
          <div aria-hidden className="relative h-12 overflow-hidden rounded-md border border-border bg-background">
            {Array.from({ length: 60 }, (_, i) => (
              <span key={i} className="absolute bottom-0 w-px bg-muted-foreground/40" style={{ left: `${(i / 60) * 100}%`, height: `${20 + ((i * 37) % 60)}%` }} />
            ))}
            <span className="absolute inset-y-0 bg-foreground/20 ring-2 ring-foreground ring-inset" style={{ left: `${((600 - start) / 600) * 100}%`, right: `${(end / 600) * 100}%` }} />
          </div>
          <div className="flex justify-between text-xs text-muted-foreground tabular">
            <span>{r.tenMin}</span>
            <span>{r.now}</span>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="text-sm">
              <span className="font-bold">{r.from}</span> <span className="tabular">{span(start)}</span>
              <input type="range" min={0} max={600} step={5} value={600 - from} onChange={(e) => setFrom(600 - Number(e.target.value))} className="mt-1 w-full accent-foreground" />
            </label>
            <label className="text-sm">
              <span className="font-bold">{r.to}</span> <span className="tabular">{span(end)}</span>
              <input type="range" min={0} max={600} step={5} value={600 - to} onChange={(e) => setTo(600 - Number(e.target.value))} className="mt-1 w-full accent-foreground" />
            </label>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Button type="button" variant="outline" size="lg" disabled>
              <IconPaperclip aria-hidden />
              {r.take}
            </Button>
            <span className="text-sm tabular">{r.length(start - end)}</span>
          </div>
          <p className="text-sm text-pretty text-muted-foreground">{r.previewNote}</p>
        </div>
      )}
    </section>
  );
}

/**
 * « Entendu à la radio » (phone first, about ten seconds): pick the station, keep or correct the
 * time, say in one sentence what was announced, send. An audio extract is optional. It lands in
 * Veille, grouped with the same rumour, and becomes a dossier in one click. In Malagasy the
 * newsroom reads the journalist's own sentence; nothing replaces it with a machine transcript.
 */
export function VeilleurView({ ws, desk }: { ws: string; desk: boolean }) {
  const { me } = useMe(ws);
  const prefs = useSWR<Prefs>(`/workspaces/${ws}/me/prefs`, fetcher);
  const clips = useSWR<Clip[]>(`/workspaces/${ws}/radio-clips`, fetcher, { refreshInterval: 30_000 });
  const radios = useSWR<Radio[]>(`/workspaces/${ws}/radios`, fetcher);
  // What was typed here wins; otherwise the station this device used last, then my preference.
  const [typed, setTyped] = useState<string | null>(null);
  const [remembered, setRemembered] = useState<string | null>(null);
  const [known, setKnown] = useState<string[]>([]);
  const [lang, setLang] = useState<Lang>("mg");
  const [time, setTime] = useState("");
  const [text, setText] = useState("");
  const [sending, setSending] = useState<null | number>(null);
  const [canRecord, setCanRecord] = useState(false);
  const [file, setFile] = useState<Attached | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const recording = useRecording(() => toast.error(w.micDenied));
  const dictation = useDictation(lang, (said) => setText((x) => (x ? `${x} ${said}` : said)));

  // Browser-only facts, read after mount so the first render matches the server's.
  useEffect(() => {
    requestAnimationFrame(() => {
      setCanRecord("MediaRecorder" in window && !!navigator.mediaDevices?.getUserMedia);
      setRemembered(read(STATION));
      setLang(read(LANG) === "fr" ? "fr" : "mg");
      setTime(clock(new Date()));
      try {
        setKnown(JSON.parse(read(STATIONS) ?? "[]"));
      } catch {
        setKnown([]);
      }
    });
  }, []);
  const station = typed ?? remembered ?? prefs.data?.station ?? "";
  // The partner radios first, then the stations typed on this device.
  const choices = [...new Set([...(radios.data ?? []).map((x) => x.name), ...known])].slice(0, 8);

  const recorded = recording.clip ? { ...recording.clip, name: null } : null;
  const clip: Attached | null = file ?? recorded;
  const enough = text.trim().length >= 10;
  const canSend = station.trim().length > 0 && enough && sending === null && recording.state !== "recording";
  const mine = (clips.data ?? []).filter((c) => !desk || c.created_by === me?.id);

  function chooseLang(l: Lang) {
    setLang(l);
    write(LANG, l);
  }

  function pickFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    if (f.size > 25 * 1024 * 1024) return void toast.error(w.tooBig);
    recording.reset();
    setFile({ blob: f, url: URL.createObjectURL(f), startedAt: time ? heardAt(time) : new Date(), seconds: null, name: f.name });
  }

  function dropClip() {
    recording.reset();
    setFile(null);
  }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!canSend) return;
    const name = station.trim();
    setSending(0);
    try {
      let fileId: string | undefined;
      if (clip) {
        try {
          const type = clip.blob.type || "audio/mpeg";
          const ext = clip.name?.split(".").pop() ?? (type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm");
          const up = await api<Upload>(`/workspaces/${ws}/radio-clips/upload-url`, {
            method: "POST",
            body: JSON.stringify({ filename: `antenne-${clip.startedAt.toISOString().slice(0, 16).replace(/[:T]/g, "-")}.${ext}`, mime: type, size_bytes: clip.blob.size }),
          });
          await put(up, clip.blob, (f) => setSending(Math.round(f * 100)));
          fileId = up.file_id;
        } catch (err) {
          if (!(err instanceof ApiError && (err.status === 503 || err.status === 415))) throw err;
          toast(w.noStorage);
        }
      }
      await api<Clip>(`/workspaces/${ws}/radio-clips`, {
        method: "POST",
        body: JSON.stringify({ station: name, heard_text: text.trim(), language: lang, recorded_at: (time ? heardAt(time) : new Date()).toISOString(), file_id: fileId }),
      });
      write(STATION, name);
      setRemembered(name);
      const next = [name, ...known.filter((k) => k !== name)].slice(0, 8);
      setKnown(next);
      write(STATIONS, JSON.stringify(next));
      setText("");
      setTime(clock(new Date()));
      dropClip();
      toast(w.sent);
      void clips.mutate();
    } catch {
      toast.error(w.failed);
    } finally {
      setSending(null);
    }
  }

  const remaining = Math.max(0, MAX_SECONDS - recording.elapsed);

  return (
    <div className="mx-auto max-w-xl px-4 pt-6 pb-16 lg:pt-8">
      {desk && (
        <Link href={`/w/${ws}/watch` as never} className="mb-4 inline-flex items-center gap-1.5 text-sm font-bold underline underline-offset-4">
          <IconArrowLeft className="size-4" aria-hidden />
          {w.deskLink}
        </Link>
      )}
      <h1 className="page-title">{w.title}</h1>
      <p className="mt-2 text-pretty text-muted-foreground">{w.lead}</p>

      <form onSubmit={send} className="mt-6 space-y-6">
        <div>
          <Label htmlFor="station" className="font-bold">
            {w.station}
          </Label>
          {choices.length > 0 && (
            <div role="radiogroup" aria-label={w.stationsKnown} className="mt-1.5 flex flex-wrap gap-2">
              {choices.map((k) => (
                <button
                  key={k}
                  type="button"
                  role="radio"
                  aria-checked={station === k}
                  onClick={() => setTyped(k)}
                  className={cn(
                    "h-10 rounded-full border px-3.5 text-sm font-bold outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    station === k ? "border-foreground bg-primary text-primary-foreground" : "border-border bg-card hover:bg-raised",
                  )}
                >
                  {k}
                </button>
              ))}
            </div>
          )}
          <Input
            id="station"
            value={station}
            onChange={(e) => setTyped(e.target.value)}
            placeholder={w.stationPlaceholder}
            maxLength={120}
            autoComplete="off"
            className="mt-2 h-12 bg-card text-base"
          />
        </div>

        <div className="grid gap-4 sm:grid-cols-[10rem_1fr]">
          <div>
            <Label htmlFor="heard-at" className="font-bold">
              {w.time}
            </Label>
            <Input id="heard-at" type="time" value={time} onChange={(e) => setTime(e.target.value)} aria-describedby="heard-at-hint" className="mt-1.5 h-12 bg-card text-base tabular" />
          </div>
          <fieldset>
            <legend className="font-bold">{w.language}</legend>
            <PillTabs
              kind="radio"
              fill
              className="mt-1.5 flex"
              label={w.language}
              value={lang}
              onChange={chooseLang}
              items={(["mg", "fr"] as const).map((l) => ({ value: l, label: w.languages[l] }))}
            />
          </fieldset>
          <p id="heard-at-hint" className="text-sm text-muted-foreground sm:col-span-2">
            {w.timeHint}
          </p>
        </div>

        <div>
          <div className="flex items-end justify-between gap-3">
            <Label htmlFor="heard" className="font-bold">
              {w.heard}
            </Label>
            {canRecord && (
              <Button
                type="button"
                variant="outline"
                size="lg"
                onClick={dictation.toggle}
                disabled={recording.state === "recording" || dictation.state === "transcribing"}
                aria-pressed={dictation.state === "recording"}
              >
                {dictation.state === "transcribing" ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconMicrophone aria-hidden />}
                {dictation.state === "recording" ? w.dictating : dictation.state === "transcribing" ? w.transcribing : w.dictate}
              </Button>
            )}
          </div>
          <textarea
            id="heard"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={w.heardPlaceholder}
            rows={3}
            maxLength={4000}
            lang={lang}
            className="mt-1.5 w-full rounded-md border border-input bg-card px-3 py-2.5 text-base outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          />
          <p className="mt-1 text-sm text-pretty text-muted-foreground">{lang === "mg" ? w.mgNote : w.frNote}</p>
          {!enough && text.trim().length > 0 && <p className="mt-1 text-sm font-bold">{w.tooShort}</p>}
        </div>

        <details className="group rounded-md border border-border bg-card" open={!!clip || recording.state === "recording" || undefined}>
          <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 font-bold outline-none focus-visible:ring-2 focus-visible:ring-ring">
            <IconPaperclip className="size-5" aria-hidden />
            {w.audio}
          </summary>
          <div className="space-y-3 border-t border-border px-4 pt-3 pb-4">
            <p className="text-sm text-muted-foreground">{w.audioLead}</p>
            {recording.state === "recording" ? (
              <Button type="button" onClick={recording.stop} className="h-14 w-full gap-2 font-bold">
                <span className="step-active size-3 rounded-full bg-primary-foreground" aria-hidden />
                <IconStop className="size-5" aria-hidden />
                {w.stop}
                <span className="font-normal tabular" aria-live="polite">
                  · {w.remaining(remaining)}
                </span>
              </Button>
            ) : clip ? (
              <div>
                <p className="font-bold">{clip.name ? w.fileAttached(clip.name) : w.recorded(clip.seconds ?? 0)}</p>
                <audio controls src={clip.url} className="mt-2 w-full" />
                <Button type="button" variant="ghost" size="lg" onClick={dropClip} className="mt-1">
                  {w.redo}
                </Button>
              </div>
            ) : (
              <div className="flex flex-wrap gap-2">
                {canRecord && (
                  <Button type="button" variant="outline" size="lg" onClick={recording.start} disabled={dictation.state !== "idle"}>
                    <IconMicrophone aria-hidden />
                    {w.record}
                  </Button>
                )}
                <Button type="button" variant="outline" size="lg" onClick={() => fileInput.current?.click()}>
                  <IconPaperclip aria-hidden />
                  {w.pickFile}
                </Button>
                <input ref={fileInput} type="file" accept="audio/*" className="sr-only" tabIndex={-1} onChange={pickFile} />
                {canRecord && <p className="w-full text-sm text-muted-foreground">{w.maxNote}</p>}
              </div>
            )}
          </div>
        </details>

        <Button type="submit" variant="action" size="xl" className="h-14 w-full text-base" disabled={!canSend}>
          {sending !== null ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconPaperPlaneTilt aria-hidden />}
          {sending !== null ? (clip && sending < 100 ? w.uploading(sending) : w.sending) : w.send}
        </Button>
      </form>

      <Rewind radios={radios.data ?? []} />

      <section aria-labelledby="mes-signalements" className="mt-10 border-t border-foreground pt-3">
        <h2 id="mes-signalements" className="font-display text-xl font-bold">
          {w.mine}
        </h2>
        <div className="mt-3">{clips.data ? <MyClips clips={mine} /> : null}</div>
      </section>
    </div>
  );
}
