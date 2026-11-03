"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { DemoTag, LoadFailed, Section } from "@/components/rubrique/bits";
import { api, fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/live";
import { IconArrowLeft, IconCircleNotch, IconMicrophone, IconStop } from "@/lib/icons";
import { cn } from "@/lib/utils";
import { EvidenceLine, FlagLabel, flagOf, questionFor, type Evidence } from "./flag";
import type { ChunkResult, ClaimOut, Pack, ShowOut } from "./types";

const s = t.studio;
const CHUNK_MS = 10_000;

function clock(at: number) {
  const s0 = Math.max(0, Math.floor(at));
  const h = Math.floor(s0 / 3600);
  const m = Math.floor((s0 % 3600) / 60);
  const ss = String(s0 % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

/** One claim the crew spotted: its flag (never a verdict), its evidence and what the producer does. */
function ClaimCard({
  ws,
  c,
  show,
  onChanged,
}: {
  ws: string;
  c: ClaimOut;
  show: ShowOut;
  onChanged: () => void;
}) {
  const f = s.flag;
  const [question, setQuestion] = useState(c.question || questionFor(c as never));
  const [busy, setBusy] = useState(false);
  const { kind, evidence } = flagOf(c as never);
  const speaker = show.speakers.find((sp) => sp.id === c.speaker_id);

  async function act(path: string, body?: unknown) {
    setBusy(true);
    try {
      await api(`/workspaces/${ws}/studio/${show.id}/claims/${c.id}${path}`, {
        method: "POST",
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      toast.success(f.sent);
      onChanged();
    } catch {
      toast.error(f.failed);
    } finally {
      setBusy(false);
    }
  }

  return (
    <article data-flag={kind} className="border-b border-border py-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground tabular">
            {clock(c.at_s)}
            {speaker ? ` · ${speaker.name}` : ""} · {f.origin[c.origin]}
          </p>
          <p className="mt-1 text-pretty font-bold">{c.text}</p>
        </div>
        <FlagLabel kind={kind} />
      </div>
      <ul className="mt-2 grid gap-1.5">
        {(evidence as Evidence[]).slice(0, 3).map((e, i) => (
          <li key={i} className="rounded-md border border-border px-3 py-2">
            <EvidenceLine e={e} />
          </li>
        ))}
        {kind === "no_source" && <li className="text-sm text-muted-foreground">{f.noSourceNote}</li>}
      </ul>
      {c.status === "dismissed" ? (
        <p className="mt-2 text-sm text-muted-foreground">{f.status.dismissed}</p>
      ) : c.status === "sent" ? (
        <p className="mt-2 text-sm font-bold">{f.status.sent}</p>
      ) : (
        <div className="mt-3 grid gap-2">
          <label className="grid gap-1">
            <span className="text-sm font-bold">{f.question}</span>
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              rows={2}
              className="rounded-md border border-border bg-background px-3 py-2 text-sm"
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <Button variant="action" disabled={busy} onClick={() => act("/send", { question })}>
              {busy ? f.sending : f.send}
            </Button>
            <Button variant="ghost" disabled={busy} onClick={() => act("/dismiss")}>
              {f.dismiss}
            </Button>
          </div>
        </div>
      )}
    </article>
  );
}

export function ShowRoom() {
  const { ws, id } = useParams<{ ws: string; id: string }>();
  const { data: show, error, mutate } = useSWR<ShowOut>(`/workspaces/${ws}/studio/${id}`, fetcher, {
    refreshInterval: 5000,
  });
  const [tab, setTab] = useState<"live" | "debate" | "bilan">("live");
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [typed, setTyped] = useState("");
  const [speaker, setSpeaker] = useState<string | "">("");
  const [pack, setPack] = useState<Pack | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const seq = useRef(0);
  const startedAt = useRef(0);

  useEffect(() => {
    if (!show) return;
    seq.current = show.chunks;
  }, [show]);

  // Before the show: the fiches are fetched once and kept by the browser (IndexedDB, through the SW).
  useEffect(() => {
    if (!show || show.status !== "draft") return;
    api<Pack>(`/workspaces/${ws}/studio/${id}/pack`)
      .then(setPack)
      .catch(() => setPack(null));
  }, [show, ws, id]);

  const sendChunk = useCallback(
    async (blob: Blob, at: number) => {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/workspaces/${ws}/studio/${id}/chunk?seq=${seq.current}&start_s=${Math.round(at)}&duration_s=10`,
        { method: "POST", body: blob, headers: { "Content-Type": blob.type || "audio/webm" } },
      ).catch(() => null);
      seq.current += 1;
      if (res?.ok) {
        const out = (await res.json()) as ChunkResult;
        if (out.error) toast(out.error === "stt_unavailable" ? s.live.sttDown : out.error);
        mutate();
      }
    },
    [ws, id, mutate],
  );

  async function start() {
    setBusy(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      await api(`/workspaces/${ws}/studio/${id}/start`, { method: "POST" });
      const rec = new MediaRecorder(stream, { mimeType: MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "" });
      startedAt.current = Date.now();
      seq.current = 0;
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) void sendChunk(e.data, (Date.now() - startedAt.current) / 1000 - CHUNK_MS / 1000);
      };
      rec.start(CHUNK_MS);
      recorder.current = rec;
      setRecording(true);
      mutate();
    } catch {
      toast.error(s.prep.micDenied);
    } finally {
      setBusy(false);
    }
  }

  async function end() {
    if (!window.confirm(s.live.endConfirm)) return;
    setBusy(true);
    recorder.current?.stop();
    recorder.current?.stream.getTracks().forEach((tr) => tr.stop());
    setRecording(false);
    try {
      await api(`/workspaces/${ws}/studio/${id}/end`, { method: "POST" });
      setTab("bilan");
      mutate();
    } finally {
      setBusy(false);
    }
  }

  async function addClaim() {
    if (typed.trim().length < 3) return;
    setBusy(true);
    try {
      await api(`/workspaces/${ws}/studio/${id}/claims`, {
        method: "POST",
        body: JSON.stringify({ text: typed.trim(), speaker_id: speaker || null }),
      });
      setTyped("");
      mutate();
    } catch {
      toast.error(s.flag.failed);
    } finally {
      setBusy(false);
    }
  }

  async function setSpeakerNow(speakerId: string | null) {
    await api(`/workspaces/${ws}/studio/${id}/speaker`, {
      method: "POST",
      body: JSON.stringify({ speaker_id: speakerId }),
    }).catch(() => undefined);
    mutate();
  }

  async function follow(c: ClaimOut) {
    setBusy(true);
    try {
      const made = await api<{ item_id: string; ref: string | null }>(
        `/workspaces/${ws}/studio/${id}/claims/${c.id}/follow`,
        { method: "POST" },
      );
      toast.success(s.bilan.followed(made.ref ?? ""));
      mutate();
    } catch {
      toast.error(s.bilan.followFailed);
    } finally {
      setBusy(false);
    }
  }

  if (error) return <LoadFailed onRetry={() => mutate()} />;
  if (!show)
    return (
      <p className="mx-auto flex max-w-[70ch] items-center gap-2 px-4 pt-8 text-muted-foreground">
        <IconCircleNotch className="size-4 animate-spin" aria-hidden /> Studio
      </p>
    );

  const pending = show.claim_list.filter((c) => c.status === "pending");
  const duration = show.duration_s || 0;

  return (
    <div className="mx-auto max-w-[88rem] px-4 pt-6 pb-24 lg:px-8">
      <nav className="flex items-center justify-between gap-3">
        <Link href={`/w/${ws}/studio` as never} className="inline-flex items-center gap-1.5 text-sm font-bold hover:underline">
          <IconArrowLeft className="size-4" aria-hidden /> {s.list.title}
        </Link>
        <Link
          href={`/w/${ws}/studio/${id}/presenter` as never}
          target="_blank"
          className="text-sm font-bold underline underline-offset-4"
        >
          {s.prep.presenterLink}
        </Link>
      </nav>

      <header className="mt-4 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="page-title flex flex-wrap items-center gap-2">
            <IconMicrophone className="size-6" aria-hidden /> {show.title}
            {show.is_demo && <DemoTag />}
          </h1>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 text-sm text-muted-foreground">
            <span>{s.list.status[show.status]}</span>
            {show.station && <span>{show.station}</span>}
            {show.status !== "draft" && <span className="tabular">{clock(duration)}</span>}
            <span>{s.live.queue(pending.length)}</span>
          </p>
        </div>
        {show.status === "draft" && (
          <Button variant="action" onClick={start} disabled={busy}>
            {busy ? s.prep.starting : s.prep.start}
          </Button>
        )}
        {show.status === "live" && (
          <div className="flex items-center gap-2">
            <span className={cn("inline-flex items-center gap-1.5 font-bold", recording ? "" : "text-muted-foreground")}>
              <span className={cn("size-2 rounded-full border border-foreground", recording && "bg-foreground")} aria-hidden />
              {recording ? s.live.onAir : s.live.paused}
            </span>
            <Button variant="outline" onClick={end} disabled={busy} className="gap-1.5">
              <IconStop className="size-4" aria-hidden /> {busy ? s.live.ending : s.live.end}
            </Button>
          </div>
        )}
      </header>

      {show.status === "draft" && (
        <Section title={s.prep.title} id="prep" className="mt-6">
          <p className="text-sm font-bold">{s.prep.pack}</p>
          <p className="mt-1 text-sm text-muted-foreground">
            {pack ? s.prep.packCounts(pack.verdicts.length, pack.figures.length, pack.registry.length) : s.prep.packing}
          </p>
          {pack && <p className="mt-1 text-sm text-muted-foreground">{s.prep.savedOffline}</p>}
          <p className="mt-4 text-sm text-muted-foreground">{s.prep.micDenied}</p>
        </Section>
      )}

      {show.status !== "draft" && (
        <div role="tablist" aria-label={s.list.title} className="mt-6 flex gap-1 border-b border-border">
          {(
            [
              ["live", s.live.flags],
              ["debate", s.debate.title],
              ["bilan", s.bilan.title],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              role="tab"
              aria-selected={tab === key}
              onClick={() => setTab(key)}
              className={cn(
                "-mb-px border-b-2 px-3 py-2 text-sm font-bold whitespace-nowrap",
                tab === key ? "border-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {show.status !== "draft" && tab === "live" && (
        <div className="mt-6 grid gap-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <div className="min-w-0">
            <p className="text-sm font-bold text-muted-foreground">{s.live.modeCautious}</p>
            <h2 className="mt-3 font-display text-lg font-bold">{s.live.flags}</h2>
            {pending.length === 0 && (
              <p className="mt-2 text-muted-foreground">{s.live.flagsEmpty}</p>
            )}
            <div className="mt-2 border-t border-foreground">
              {pending.map((c) => (
                <ClaimCard key={c.id} ws={ws} c={c} show={show} onChanged={() => mutate()} />
              ))}
            </div>
          </div>
          <aside className="grid content-start gap-6">
            <div>
              <label className="grid gap-1">
                <span className="text-sm font-bold">{s.live.type}</span>
                <span className="text-sm text-muted-foreground">{s.live.typeLead}</span>
                <textarea
                  value={typed}
                  onChange={(e) => setTyped(e.target.value)}
                  rows={3}
                  placeholder={show.language === "mg" ? s.live.typeMgPlaceholder : s.live.typePlaceholder}
                  className="rounded-md border border-border bg-background px-3 py-2 text-sm"
                />
              </label>
              {show.speakers.length > 0 && (
                <label className="mt-2 grid gap-1">
                  <span className="text-sm font-bold">{s.live.speakers}</span>
                  <select
                    value={speaker}
                    onChange={(e) => setSpeaker(e.target.value)}
                    className="h-10 rounded-md border border-border bg-background px-2"
                  >
                    <option value="">{s.live.nobody}</option>
                    {show.speakers.map((sp) => (
                      <option key={sp.id} value={sp.id}>
                        {sp.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <Button variant="action" className="mt-2" onClick={addClaim} disabled={busy || typed.trim().length < 3}>
                {busy ? s.live.adding : s.live.add}
              </Button>
            </div>
            <div>
              <h2 className="font-display text-lg font-bold">{s.live.transcript}</h2>
              <p className="mt-1 max-h-[24rem] overflow-auto text-sm whitespace-pre-wrap text-muted-foreground">
                {show.segments.length
                  ? show.segments.map((g) => `[${clock(g.start)}] ${g.text}`).join("\n")
                  : show.language === "mg"
                    ? s.live.transcriptMg
                    : s.live.transcriptEmpty}
              </p>
            </div>
            {show.speakers.length > 0 && show.status === "live" && (
              <div>
                <h2 className="font-display text-lg font-bold">{s.live.speakers}</h2>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <Button variant="outline" size="sm" onClick={() => setSpeakerNow(null)}>
                    {s.live.nobody}
                  </Button>
                  {show.speakers.map((sp) => (
                    <Button
                      key={sp.id}
                      variant={show.current_speaker_id === sp.id ? "action" : "outline"}
                      size="sm"
                      onClick={() => setSpeakerNow(sp.id)}
                    >
                      {sp.name}
                    </Button>
                  ))}
                </div>
              </div>
            )}
          </aside>
        </div>
      )}

      {show.status !== "draft" && tab === "debate" && (
        <Section title={s.debate.title} id="debate" lead={s.debate.lead} className="mt-6">
          <ul className="border-t border-foreground">
            {show.by_speaker.map((row) => (
              <li key={row.speaker_id ?? "none"} className="border-b border-border py-3">
                <p className="font-bold">{row.name ?? s.debate.unassigned}</p>
                <p className="text-sm text-muted-foreground">
                  {s.debate.line(row.claims, row.contradicted_official)} · {s.debate.consistent(row.consistent)} ·{" "}
                  {s.debate.noSource(row.no_source)}
                </p>
                {row.camp && <p className="text-xs text-muted-foreground">{row.camp}</p>}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {show.status !== "draft" && tab === "bilan" && (
        <Section
          title={s.bilan.title}
          id="bilan"
          lead={s.bilan.lead(show.claim_list.length, show.sent)}
          className="mt-6"
        >
          {show.started_at && (
            <p className="text-sm text-muted-foreground">
              {s.bilan.aired(new Date(show.started_at).toLocaleDateString("fr-FR"), clock(duration))}
            </p>
          )}
          {show.claim_list.length === 0 ? (
            <p className="mt-4 text-muted-foreground">{s.bilan.noClaims}</p>
          ) : (
            <ol className="mt-4 border-t border-foreground">
              {show.claim_list.map((c) => {
                const { kind } = flagOf(c as never);
                return (
                  <li key={c.id} className="border-b border-border py-4">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-xs text-muted-foreground tabular">{clock(c.at_s)}</p>
                        <p className="mt-1 text-pretty font-bold">{c.text}</p>
                        <div className="mt-1.5">
                          <FlagLabel kind={kind} />
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-1.5">
                        {c.clip?.url ? (
                          <a href={c.clip.url} className="text-sm font-bold underline underline-offset-4">
                            {s.bilan.listen(clock(c.at_s))}
                          </a>
                        ) : (
                          <span className="text-xs text-muted-foreground">{s.bilan.noClip}</span>
                        )}
                        {c.item_id ? (
                          <Link
                            href={`/w/${ws}/claims/${c.item_id}` as never}
                            className="text-sm font-bold underline underline-offset-4"
                          >
                            {s.bilan.openDossier(c.ref ?? "")}
                          </Link>
                        ) : (
                          <Button variant="outline" size="sm" onClick={() => follow(c)} disabled={busy}>
                            {s.bilan.follow}
                          </Button>
                        )}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
          {show.segments.length > 0 && (
            <details className="mt-6">
              <summary className="cursor-pointer font-bold">{s.bilan.transcript}</summary>
              <p className="mt-2 text-sm whitespace-pre-wrap text-muted-foreground">
                {show.segments.map((g) => `[${clock(g.start)}] ${g.text}`).join("\n")}
              </p>
            </details>
          )}
        </Section>
      )}
    </div>
  );
}
