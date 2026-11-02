"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { IconArrowLeft, IconCircleNotch, IconMicrophone, IconPaperPlaneTilt, IconSealCheck, IconStop } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { VerdictChip } from "@/components/claims/verdict";
import { DemoTag, when } from "@/components/rubrique/bits";
import type { Clip, Prefs } from "@/components/rubrique/types";
import { useMe } from "@/components/rubrique/use-me";
import { api, API_URL, ApiError, fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/fr";
import { cn } from "@/lib/utils";

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

/**
 * À l'antenne, the veilleur's screen (phone first): record what the radio says, name the station,
 * say in one sentence what was announced, send. In Malagasy the newsroom reads the veilleur's own
 * sentence; nothing replaces it with a machine transcript.
 */
export function VeilleurView({ ws, desk }: { ws: string; desk: boolean }) {
  const { me } = useMe(ws);
  const prefs = useSWR<Prefs>(`/workspaces/${ws}/me/prefs`, fetcher);
  const clips = useSWR<Clip[]>(`/workspaces/${ws}/radio-clips`, fetcher, { refreshInterval: 30_000 });
  // What was typed here wins; otherwise the station this device used last, then my preference.
  const [typed, setTyped] = useState<string | null>(null);
  const [remembered, setRemembered] = useState<string | null>(null);
  const [known, setKnown] = useState<string[]>([]);
  const [lang, setLang] = useState<Lang>("mg");
  const [text, setText] = useState("");
  const [sending, setSending] = useState<null | number>(null);
  const [canRecord, setCanRecord] = useState(false);
  const recording = useRecording(() => toast.error(w.micDenied));
  const dictation = useDictation(lang, (said) => setText((x) => (x ? `${x} ${said}` : said)));

  // Browser-only facts, read after mount so the first render matches the server's.
  useEffect(() => {
    requestAnimationFrame(() => {
      setCanRecord("MediaRecorder" in window && !!navigator.mediaDevices?.getUserMedia);
      setRemembered(read(STATION));
      setLang(read(LANG) === "fr" ? "fr" : "mg");
      try {
        setKnown(JSON.parse(read(STATIONS) ?? "[]"));
      } catch {
        setKnown([]);
      }
    });
  }, []);
  const station = typed ?? remembered ?? prefs.data?.station ?? "";

  const clip = recording.clip;
  const enough = text.trim().length >= 10 || (!!clip && lang === "fr");
  const canSend = station.trim().length > 0 && enough && sending === null && recording.state !== "recording";
  const mine = (clips.data ?? []).filter((c) => !desk || c.created_by === me?.id);

  function chooseLang(l: Lang) {
    setLang(l);
    write(LANG, l);
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
          const ext = clip.blob.type.includes("mp4") ? "m4a" : clip.blob.type.includes("ogg") ? "ogg" : "webm";
          const up = await api<Upload>(`/workspaces/${ws}/radio-clips/upload-url`, {
            method: "POST",
            body: JSON.stringify({ filename: `antenne-${clip.startedAt.toISOString().slice(0, 16).replace(/[:T]/g, "-")}.${ext}`, mime: clip.blob.type, size_bytes: clip.blob.size }),
          });
          await put(up, clip.blob, (f) => setSending(Math.round(f * 100)));
          fileId = up.file_id;
        } catch (err) {
          if (!(err instanceof ApiError && err.status === 503) || text.trim().length < 10) throw err;
          toast(w.noStorage);
        }
      }
      await api<Clip>(`/workspaces/${ws}/radio-clips`, {
        method: "POST",
        body: JSON.stringify({ station: name, heard_text: text.trim(), language: lang, recorded_at: (clip?.startedAt ?? new Date()).toISOString(), file_id: fileId }),
      });
      write(STATION, name);
      setRemembered(name);
      const next = [name, ...known.filter((k) => k !== name)].slice(0, 8);
      setKnown(next);
      write(STATIONS, JSON.stringify(next));
      setText("");
      recording.reset();
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
        <Link href={`/w/${ws}/veille` as never} className="mb-4 inline-flex items-center gap-1.5 text-sm font-bold underline underline-offset-4">
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
          <Input
            id="station"
            list="stations-connues"
            value={station}
            onChange={(e) => setTyped(e.target.value)}
            placeholder={w.stationPlaceholder}
            maxLength={120}
            autoComplete="off"
            className="mt-1.5 h-12 bg-card text-base"
          />
          <datalist id="stations-connues">
            {known.map((k) => (
              <option key={k} value={k} />
            ))}
          </datalist>
        </div>

        <fieldset>
          <legend className="font-bold">{w.language}</legend>
          <div role="radiogroup" className="mt-1.5 grid grid-cols-2 rounded-md border border-input bg-card p-0.5">
            {(["mg", "fr"] as const).map((l) => (
              <button
                key={l}
                type="button"
                role="radio"
                aria-checked={lang === l}
                onClick={() => chooseLang(l)}
                className={cn("h-11 rounded-[3px] font-bold outline-none focus-visible:ring-2 focus-visible:ring-ring", lang === l ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground")}
              >
                {w.languages[l]}
              </button>
            ))}
          </div>
        </fieldset>

        <div>
          {!canRecord ? (
            <p className="rounded-md border border-dashed border-border p-4 text-sm">{w.noRecorder}</p>
          ) : recording.state === "recording" ? (
            <Button type="button" onClick={recording.stop} className="h-24 w-full flex-col gap-1 text-lg font-bold">
              <span className="inline-flex items-center gap-2">
                <span className="step-active size-3 rounded-full bg-primary-foreground" aria-hidden />
                <IconStop className="size-6" aria-hidden />
                {w.stop}
              </span>
              <span className="text-sm font-normal tabular" aria-live="polite">
                {w.remaining(remaining)}
              </span>
            </Button>
          ) : clip ? (
            <div className="rounded-md border border-foreground bg-card p-4">
              <p className="font-bold">{w.recorded(clip.seconds)}</p>
              <audio controls src={clip.url} className="mt-2 w-full" />
              <Button type="button" variant="ghost" size="lg" onClick={recording.reset} className="mt-2">
                {w.redo}
              </Button>
            </div>
          ) : (
            <>
              <Button type="button" variant="action" onClick={recording.start} disabled={dictation.state !== "idle"} className="h-24 w-full gap-3 text-xl">
                <IconMicrophone className="size-7" aria-hidden />
                {w.record}
              </Button>
              <p className="mt-1.5 text-center text-sm text-muted-foreground">{w.maxNote}</p>
            </>
          )}
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
            rows={4}
            maxLength={4000}
            lang={lang}
            className="mt-1.5 w-full rounded-md border border-input bg-card px-3 py-2.5 text-base outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          />
          <p className="mt-1 text-sm text-pretty text-muted-foreground">{lang === "mg" ? w.mgNote : w.frNote}</p>
          {!enough && text.trim().length > 0 && <p className="mt-1 text-sm font-bold">{w.tooShort}</p>}
        </div>

        {/* One primary per screen: Enregistrer while nothing is recorded, then Envoyer. */}
        <Button type="submit" variant={clip || !canRecord ? "default" : "outline"} size="xl" className="h-14 w-full text-base" disabled={!canSend}>
          {sending !== null ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconPaperPlaneTilt aria-hidden />}
          {sending !== null ? (clip && sending < 100 ? w.uploading(sending) : w.sending) : w.send}
        </Button>
      </form>

      <section aria-labelledby="mes-signalements" className="mt-10 border-t border-foreground pt-3">
        <h2 id="mes-signalements" className="font-display text-xl font-bold">
          {w.mine}
        </h2>
        <div className="mt-3">{clips.data ? <MyClips clips={mine} /> : null}</div>
      </section>
    </div>
  );
}
