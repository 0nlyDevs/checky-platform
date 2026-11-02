"use client";

import type { Item } from "@fanilo/shared";
import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { type Gap, fmtShort, type Stop, type Trajet } from "@/components/dossier/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { api, fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/fr";
import { IconArrowSquareOut, IconBroadcast, IconCircleNotch, IconPlus } from "@/lib/icons";
import { cn } from "@/lib/utils";

const tr = t.dossier.trajet;
const CHANNELS = ["facebook", "whatsapp", "tiktok", "radio", "sms", "press", "web", "poster", "institution", "voice", "other"] as const;

const selectClass =
  "h-10 w-full rounded-md border border-input bg-background px-3 text-base outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30";

function region(stop: { location: Record<string, unknown> }) {
  const l = stop.location ?? {};
  return typeof l.region === "string" ? l.region : typeof l.name === "string" ? l.name : null;
}

/** One stop on a line: a disc on the rule (dashed for the rumour, solid for the truth), what and when. */
function StopRow({ stop, side, last }: { stop: Stop; side: "rumour" | "truth"; last: boolean }) {
  const count = typeof stop.proof?.count === "number" && stop.proof.count > 1 ? stop.proof.count : null;
  const url = typeof stop.proof?.url === "string" ? stop.proof.url : null;
  const note = typeof stop.proof?.note === "string" ? stop.proof.note : null;
  const where = region(stop);
  return (
    <li className="relative grid grid-cols-[1rem_minmax(0,1fr)] gap-x-3 pb-4 last:pb-0">
      {!last && <span aria-hidden className={cn("absolute top-4 bottom-0 left-[0.4375rem] w-px", side === "truth" ? "bg-foreground" : "bg-border")} />}
      <span
        aria-hidden
        className={cn(
          "relative z-10 mt-1 size-3.5 rounded-full",
          side === "truth" ? "bg-foreground" : "border-2 border-dashed border-foreground bg-card",
        )}
      />
      <div className="min-w-0 text-sm">
        <p className="flex flex-wrap items-baseline gap-x-2">
          <span className="font-bold">{tr.channels[stop.channel] ?? stop.channel}</span>
          {count && <span className="font-display font-bold tabular">{tr.count(count)}</span>}
          <time dateTime={stop.at} className="text-muted-foreground tabular">
            {fmtShort(stop.at)}
          </time>
        </p>
        <p className="text-pretty">
          {stop.place}
          {where && !stop.place.includes(where) && <span className="text-muted-foreground"> · {where}</span>}
        </p>
        {note && <p className="text-muted-foreground text-pretty">{note}</p>}
        <p className="flex flex-wrap gap-x-2 text-muted-foreground">
          <span>{tr.status[stop.status] ?? stop.status}</span>
          {stop.derived && <span>· {tr.derived}</span>}
          {url && (
            <a href={url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 underline decoration-border underline-offset-4 hover:text-foreground">
              {t.dossier.facts.open}
              <IconArrowSquareOut className="size-3" aria-hidden />
            </a>
          )}
        </p>
      </div>
    </li>
  );
}

function Line({ title, stops, side, empty }: { title: string; stops: Stop[]; side: "rumour" | "truth"; empty: string }) {
  return (
    <div className="min-w-0">
      <h3 className="mb-3 flex items-baseline gap-2 font-bold">
        {title}
        <span className="font-display tabular text-muted-foreground">{stops.length}</span>
      </h3>
      {stops.length ? (
        <ol aria-label={title}>
          {stops.map((s, i) => (
            <StopRow key={s.id ?? `${s.channel}-${s.at}`} stop={s} side={side} last={i === stops.length - 1} />
          ))}
        </ol>
      ) : (
        <p className="text-sm text-muted-foreground">{empty}</p>
      )}
    </div>
  );
}

/** A member notes where they saw the rumour (or sent the truth), with what they saw. */
function AddStop({ ws, item, onAdded }: { ws: string; item: Item; onAdded: () => void }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const published = item.status === "published";

  async function add(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const v = Object.fromEntries(new FormData(form).entries()) as Record<string, string>;
    setBusy(true);
    try {
      await api(`/workspaces/${ws}/items/${item.id}/routes`, {
        method: "POST",
        body: JSON.stringify({ side: v.side, channel: v.channel, place: v.place, note: v.note, url: v.url || null, at: new Date().toISOString() }),
      });
      form.reset();
      setOpen(false);
      onAdded();
    } catch {
      toast.error(tr.failed);
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        <IconPlus aria-hidden />
        {tr.addTitle}
      </Button>
    );
  }
  return (
    <form onSubmit={add} className="grid gap-3 rounded-md border border-border bg-card p-4 sm:grid-cols-2">
      <div className="space-y-1.5">
        <Label htmlFor="stop-side">{tr.side}</Label>
        <select id="stop-side" name="side" className={selectClass} defaultValue="rumour">
          <option value="rumour">{tr.rumour}</option>
          {published && <option value="truth">{tr.truth}</option>}
        </select>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="stop-channel">{tr.channel}</Label>
        <select id="stop-channel" name="channel" className={selectClass} defaultValue="facebook">
          {CHANNELS.map((c) => (
            <option key={c} value={c}>
              {tr.channels[c]}
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-1.5 sm:col-span-2">
        <Label htmlFor="stop-place">{tr.place}</Label>
        <Input id="stop-place" name="place" required maxLength={300} className="h-10" />
      </div>
      <div className="space-y-1.5 sm:col-span-2">
        <Label htmlFor="stop-note">{tr.note}</Label>
        <textarea id="stop-note" name="note" required minLength={5} maxLength={1000} rows={2} className="w-full resize-y rounded-md border border-input bg-background px-3 py-2 text-base outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30" />
      </div>
      <div className="space-y-1.5 sm:col-span-2">
        <Label htmlFor="stop-url">{tr.proof}</Label>
        <Input id="stop-url" name="url" type="url" className="h-10" />
      </div>
      <div className="flex gap-2 sm:col-span-2">
        <Button type="submit" size="sm" disabled={busy}>
          {busy && <IconCircleNotch className="animate-spin" aria-hidden />}
          {tr.add}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={() => setOpen(false)}>
          {tr.cancel}
        </Button>
      </div>
    </form>
  );
}

/**
 * « Le trajet »: where the rumour went, where the truth followed, and the routes it has not taken
 * yet. Every stop was noted by someone with its proof; nothing is inferred from a click.
 */
export function RoutePanel({ ws, item, onDiffuseHere }: { ws: string; item: Item; onDiffuseHere?: (gap: Gap) => void }) {
  const { data, mutate } = useSWR<Trajet>(`/workspaces/${ws}/items/${item.id}/trajet`, fetcher);
  const published = item.status === "published";

  return (
    <section aria-labelledby="trajet" className="space-y-5">
      <header>
        <h2 id="trajet" className="font-display text-xl font-bold">
          {tr.title}
        </h2>
        <p className="mt-0.5 max-w-[70ch] text-sm text-muted-foreground">{tr.lead}</p>
      </header>

      {!data ? (
        <Skeleton className="h-40 w-full" />
      ) : (
        <>
          <p className="font-medium text-pretty">{data.summary}</p>
          <div className="grid gap-6 rounded-md border border-border bg-card p-4 md:grid-cols-2 md:p-5">
            <Line title={tr.rumour} stops={data.rumour} side="rumour" empty={tr.noRumour} />
            <Line title={tr.truth} stops={data.truth} side="truth" empty={tr.noTruth} />
          </div>
          {data.gaps.length > 0 && (
            <div>
              <h3 className="font-bold">{tr.gaps}</h3>
              <ul className="mt-2 divide-y divide-border border-y border-border">
                {data.gaps.map((g) => (
                  <li key={`${g.channel}-${g.place}`} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 py-2.5 text-sm">
                    <span className="min-w-0">
                      <span className="font-bold">{tr.channels[g.channel] ?? g.channel}</span> · {g.place}
                      {region(g) && !g.place.includes(region(g)!) && <span className="text-muted-foreground"> · {region(g)}</span>}
                    </span>
                    {published && onDiffuseHere && (
                      <Button size="sm" variant="outline" onClick={() => onDiffuseHere(g)}>
                        <IconBroadcast aria-hidden />
                        {tr.diffuseHere}
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
      <AddStop ws={ws} item={item} onAdded={() => mutate()} />
    </section>
  );
}
