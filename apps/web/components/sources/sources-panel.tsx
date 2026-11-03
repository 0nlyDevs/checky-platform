"use client";

import type { components } from "@fanilo/shared";
import Link from "next/link";
import { useRef, useState } from "react";
import useSWR from "swr";
import { IconArrowCounterClockwise, IconArrowSquareOut, IconCalendarDots, IconCheck, IconCircleNotch, IconCopy, IconEye, IconEyeSlash, IconFileText, IconImage, IconLink, IconMapPin, IconPaperclip, IconPlay, IconPlus, IconSealCheck, IconSparkle, IconTextT, IconVideoCamera, IconWarning, IconWaveform, type Icon } from "@/lib/icons";
import { toast } from "sonner";
import { undoable } from "@/lib/undo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkspace } from "@/hooks/use-workspace";
import { useWorkspaceSocket } from "@/hooks/use-workspace-socket";
import { api, ApiError, fetcher } from "@/lib/api";
import { dateFormat, t } from "@/lib/i18n/live";
import { uploadFile, type Source } from "@/lib/upload";
import { cn } from "@/lib/utils";
import { ImageTrace } from "@/components/sources/image-trace";
import { EcoGate, EcoImage } from "@/components/prefs/eco";

const KIND_ICON: Record<string, Icon> = { url: IconLink, pdf: IconFileText, image: IconImage, audio: IconWaveform, video: IconVideoCamera, text: IconTextT };
const ACCEPT = "image/jpeg,image/png,image/webp,image/gif,image/heic,application/pdf,audio/*,video/mp4,video/webm,video/quicktime,video/3gpp";

const dateFmt = dateFormat({ day: "numeric", month: "short", year: "numeric" });
const sizeFmt = (bytes: number) =>
  bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} Ko` : `${(bytes / 1024 / 1024).toFixed(1).replace(".", ",")} Mo`;

function errorText(e: unknown) {
  if (e instanceof ApiError) return t.sources.errors[e.code] ?? t.sources.errors.generic;
  return t.sources.errors.upload;
}

function host(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/** "2004-09-02" → "2 sept. 2004"; anything else as given. */
function pubDate(v: string) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(v);
  return m ? dateFmt.format(new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))) : v;
}

/** EXIF "2026:10:24 09:12:03" → a French date, or the raw value if it does not parse. */
function exifDate(v: string) {
  const m = /^(\d{4}):(\d{2}):(\d{2})/.exec(v);
  return m ? dateFmt.format(new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))) : v;
}

type Shown = components["schemas"]["PictureOut"];
type MemoryMatch = components["schemas"]["MemoryMatch"];

/**
 * A picture of a source as the desk shows it: faces blurred, or hidden while they could not be
 * checked. « Voir l'original » asks the API for the untouched file; that look is logged on the
 * dossier. `frame` is the keyframe index for a video, absent for an image.
 */
function FacePicture({ ws, source, shown, frame, alt, width, height, className }: { ws: string; source: Source; shown: Shown; frame?: number; alt: string; width: number; height: number; className?: string }) {
  const [original, setOriginal] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function reveal() {
    setBusy(true);
    try {
      const r = await api<{ url: string }>(`/workspaces/${ws}/sources/${source.id}/reveal`, {
        method: "POST",
        body: JSON.stringify(frame == null ? {} : { frame }),
      });
      setOriginal(r.url);
    } catch (e) {
      toast.error(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-1">
      {original ? (
        // eslint-disable-next-line @next/next/no-img-element -- presigned storage URL, asked for on purpose
        <img src={original} alt={alt} width={width} height={height} className={className} />
      ) : shown.image_url ? (
        <EcoImage src={shown.image_url} alt={alt} width={width} height={height} className={className} />
      ) : (
        <div className={cn("flex items-center justify-center gap-1.5 bg-muted p-2 text-center text-xs text-muted-foreground", className)}>
          <IconEyeSlash className="size-3.5 shrink-0" aria-hidden />
          {t.sources.faces.unchecked}
        </div>
      )}
      <p className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
        {!!shown.faces && !original && <span>{t.sources.faces.blurred(shown.faces)}</span>}
        {original ? (
          <span>{t.sources.faces.revealed}</span>
        ) : (
          shown.faces !== 0 && (
            <button type="button" onClick={reveal} disabled={busy} className="inline-flex items-center gap-1 font-medium text-foreground underline decoration-border underline-offset-4 hover:decoration-foreground disabled:opacity-60">
              <IconEye className="size-3.5" aria-hidden />
              {t.sources.faces.reveal}
            </button>
          )
        )}
      </p>
    </div>
  );
}

/** Reverse-search links, built by the API on the blurred copy (none while faces are unchecked). */
function ReverseLinks({ links, label }: { links: Shown["reverse_search"]; label?: string }) {
  if (!links.length) return null;
  return (
    <>
      {links.map((service) => (
        <a key={service.name} href={service.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-0.5 text-foreground underline decoration-border underline-offset-4 hover:decoration-foreground" aria-label={label ? `${label} · ${service.name}` : undefined}>
          {service.name}
        </a>
      ))}
    </>
  );
}

/** The newsroom's memory of a picture: the same image (or video frame) seen before, oldest first. */
function PictureMemory({ ws, source }: { ws: string; source: Source }) {
  const { data } = useSWR<MemoryMatch[]>(`/workspaces/${ws}/sources/${source.id}/memory`, fetcher);
  if (!data?.length) return null;
  return (
    <ul className="space-y-1 text-sm">
      {data.map((m) => {
        const href = m.own && m.item_id ? `/w/${ws}/affirmations/${m.item_id}` : m.verdict_id ? `/verifies/${m.verdict_id}` : null;
        return (
          <li key={m.source_id} className="flex items-start gap-1.5 font-medium">
            <IconCalendarDots className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            {href ? (
              <Link href={href} className="underline decoration-border underline-offset-4 hover:decoration-foreground">
                {m.line}
                {m.ref ? ` · ${m.ref}` : ""}
              </Link>
            ) : (
              <span>{m.line}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function ImageFacts({ ws, source }: { ws: string; source: Source }) {
  const meta = (source.file?.meta ?? {}) as { exif?: Record<string, unknown>; ai_markers?: string[]; content_credentials?: boolean };
  const exif = meta.exif ?? {};
  const camera = [exif.Make, exif.Model].filter(Boolean).join(" ");
  const date = (exif.DateTimeOriginal ?? exif.DateTime) as string | undefined;
  const picture = source.file?.picture;
  return (
    <div className="mt-2 space-y-1.5 text-sm">
      {picture && (
        <FacePicture ws={ws} source={source} shown={picture} alt={source.title} width={240} height={160} className="h-40 w-60 max-w-full rounded-md object-contain" />
      )}
      {Object.keys(exif).length === 0 ? (
        <p className="text-muted-foreground">{t.sources.exifNone}</p>
      ) : (
        <ul className="space-y-0.5">
          {camera && <li>{t.sources.exifCamera(camera)}</li>}
          {date && <li>{t.sources.exifDate(exifDate(date))}</li>}
          {"GPS" in exif && (
            <li className="flex items-center gap-1.5">
              <IconMapPin className="size-3.5" aria-hidden />
              {t.sources.exifGps}
            </li>
          )}
        </ul>
      )}
      {meta.ai_markers?.length ? (
        <ImageTrace state="detected">{t.sources.aiMarkers(meta.ai_markers.join(", "))}</ImageTrace>
      ) : (
        <ImageTrace state="none">{t.linkCheck.imageNoMarkers}</ImageTrace>
      )}
      {meta.content_credentials && (
        <p className="flex items-start gap-1.5">
          <IconSealCheck className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          {t.sources.contentCredentials}
        </p>
      )}
      {source.duplicates > 0 && (
        <p className="flex items-center gap-1.5 font-medium">
          <IconCopy className="size-3.5" aria-hidden />
          {t.sources.duplicates(source.duplicates)}
        </p>
      )}
      <PictureMemory ws={ws} source={source} />
      {!!picture?.reverse_search.length && (
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-muted-foreground">
          <span>{t.sources.reverse}{t.common.colon}</span>
          <ReverseLinks links={picture.reverse_search} />
        </p>
      )}
    </div>
  );
}

type Transcript = components["schemas"]["TranscriptOut"];

/** 75.4 → "1:15", in the airtime face. */
const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

type Highlight = { text: string; start: number | null };
type Highlights = { quotes: Highlight[]; claims: Highlight[]; dropped_quotes: number; model: string };

/** F3: the interview's key quotes (click to hear) and its checkable claims (one click to track). */
function HighlightsBlock({ ws, source, highlights, play, onRefresh }: { ws: string; source: Source; highlights?: Highlights | null; play: (s: number) => void; onRefresh: () => void }) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [created, setCreated] = useState<Set<number>>(new Set());

  useWorkspaceSocket(ws, {
    "source.updated": (s: Source) => {
      if (s.id !== source.id || !jobId) return;
      setJobId(null);
      onRefresh();
    },
    "job.failed": (j: { id: string }) => {
      if (j.id !== jobId) return;
      setJobId(null);
      toast.error(t.sources.extractFailed);
    },
  });

  async function extract() {
    try {
      const job = await api<{ id: string }>(`/workspaces/${ws}/sources/${source.id}/quotes`, { method: "POST" });
      setJobId(job.id);
    } catch (e) {
      toast.error(errorText(e));
    }
  }

  async function toClaim(c: Highlight, i: number) {
    try {
      await api(`/workspaces/${ws}/items`, {
        method: "POST",
        body: JSON.stringify({
          title: c.text.slice(0, 300),
          body: t.sources.claimBody(source.title, c.start != null ? clock(c.start) : "—"),
          data: { first_seen_at: new Date().toISOString(), origin: "other", from_source_id: source.id },
        }),
      });
      setCreated((prev) => new Set(prev).add(i));
      toast.success(t.sources.claimCreated);
    } catch (e) {
      toast.error(errorText(e));
    }
  }

  return (
    <div className="space-y-3 pt-1">
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="outline" size="sm" onClick={extract} disabled={Boolean(jobId)}>
          {jobId ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconSparkle aria-hidden />}
          {highlights ? t.sources.reExtract : t.sources.extract}
        </Button>
        {jobId && (
          <span className="text-sm text-muted-foreground" role="status">
            {t.sources.extracting}
          </span>
        )}
      </div>
      {highlights && (
        <>
          {highlights.quotes.length > 0 && (
            <div>
              <h4 className="text-sm font-medium text-muted-foreground">{t.sources.quotes}</h4>
              <ul className="mt-1.5 space-y-1.5">
                {highlights.quotes.map((q, i) => (
                  <li key={i}>
                    <button type="button" onClick={() => q.start != null && play(q.start)} className="group flex w-full gap-3 rounded-sm px-2 py-1 text-left hover:bg-accent">
                      <span className="w-12 shrink-0 font-display text-sm tracking-wide tabular text-muted-foreground">{q.start != null ? clock(q.start) : "—"}</span>
                      <span className="quote text-pretty">{t.common.quote(q.text)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {highlights.claims.length > 0 && (
            <div>
              <h4 className="text-sm font-medium text-muted-foreground">{t.sources.claims}</h4>
              <ul className="mt-1.5 divide-y divide-border rounded-md border border-border">
                {highlights.claims.map((c, i) => (
                  <li key={i} className="flex flex-wrap items-center gap-x-3 gap-y-1.5 px-3 py-2">
                    <span className="w-12 shrink-0 font-display text-sm tracking-wide tabular text-muted-foreground">{c.start != null ? clock(c.start) : "—"}</span>
                    <span className="min-w-0 flex-1 text-sm text-pretty">{c.text}</span>
                    <Button variant="ghost" size="sm" onClick={() => toClaim(c, i)} disabled={created.has(i)}>
                      {created.has(i) ? <IconCheck aria-hidden /> : <IconPlus aria-hidden />}
                      {t.sources.toClaim}
                    </Button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {highlights.dropped_quotes > 0 && <p className="text-sm text-muted-foreground">{t.sources.droppedQuotes(highlights.dropped_quotes)}</p>}
        </>
      )}
    </div>
  );
}

function AudioFacts({ ws, source }: { ws: string; source: Source }) {
  const [open, setOpen] = useState(false);
  const audio = useRef<HTMLMediaElement>(null);
  const { data: tr, mutate: refreshTranscript } = useSWR<Transcript>(open ? `/workspaces/${ws}/sources/${source.id}/transcript` : null, fetcher);
  const meta = (source.file?.meta ?? {}) as { language?: string; ai_markers?: string[] };
  const frames = source.file?.keyframes ?? [];

  function play(from: number) {
    const el = audio.current;
    if (!el) return;
    el.currentTime = from;
    void el.play();
  }

  async function redo(language: string) {
    try {
      await api(`/workspaces/${ws}/sources/${source.id}/transcribe`, { method: "POST", body: JSON.stringify({ language }) });
      setOpen(false);
      toast.success(t.sources.redoStarted);
    } catch (e) {
      toast.error(errorText(e));
    }
  }

  return (
    <div className="mt-2 space-y-2">
      {source.file?.download_url &&
        (source.kind === "video" ? (
          // Mode éco: the video waits for a tap (even its metadata costs data on a 2G link).
          <EcoGate kind="video" className="h-32 w-full max-w-md">
            <video ref={(el) => { audio.current = el; }} controls preload="metadata" src={source.file.download_url} className="max-h-72 w-full max-w-md rounded-md bg-foreground" />
          </EcoGate>
        ) : (
          <audio ref={(el) => { audio.current = el; }} controls preload="none" src={source.file.download_url} className="h-9 w-full max-w-md" />
        ))}
      {source.kind === "video" && frames.length > 0 && (
        <section aria-label={t.sources.videoFrames} className="space-y-2">
          <p className="text-sm font-medium">{t.sources.videoFrames}</p>
          <p className="text-xs text-muted-foreground">{t.sources.faceReview}</p>
          <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
            {frames.map((frame) => (
              <li key={frame.index} className="min-w-0 space-y-1 rounded-md border border-border p-1.5">
                <FacePicture ws={ws} source={source} shown={frame} frame={frame.index} alt={t.sources.frameAt(clock(frame.at_s))} width={192} height={108} className="aspect-video w-full rounded-sm object-cover" />
                <button type="button" onClick={() => play(frame.at_s)} className="inline-flex items-center gap-1 text-xs font-medium tabular-nums underline decoration-border underline-offset-4 hover:decoration-foreground" aria-label={t.sources.playFrame(clock(frame.at_s))}>
                  <IconPlay className="size-3" aria-hidden />
                  {clock(frame.at_s)}
                </button>
                <div className="flex flex-wrap gap-x-2 gap-y-1 text-xs font-medium">
                  <ReverseLinks links={frame.reverse_search} label={t.sources.searchFrame(clock(frame.at_s))} />
                </div>
              </li>
            ))}
          </ul>
          <PictureMemory ws={ws} source={source} />
        </section>
      )}
      {!!meta.ai_markers?.length && (
        <ImageTrace state="detected" className="text-sm">
          {t.sources.aiMarkers(meta.ai_markers.join(", "))}
        </ImageTrace>
      )}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="font-medium underline decoration-border underline-offset-4 hover:decoration-foreground"
        >
          {open ? t.sources.hideTranscript : t.sources.showTranscript}
        </button>
        {meta.language && <span className="text-muted-foreground">{t.sources.detected(t.sources.languages[meta.language.toLowerCase()] ?? meta.language)}</span>}
        <span className="flex items-center gap-2 text-muted-foreground">
          <IconArrowCounterClockwise className="size-3.5" aria-hidden />
          {t.sources.redo}
          <button type="button" onClick={() => redo("fr")} className="text-foreground underline decoration-border underline-offset-4 hover:decoration-foreground">
            {t.sources.redoFr}
          </button>
          <button type="button" onClick={() => redo("mg")} className="text-foreground underline decoration-border underline-offset-4 hover:decoration-foreground">
            {t.sources.redoMg}
          </button>
        </span>
      </div>
      {open &&
        (!tr ? (
          <Skeleton className="h-16 w-full" />
        ) : tr.segments.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t.sources.noSpeech}</p>
        ) : (
          <ol className="max-h-80 space-y-0.5 overflow-y-auto rounded-md border border-border p-1">
            {tr.segments.map((g, i) => (
              <li key={i}>
                <button
                  type="button"
                  onClick={() => play(g.start)}
                  aria-label={`${t.sources.playFrom(clock(g.start))}${t.common.colon} ${g.text}`}
                  className="group flex w-full gap-3 rounded-sm px-2 py-1 text-left text-sm hover:bg-accent focus-visible:outline-2"
                >
                  <span className="flex w-12 shrink-0 items-center gap-1 font-display tracking-wide tabular text-muted-foreground">
                    <IconPlay className="size-3 opacity-0 group-hover:opacity-100" aria-hidden />
                    {clock(g.start)}
                  </span>
                  <span className="text-pretty">{g.text}</span>
                </button>
              </li>
            ))}
          </ol>
        ))}
      {open && tr && tr.segments.length > 0 && (
        <HighlightsBlock ws={ws} source={source} highlights={tr.highlights as Highlights | null | undefined} play={play} onRefresh={() => refreshTranscript()} />
      )}
    </div>
  );
}

/** Today in the browser's own time zone, as YYYY-MM-DD (toISOString would give UTC's day). */
function localToday() {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
}

/** The publication date the AI checks against the rumour; who added the source (or an editor) can set it. */
function SourceDate({ ws, source, canEdit }: { ws: string; source: Source; canEdit: boolean }) {
  const d = t.sources.date;
  const [editing, setEditing] = useState(false);
  const [pending, setPending] = useState(false);
  const day = source.published_at?.slice(0, 10) ?? "";

  async function save(value: string | null) {
    setPending(true);
    try {
      await api(`/workspaces/${ws}/sources/${source.id}`, { method: "PATCH", body: JSON.stringify({ published_at: value }) });
      toast.success(d.saved);
      setEditing(false);
    } catch {
      toast.error(d.failed);
    } finally {
      setPending(false);
    }
  }

  if (editing) {
    return (
      <form
        className="mt-2 flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const value = String(new FormData(e.currentTarget).get("published_at") || "");
          void save(value || null);
        }}
      >
        <div className="space-y-1">
          <Label htmlFor={`date-${source.id}`} className="text-sm">
            {d.label}
          </Label>
          <Input
            id={`date-${source.id}`}
            name="published_at"
            type="date"
            defaultValue={day}
            max={localToday()}
            className="h-9 w-44 tabular"
            autoFocus
          />
        </div>
        <Button type="submit" size="sm" className="h-9" disabled={pending}>
          {pending && <IconCircleNotch className="animate-spin" aria-hidden />}
          {d.save}
        </Button>
        {day && (
          <Button type="button" variant="ghost" size="sm" className="h-9" disabled={pending} onClick={() => void save(null)}>
            {d.clear}
          </Button>
        )}
        <Button type="button" variant="ghost" size="sm" className="h-9" disabled={pending} onClick={() => setEditing(false)}>
          {d.cancel}
        </Button>
        <p className="basis-full text-sm text-muted-foreground">{d.hint}</p>
      </form>
    );
  }
  return (
    <p className="mt-1 flex flex-wrap items-center gap-x-1.5 text-sm text-muted-foreground">
      <IconCalendarDots className="size-3.5 shrink-0" aria-hidden />
      {day ? d.known(pubDate(day)) : d.unknown}
      {canEdit && (
        <>
          <span aria-hidden>·</span>
          <button type="button" className="underline underline-offset-2 hover:text-foreground" onClick={() => setEditing(true)}>
            {day ? d.edit : d.add}
          </button>
        </>
      )}
    </p>
  );
}

function SourceRow({ ws, source, onRemove }: { ws: string; source: Source; onRemove?: () => void }) {
  const [confirming, setConfirming] = useState(false);
  const Icon = KIND_ICON[source.kind] ?? IconFileText;
  const href = source.url ?? source.file?.download_url ?? undefined;
  const meta = (source.file?.meta ?? {}) as { pages?: number };
  const details = [
    t.sources.kinds[source.kind] ?? source.kind,
    source.url && host(source.url),
    source.file && sizeFmt(source.file.size_bytes),
    meta.pages && t.sources.pages(meta.pages),
    source.author,
  ].filter(Boolean);

  return (
    <li className="flex gap-3 px-4 py-3.5">
      <Icon className="mt-0.5 size-[1.125rem] shrink-0 text-muted-foreground" aria-hidden />
      <div className="min-w-0 flex-1">
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            {href ? (
              <a href={href} target="_blank" rel="noreferrer" className="group inline-flex max-w-full items-baseline gap-1.5 font-medium hover:underline">
                <span className="line-clamp-2 text-pretty">{source.title}</span>
                <IconArrowSquareOut className="size-3.5 shrink-0 self-center text-muted-foreground" aria-label={t.sources.open} />
              </a>
            ) : (
              <p className="line-clamp-2 font-medium text-pretty">{source.title}</p>
            )}
            <p className="truncate text-sm text-muted-foreground">{details.join(" · ")}</p>
            {/* Same rule as removing: who added it, or an editor. */}
            {source.status !== "queued" && <SourceDate ws={ws} source={source} canEdit={Boolean(onRemove)} />}
          </div>
          {!onRemove ? null : confirming ? (
            <Button variant="destructive" size="sm" onClick={onRemove} onBlur={() => setConfirming(false)} autoFocus>
              {t.sources.removeConfirm}
            </Button>
          ) : (
            <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={() => setConfirming(true)}>
              {t.sources.remove}
            </Button>
          )}
        </div>

        {source.status === "queued" && (
          <p className="mt-2 flex items-center gap-2 text-sm text-muted-foreground" role="status">
            <IconCircleNotch className="size-3.5 animate-spin" aria-hidden />
            {source.kind === "audio" || source.kind === "video" ? t.sources.transcribing : t.sources.analysing}
          </p>
        )}
        {source.status === "failed" && (
          <p className="mt-2 flex items-start gap-2 rounded-md bg-verdict-false-soft px-2.5 py-1.5 text-sm text-verdict-false-ink" role="alert">
            <IconWarning className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            <span>
              <span className="font-medium">{t.sources.failed}</span> · {source.error}
            </span>
          </p>
        )}
        {source.status === "ready" && source.kind === "image" && <ImageFacts ws={ws} source={source} />}
        {(source.kind === "audio" || source.kind === "video") && source.status !== "queued" && <AudioFacts ws={ws} source={source} />}
        {source.status === "ready" && source.kind !== "audio" && source.kind !== "video" && source.excerpt && (
          <p className="mt-2 line-clamp-3 max-w-[70ch] text-sm text-pretty">{source.excerpt}</p>
        )}
        {source.status === "ready" && source.error && (
          <p className="mt-2 text-sm text-muted-foreground">{source.error}</p>
        )}
      </div>
    </li>
  );
}

/** Sources of one claim (`itemId`), or of the whole workspace. Live: other people's additions appear as they land. */
export function SourcesPanel({ ws, itemId, kind }: { ws: string; itemId?: string; kind?: "audio" }) {
  const query = new URLSearchParams({ ...(itemId && { item_id: itemId }), ...(kind && { kind }) }).toString();
  const key = `/workspaces/${ws}/sources${query ? `?${query}` : ""}`;
  const { data: sources, error, mutate } = useSWR<Source[]>(key, fetcher);
  const [url, setUrl] = useState("");
  const [adding, setAdding] = useState(false);
  const [upload, setUpload] = useState<{ name: string; progress: number } | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const { joined } = useWorkspace(ws);
  const canRemove = () => joined;

  const mine = (s: { item_id?: string | null; kind?: string }) =>
    (!itemId || s.item_id === itemId) && (!kind || !s.kind || s.kind === kind);
  useWorkspaceSocket(ws, {
    "source.created": (s: Source) => mine(s) && mutate(),
    "source.updated": (s: Source) => mine(s) && mutate(),
    "source.deleted": (s: { item_id: string | null }) => mine(s) && mutate(),
    reconnected: () => mutate(),
  });

  async function addUrl(e: React.FormEvent) {
    e.preventDefault();
    const value = url.trim();
    if (!value) return;
    setAdding(true);
    try {
      const s = await api<Source>(`/workspaces/${ws}/sources`, {
        method: "POST",
        body: JSON.stringify({ url: /^https?:\/\//i.test(value) ? value : `https://${value}`, item_id: itemId }),
      });
      mutate((list) => (list?.some((x) => x.id === s.id) ? list : [s, ...(list ?? [])]), { revalidate: false });
      setUrl("");
      undoable(t.sources.added, () => unattach(s), t.sources.removed);
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setAdding(false);
    }
  }

  async function addFile(file: File | undefined) {
    if (!file) return;
    if (file.size > 25 * 1024 * 1024) {
      toast.error(t.sources.errors.too_large);
      return;
    }
    setUpload({ name: file.name, progress: 0 });
    try {
      const s = await uploadFile(ws, file, itemId, (progress) => setUpload({ name: file.name, progress }));
      mutate((list) => (list?.some((x) => x.id === s.id) ? list : [s, ...(list ?? [])]), { revalidate: false });
      undoable(t.sources.added, () => unattach(s), t.sources.removed);
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setUpload(null);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  /** Undo of an addition: the source is taken out again. */
  async function unattach(s: Source) {
    await api(`/workspaces/${ws}/sources/${s.id}`, { method: "DELETE" });
    mutate((list) => list?.filter((x) => x.id !== s.id), { revalidate: false });
  }

  async function remove(s: Source) {
    mutate((list) => list?.filter((x) => x.id !== s.id), { revalidate: false });
    try {
      await api(`/workspaces/${ws}/sources/${s.id}`, { method: "DELETE" });
      toast.success(t.sources.removed);
    } catch (err) {
      toast.error(errorText(err));
      mutate();
    }
  }

  const inputId = itemId ? `source-url-${itemId}` : "source-url";

  return (
    <div className="space-y-4">
      <form onSubmit={addUrl} className="flex flex-wrap gap-2">
        {!kind && (
          <>
        <Label htmlFor={inputId} className="sr-only">
          {t.sources.urlLabel}
        </Label>
        <Input
          id={inputId}
          type="url"
          inputMode="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder={t.sources.urlPlaceholder}
          className="h-10 min-w-0 flex-1 basis-64 bg-card"
        />
        <Button type="submit" className="h-10" disabled={adding || !url.trim()}>
          {adding ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconPlus aria-hidden />}
          {t.sources.addUrl}
        </Button>
          </>
        )}
        <Button type="button" variant="outline" className="h-10" disabled={Boolean(upload)} onClick={() => fileInput.current?.click()}>
          <IconPaperclip aria-hidden />
          {kind ? t.transcriptions.attach : t.sources.attach}
        </Button>
        <input ref={fileInput} type="file" accept={kind ? "audio/*" : ACCEPT} className="sr-only" tabIndex={-1} aria-hidden onChange={(e) => addFile(e.target.files?.[0])} />
        <p className="w-full text-sm text-muted-foreground">{kind ? t.transcriptions.attachHint : t.sources.attachHint}</p>
      </form>

      {upload && (
        <div className="rounded-md border border-border bg-card px-4 py-3" role="status">
          <p className="truncate text-sm">{t.sources.uploading(upload.name)}</p>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-primary transition-[width] duration-150" style={{ width: `${Math.round(upload.progress * 100)}%` }} />
          </div>
        </div>
      )}

      {error ? (
        <div>
          <p className="text-muted-foreground">{t.claims.errorTitle}</p>
          <Button variant="outline" className="mt-3" onClick={() => mutate()}>
            {t.claims.retry}
          </Button>
        </div>
      ) : !sources ? (
        <Skeleton className="h-24 w-full" />
      ) : sources.length === 0 ? (
        <p className={cn("rounded-md border border-dashed border-border px-4 py-5 text-muted-foreground")}>{kind ? t.transcriptions.empty : t.sources.empty}</p>
      ) : (
        <ul className="divide-y divide-border rounded-lg border border-border bg-card">
          {sources.map((s) => (
            <SourceRow key={s.id} ws={ws} source={s} onRemove={canRemove() ? () => remove(s) : undefined} />
          ))}
        </ul>
      )}
    </div>
  );
}
