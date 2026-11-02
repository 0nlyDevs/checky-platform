"use client";

import type { Item } from "@fanilo/shared";
import Link from "next/link";
import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError, fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/fr";
import { IconArrowSquareOut, IconBroadcast, IconCheck, IconCircleNotch, IconCopy, IconPlus, IconX } from "@/lib/icons";
import { cn } from "@/lib/utils";
import type { Formats } from "./types";

const f = t.dossier.diffuse;
const CHANNELS = ["whatsapp", "facebook", "radio", "sms", "web", "press", "poster", "institution", "tiktok", "voice", "other"] as const;

export type RouteDraft = { channel: string; place: string; location?: Record<string, unknown> | null };

const words = (s: string) => s.trim().split(/\s+/).filter(Boolean).length;

/** One ready text: its name, the text as it will be sent, a copy button and « envoyé » to tick. */
function FormatBlock({
  id,
  label,
  text,
  meta,
  ticked,
  onTick,
  draft,
  locked,
}: {
  id: string;
  label: string;
  text: string;
  meta?: string;
  ticked: boolean;
  onTick: (on: boolean) => void;
  draft?: boolean;
  /** A Malagasy draft nobody has reread yet: shown, but neither copied nor counted as sent. */
  locked?: boolean;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <li className={cn("rounded-md border bg-card p-4", draft ? "border-dashed border-foreground/60" : "border-border")}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h4 className="font-bold">{label}</h4>
        {meta && <span className="text-sm text-muted-foreground tabular">{meta}</span>}
      </div>
      <p className="mt-2 whitespace-pre-wrap text-pretty">{text}</p>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <Button
          size="sm"
          variant="outline"
          disabled={locked}
          onClick={async () => {
            await navigator.clipboard.writeText(text).catch(() => null);
            setCopied(true);
            onTick(true);
          }}
        >
          {copied ? <IconCheck aria-hidden /> : <IconCopy aria-hidden />}
          {locked ? f.mgLocked : copied ? f.copied : f.copy}
        </Button>
        <label htmlFor={`fmt-${id}`} className="inline-flex items-center gap-2 text-sm">
          <input
            id={`fmt-${id}`}
            type="checkbox"
            checked={ticked && !locked}
            disabled={locked}
            onChange={(e) => onTick(e.target.checked)}
            className="size-4 accent-foreground"
          />
          {t.dossier.trajet.status.sent}
        </label>
      </div>
    </li>
  );
}

/**
 * « Diffuser »: the signed verdict in every format a newsroom sends (radio line, flash, SMS, posts,
 * a note to the institution, the card, the poster). Checky sends nothing: the journalist copies,
 * sends from their own tools, then notes the routes, which become truth stops on the trajet.
 */
export function DiffusePanel({
  ws,
  item,
  routes,
  onRoutes,
}: {
  ws: string;
  item: Item;
  routes: RouteDraft[];
  onRoutes: (routes: RouteDraft[]) => void;
}) {
  const published = item.status === "published";
  const key = published ? `/workspaces/${ws}/items/${item.id}/diffusion` : null;
  const { data, error, isLoading } = useSWR<Formats>(key, fetcher, { revalidateOnFocus: false });
  const { mutate } = useSWRConfig();
  const [ticked, setTicked] = useState<Set<string>>(new Set());
  const [rereading, setRereading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [channel, setChannel] = useState<string>("whatsapp");
  const [place, setPlace] = useState("");

  const tick = (id: string) => (on: boolean) =>
    setTicked((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });

  async function send() {
    setBusy(true);
    try {
      const out = await api<{ formats: string[]; dropped: string[] }>(`/workspaces/${ws}/items/${item.id}/diffuse`, {
        method: "POST",
        body: JSON.stringify({
          routes: routes.map((r) => ({ channel: r.channel, place: r.place, location: r.location ?? null })),
          formats: [...ticked].filter((id) => reread || !id.endsWith("_mg")),
        }),
      });
      toast.success(f.sent(routes.length));
      if (out.dropped.length) toast(f.dropped);
      onRoutes([]);
      mutate(`/workspaces/${ws}/items/${item.id}/trajet`);
      mutate(`/workspaces/${ws}/items/${item.id}/diffusion`);
    } catch {
      toast.error(f.failed);
    } finally {
      setBusy(false);
    }
  }

  // The reread vouches for the exact strings on screen (`mg_hash`); any change locks them again.
  const reread = !!data?.relu_mg?.current;
  async function markReread(on: boolean) {
    if (!data) return;
    setRereading(true);
    try {
      await api(`/workspaces/${ws}/items/${item.id}/relu-mg`, on ? { method: "POST", body: JSON.stringify({ mg_hash: data.mg_hash }) } : { method: "DELETE" });
    } catch (e) {
      toast.error(e instanceof ApiError && e.code === "mg_changed" ? f.mgChanged : f.failed);
    } finally {
      await mutate(`/workspaces/${ws}/items/${item.id}/diffusion`);
      setRereading(false);
    }
  }

  const code = error instanceof ApiError ? error.code : null;
  const blocked = !published ? f.notPublished : code === "private_workspace" ? f.privateNewsroom : code === "missing_reason" ? f.missingReason : error ? f.loadFailed : null;

  const fr: { id: string; text: string | null | undefined; meta?: string }[] = data
    ? [
        { id: "radio_line", text: data.radio_line },
        { id: "flash", text: data.flash, meta: f.words(words(data.flash)) },
        { id: "sms", text: data.sms, meta: f.chars(data.sms.length) },
        { id: "text", text: data.text },
        { id: "institution_alert", text: data.institution_alert },
        { id: "card_fr", text: data.card.fr },
      ]
    : [];
  const mg: { id: string; text: string | null | undefined; meta?: string }[] = data
    ? [
        { id: "radio_line_mg", text: data.mg?.radio_line },
        { id: "sms_mg", text: data.mg?.sms, meta: data.mg?.sms ? f.chars(data.mg.sms.length) : undefined },
        { id: "text_mg", text: data.mg?.text },
        { id: "card_mg", text: data.card.mg },
      ].filter((x) => x.text)
    : [];

  return (
    <section id="diffuser" aria-labelledby="diffuse" className="scroll-mt-6 space-y-5">
      <header>
        <h2 id="diffuse" className="font-display text-xl font-bold">
          {f.title}
        </h2>
        <p className="mt-0.5 max-w-[70ch] text-sm text-muted-foreground">{f.lead}</p>
      </header>

      {blocked && <p className="rounded-md border border-dashed border-border px-4 py-3 text-muted-foreground">{blocked}</p>}
      {published && isLoading && (
        <div aria-busy aria-label={f.loading} className="space-y-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      )}

      {data && (
        <>
          <p className="text-sm text-muted-foreground">{f.writtenBy[data.written_by]}</p>
          <ul className="grid gap-3 lg:grid-cols-2">
            {fr
              .filter((x) => x.text)
              .map((x) => (
                <FormatBlock key={x.id} id={x.id} label={f.formats[x.id]} text={x.text!} meta={x.meta} ticked={ticked.has(x.id)} onTick={tick(x.id)} />
              ))}
          </ul>

          {mg.length > 0 && (
            <div className="space-y-3">
              <div>
                <h3 className="font-bold">{f.mgTitle}</h3>
                <p className="text-sm text-muted-foreground">{f.mgLead}</p>
              </div>
              <ul className="grid gap-3 lg:grid-cols-2">
                {mg.map((x) => (
                  <FormatBlock key={x.id} id={x.id} label={f.formats[x.id]} text={x.text!} meta={x.meta} ticked={ticked.has(x.id)} onTick={tick(x.id)} draft locked={!reread} />
                ))}
              </ul>
              <label htmlFor="relu-mg" className="inline-flex items-center gap-2 text-sm font-medium">
                <input
                  id="relu-mg"
                  type="checkbox"
                  checked={reread}
                  disabled={rereading || !data.mg_hash}
                  onChange={(e) => markReread(e.target.checked)}
                  className="size-4 accent-foreground"
                />
                {f.mgReviewed}
              </label>
              {data.relu_mg && (
                <p className="text-sm text-muted-foreground">{reread ? f.mgReviewedBy(data.relu_mg.name) : f.mgStale(data.relu_mg.name)}</p>
              )}
            </div>
          )}

          <div className="grid gap-4 rounded-md border border-border bg-card p-4 md:grid-cols-2">
            <div>
              <h3 className="font-bold">{f.poster}</h3>
              <p className="mt-0.5 text-sm text-muted-foreground">{f.posterLead}</p>
              <Button asChild size="sm" variant="outline" className="mt-3">
                <Link href={`/w/${ws}/affirmations/${item.id}/affiche`} target="_blank">
                  <IconArrowSquareOut aria-hidden />
                  {f.posterOpen}
                </Link>
              </Button>
            </div>
            <dl className="space-y-2 text-sm">
              <div>
                <dt className="text-muted-foreground">{f.permalink}</dt>
                <dd className="break-all">
                  <a href={data.permalink} target="_blank" rel="noreferrer" className="underline decoration-border underline-offset-4 hover:decoration-foreground">
                    {data.permalink}
                  </a>
                </dd>
              </div>
              {data.short_link && (
                <div>
                  <dt className="text-muted-foreground">{f.short}</dt>
                  <dd className="font-display font-bold break-all">{data.short_link}</dd>
                </div>
              )}
            </dl>
          </div>

          <div className="space-y-3">
            <div>
              <h3 className="font-bold">{f.routes}</h3>
              <p className="text-sm text-muted-foreground">{f.routesLead}</p>
            </div>
            {routes.length > 0 && (
              <ul className="divide-y divide-border border-y border-border">
                {routes.map((r, i) => (
                  <li key={`${r.channel}-${r.place}-${i}`} className="flex items-center justify-between gap-3 py-2 text-sm">
                    <span>
                      <span className="font-bold">{t.dossier.trajet.channels[r.channel] ?? r.channel}</span> · {r.place}
                    </span>
                    <Button size="icon-sm" variant="ghost" aria-label={f.remove} onClick={() => onRoutes(routes.filter((_, j) => j !== i))}>
                      <IconX aria-hidden />
                    </Button>
                  </li>
                ))}
              </ul>
            )}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (!place.trim()) return;
                onRoutes([...routes, { channel, place: place.trim() }]);
                setPlace("");
              }}
              className="flex flex-wrap items-end gap-2"
            >
              <div className="space-y-1.5">
                <Label htmlFor="route-channel">{f.channel}</Label>
                <select
                  id="route-channel"
                  value={channel}
                  onChange={(e) => setChannel(e.target.value)}
                  className="h-10 rounded-md border border-input bg-background px-3 text-base outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30"
                >
                  {CHANNELS.map((c) => (
                    <option key={c} value={c}>
                      {t.dossier.trajet.channels[c]}
                    </option>
                  ))}
                </select>
              </div>
              <div className="min-w-48 flex-1 space-y-1.5">
                <Label htmlFor="route-place">{f.place}</Label>
                <Input id="route-place" value={place} onChange={(e) => setPlace(e.target.value)} maxLength={300} className="h-10" />
              </div>
              <Button type="submit" variant="outline" className="h-10" disabled={!place.trim()}>
                <IconPlus aria-hidden />
                {f.addRoute}
              </Button>
            </form>
            <Button variant="action" size="xl" onClick={send} disabled={busy || routes.length === 0}>
              {busy ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconBroadcast aria-hidden />}
              {busy ? f.sending : f.send(routes.length)}
            </Button>
          </div>
        </>
      )}
    </section>
  );
}
