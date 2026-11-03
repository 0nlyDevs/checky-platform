"use client";

import type { Item } from "@fanilo/shared";
import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { api, ApiError, fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/live";
import { IconArrowCounterClockwise, IconCheck, IconCircleNotch, IconDownloadSimple, IconMicrophone, IconShareNetwork, IconStop, IconX } from "@/lib/icons";

const v = t.dossier.voice;
const MAX_SECONDS = 30;

type Upload = { file_id: string; upload_url: string; headers: Record<string, string> };
export type VoiceNote = { file_id: string; url: string; mime: string; size_bytes: number; seconds: number | null; language: string; by: string; at: string };

function pickMime() {
  if (typeof MediaRecorder === "undefined") return "";
  return ["audio/webm;codecs=opus", "audio/webm", "audio/ogg", "audio/mp4"].find((m) => MediaRecorder.isTypeSupported?.(m)) ?? "";
}

const EXT: Record<string, string> = { "audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/mpeg": "mp3" };

function put(up: Upload, blob: Blob) {
  return new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", up.upload_url);
    for (const [k, val] of Object.entries(up.headers)) xhr.setRequestHeader(k, val);
    xhr.onload = () => (xhr.status < 300 ? resolve() : reject(new Error(`upload ${xhr.status}`)));
    xhr.onerror = () => reject(new Error("upload network"));
    xhr.send(blob);
  });
}

/** The take being recorded or listened to, before it is kept. */
type Take = { blob: Blob; url: string; seconds: number };

/**
 * « Un démenti malgache en 30 secondes avec sa propre voix »: the journalist records it here,
 * listens, keeps it or records again. It goes straight to storage and is attached to the dossier;
 * it is never transcribed (spoken Malagasy stays with people). The public page plays it.
 */
export function VoiceNotePanel({ ws, item, onSent }: { ws: string; item: Item; onSent: () => void }) {
  const key = `/workspaces/${ws}/items/${item.id}/voice-note`;
  const { data: note, error, mutate } = useSWR<VoiceNote>(key, fetcher, { shouldRetryOnError: false, revalidateOnFocus: false });
  const missing = error instanceof ApiError && error.status === 404;
  const [state, setState] = useState<"idle" | "recording" | "saving">("idle");
  const [elapsed, setElapsed] = useState(0);
  const [take, setTake] = useState<Take | null>(null);
  const [can, setCan] = useState(false);
  const rec = useRef<MediaRecorder | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const ref = (item.data as { ref?: string }).ref ?? "dossier";

  useEffect(() => {
    // After hydration only: the server has no MediaRecorder.
    requestAnimationFrame(() => setCan("MediaRecorder" in window && !!navigator.mediaDevices?.getUserMedia));
    return () => {
      if (timer.current) clearInterval(timer.current);
      rec.current?.stream.getTracks().forEach((tr) => tr.stop());
    };
  }, []);

  async function start() {
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch {
      return toast.error(v.micDenied);
    }
    if (take) URL.revokeObjectURL(take.url);
    setTake(null);
    const mime = pickMime();
    const mr = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    const chunks: Blob[] = [];
    const started = Date.now();
    mr.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    mr.onstop = () => {
      stream.getTracks().forEach((tr) => tr.stop());
      if (timer.current) clearInterval(timer.current);
      const blob = new Blob(chunks, { type: (mr.mimeType || "audio/webm").split(";")[0] });
      const seconds = Math.min(MAX_SECONDS, Math.max(1, Math.round((Date.now() - started) / 1000)));
      setTake({ blob, url: URL.createObjectURL(blob), seconds });
      setState("idle");
    };
    rec.current = mr;
    mr.start(250);
    setElapsed(0);
    setState("recording");
    timer.current = setInterval(() => {
      const s = Math.floor((Date.now() - started) / 1000);
      setElapsed(Math.min(s, MAX_SECONDS));
      if (s >= MAX_SECONDS && mr.state === "recording") mr.stop();
    }, 200);
  }

  function stop() {
    if (rec.current?.state === "recording") rec.current.stop();
  }

  function redo() {
    if (take) URL.revokeObjectURL(take.url);
    setTake(null);
  }

  async function keep() {
    if (!take) return;
    setState("saving");
    try {
      const mime = take.blob.type || "audio/webm";
      const up = await api<Upload>(`/workspaces/${ws}/files/upload-url`, {
        method: "POST",
        body: JSON.stringify({ filename: `dementi-${ref}-mg.${EXT[mime] ?? "webm"}`, mime, size_bytes: take.blob.size }),
      });
      await put(up, take.blob);
      await mutate(api<VoiceNote>(key, { method: "PUT", body: JSON.stringify({ file_id: up.file_id, seconds: take.seconds, language: "mg" }) }), { revalidate: false });
      URL.revokeObjectURL(take.url);
      setTake(null);
      toast.success(v.saved);
    } catch (e) {
      toast.error(e instanceof ApiError && e.code === "not_signed" ? v.notSigned : v.failed);
    } finally {
      setState("idle");
    }
  }

  async function remove() {
    try {
      await api(key, { method: "DELETE" });
      await mutate(undefined, { revalidate: true });
    } catch {
      toast.error(v.failed);
    }
  }

  async function file(): Promise<File | null> {
    if (!note) return null;
    try {
      const blob = await (await fetch(note.url)).blob();
      return new File([blob], `dementi-${ref}-mg.${EXT[note.mime] ?? "webm"}`, { type: note.mime });
    } catch {
      return null;
    }
  }

  async function download() {
    const f = await file();
    if (!f) return void window.open(note?.url, "_blank", "noopener");
    const url = URL.createObjectURL(f);
    const a = document.createElement("a");
    a.href = url;
    a.download = f.name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    onSent();
  }

  async function share() {
    const f = await file();
    if (f && navigator.canShare?.({ files: [f] })) {
      try {
        await navigator.share({ files: [f], title: v.shareTitle(ref) });
        onSent();
      } catch {
        /* the journalist closed the share sheet */
      }
      return;
    }
    await download();
  }

  return (
    <div className="rounded-md border border-border bg-card p-4">
      <h3 className="font-bold">{v.title}</h3>
      <p className="mt-0.5 max-w-[60ch] text-sm text-muted-foreground">{v.lead}</p>

      {note && !take && state !== "recording" && (
        <div className="mt-3 space-y-3">
          <audio controls preload="metadata" src={note.url} className="w-full max-w-md" aria-label={v.player}>
            <track kind="captions" />
          </audio>
          <p className="text-sm text-muted-foreground tabular">{v.kept(note.seconds ? Math.round(note.seconds) : null)}</p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={share}>
              <IconShareNetwork aria-hidden />
              {v.share}
            </Button>
            <Button size="sm" variant="outline" onClick={download}>
              <IconDownloadSimple aria-hidden />
              {v.download}
            </Button>
            <Button size="sm" variant="ghost" onClick={start} disabled={!can}>
              <IconArrowCounterClockwise aria-hidden />
              {v.again}
            </Button>
            <Button size="sm" variant="ghost" onClick={remove}>
              <IconX aria-hidden />
              {v.remove}
            </Button>
          </div>
        </div>
      )}

      {state === "recording" && (
        <div className="mt-3 flex flex-wrap items-center gap-3" aria-live="polite">
          <Button size="sm" onClick={stop}>
            <IconStop aria-hidden />
            {v.stop}
          </Button>
          <span className="font-display text-lg font-bold tabular">{v.elapsed(elapsed, MAX_SECONDS)}</span>
        </div>
      )}

      {take && state !== "recording" && (
        <div className="mt-3 space-y-3">
          <audio controls src={take.url} className="w-full max-w-md" aria-label={v.listen}>
            <track kind="captions" />
          </audio>
          <p className="text-sm text-muted-foreground tabular">{v.takeLength(take.seconds)}</p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={keep} disabled={state === "saving"}>
              {state === "saving" ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconCheck aria-hidden />}
              {state === "saving" ? v.saving : v.keep}
            </Button>
            <Button size="sm" variant="outline" onClick={redo} disabled={state === "saving"}>
              <IconArrowCounterClockwise aria-hidden />
              {v.redo}
            </Button>
          </div>
        </div>
      )}

      {!take && state === "idle" && (missing || (!note && error)) && (
        <Button size="sm" variant="outline" className="mt-3" onClick={start} disabled={!can}>
          <IconMicrophone aria-hidden />
          {v.record(MAX_SECONDS)}
        </Button>
      )}
      {!can && <p className="mt-2 text-sm text-muted-foreground">{v.noMic}</p>}
    </div>
  );
}
