"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { IconArrowSquareOut, IconArrowsClockwise, IconCircleNotch, IconGlobe, IconMapPin, IconRadio, IconWarning, IconX } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { CheckedLine, DemoTag, KindLabel, LoadFailed, Section, when } from "@/components/rubrique/bits";
import { MeteoPanel } from "@/components/rubrique/meteo-panel";
import type { AntenneRow, FeedEntry, FeedOut, MapOut, Meteo, Prefs } from "@/components/rubrique/types";
import { useMe } from "@/components/rubrique/use-me";
import { useWorkspaceSocket } from "@/hooks/use-workspace-socket";
import { api, fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/fr";
import { cn } from "@/lib/utils";
import { AntenneList } from "./antenne-list";
import { SignalsPanel, useSignalToasts } from "./signals-panel";
import { VeilleurView } from "./veilleur-view";

const v = t.rubrique.veille;
const KINDS = ["all", "tip", "sms", "clip", "press"] as const;
type Tab = (typeof KINDS)[number];
const ALL = "__all";

const VeilleMap = dynamic(() => import("./veille-map"), { ssr: false, loading: () => <Skeleton className="h-full w-full rounded-none" /> });

function qs(params: Record<string, string | null | undefined>) {
  const q = new URLSearchParams();
  for (const [k, val] of Object.entries(params)) if (val) q.set(k, val);
  const s = q.toString();
  return s ? `?${s}` : "";
}

function FeedRow({ ws, e, i }: { ws: string; e: FeedEntry; i: number }) {
  const linkClass = "font-bold text-pretty outline-none after:absolute after:inset-0 hover:underline focus-visible:after:ring-2 focus-visible:after:ring-ring focus-visible:after:ring-inset";
  const title = e.item_id ? (
    <Link href={`/w/${ws}/affirmations/${e.item_id}` as never} className={linkClass}>
      {e.title}
    </Link>
  ) : e.url ? (
    <a href={e.url} target="_blank" rel="noreferrer" className={linkClass}>
      {e.title}
      <IconArrowSquareOut className="ml-1.5 inline size-4 align-[-0.1em]" aria-hidden />
    </a>
  ) : (
    <span className="font-bold text-pretty">{e.title}</span>
  );
  const excerpt = e.text && e.text !== e.title ? e.text : null;
  return (
    <li className="arrive relative border-b border-border" style={{ "--i": Math.min(i, 12) } as React.CSSProperties}>
      <div className="grid gap-x-5 gap-y-1.5 py-3.5 transition-colors hover:bg-card sm:grid-cols-[5.5rem_minmax(0,1fr)] sm:px-2">
        <p className="flex items-baseline gap-3 sm:block">
          <time dateTime={e.at} className="block font-display font-bold tabular">
            {when(e.at)}
          </time>
          <KindLabel kind={e.kind} className="font-normal text-muted-foreground sm:mt-0.5" />
        </p>
        <div className="min-w-0">
          {title}
          {excerpt && <p className="mt-0.5 line-clamp-2 text-sm text-pretty text-muted-foreground">{excerpt}</p>}
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
            {e.ref && <span className="font-display font-bold text-foreground tabular">{v.tracked(e.ref)}</span>}
            {e.place?.name && (
              <span className="inline-flex items-center gap-1">
                <IconMapPin className="size-3.5" aria-hidden />
                {e.place.name}
              </span>
            )}
            {e.station && <span>{e.station}</span>}
            {e.beats.length > 0 && <span>{e.beats.join(", ")}</span>}
            {e.risk === "high" && (
              <span className="inline-flex items-center gap-1 font-bold text-foreground">
                <IconWarning className="size-4" aria-hidden />
                {v.highRisk}
              </span>
            )}
            {e.demo && <DemoTag />}
          </p>
          {e.already_checked && (
            <div className="mt-1.5">
              <CheckedLine checked={e.already_checked} ws={ws} />
            </div>
          )}
        </div>
      </div>
    </li>
  );
}

function DeskVeille({ ws }: { ws: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const raw = params.get("type");
  const tab: Tab = (KINDS as readonly string[]).includes(raw ?? "") ? (raw as Tab) : "all";
  const region = params.get("region");
  const beat = params.get("theme");
  const country = params.get("pays");
  const [refreshing, setRefreshing] = useState(false);

  const go = (next: Record<string, string | null>) => {
    const merged = { type: tab === "all" ? null : tab, region, theme: beat, pays: country, ...next };
    router.replace(`${pathname}${qs(merged)}` as never, { scroll: false });
  };

  const feedKey = `/workspaces/${ws}/veille${qs({ region, beat, kind: tab === "all" ? null : tab })}`;
  const feed = useSWR<FeedOut>(feedKey, fetcher, { keepPreviousData: true, refreshInterval: 60_000 });
  const map = useSWR<MapOut>(`/workspaces/${ws}/veille/map${qs({ beat, country })}`, fetcher, { keepPreviousData: true });
  // The menu above the map: the newsroom's country first, then where something circulated, then the world.
  const shown = map.data?.country ?? country ?? "";
  const countryChoices = map.data ? [...new Set([map.data.home, ...map.data.countries.map((c) => c.country)])] : [];
  const countOf = (c: string) => map.data?.countries.find((x) => x.country === c)?.last_7d ?? 0;
  const antenne = useSWR<AntenneRow[]>(`/workspaces/${ws}/antenne`, fetcher);
  const meteo = useSWR<Meteo>(`/workspaces/${ws}/meteo${qs({ region })}`, fetcher, { keepPreviousData: true });
  const prefs = useSWR<Prefs>(`/workspaces/${ws}/me/prefs`, fetcher);

  const reload = () => {
    void feed.mutate();
    void map.mutate();
    void antenne.mutate();
  };
  const toastSignal = useSignalToasts();
  const { online } = useWorkspaceSocket(ws, {
    "clip.created": reload,
    "clip.updated": reload,
    "item.created": reload,
    "item.updated": reload,
    "signal.matched": (p) => {
      toastSignal(p);
      void feed.mutate();
    },
    reconnected: reload,
  });

  async function refresh() {
    setRefreshing(true);
    try {
      await api(`/workspaces/${ws}/veille/refresh`, { method: "POST" });
      toast(v.refreshed);
      setTimeout(reload, 4000);
    } catch {
      toast.error(v.refreshFailed);
    } finally {
      setRefreshing(false);
    }
  }

  const counts = feed.data?.counts ?? {};
  const total = Object.values(counts).reduce((a, b) => a + (b ?? 0), 0);
  const regions = (map.data?.regions ?? []).filter((r) => r.last_7d > 0).sort((a, b) => b.last_7d - a.last_7d);

  return (
    <div className="@container mx-auto max-w-[90rem] pb-12 lg:px-8">
      <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4 px-4 pt-6 pb-5 lg:px-0 lg:pt-8">
        <div>
          <h1 className="page-title">{v.title}</h1>
          <p className="mt-1.5 text-muted-foreground">
            {v.lead(7)}
            {feed.data && <span className="tabular"> · {total}</span>}
            {!online && <span className="ml-2 font-bold text-foreground">{t.claims.offline}</span>}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" size="xl">
            <Link href={`${pathname}?antenne=1` as never}>
              <IconRadio aria-hidden />
              {t.rubrique.antenne.record}
            </Link>
          </Button>
          <Button variant="outline" size="xl" onClick={refresh} disabled={refreshing}>
            {refreshing ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconArrowsClockwise aria-hidden />}
            {refreshing ? v.refreshing : v.refresh}
          </Button>
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-2 px-4 pb-5 lg:px-0">
        <div role="tablist" aria-label={v.tabsLabel} className="-mx-4 flex basis-[calc(100%+2rem)] gap-1 overflow-x-auto px-4 pb-1 [scrollbar-width:none] lg:mx-0 lg:px-0 @3xl:basis-auto">
          {KINDS.map((k) => (
            <button
              key={k}
              type="button"
              role="tab"
              aria-selected={tab === k}
              onClick={() => go({ type: k === "all" ? null : k })}
              className={cn(
                "inline-flex h-11 shrink-0 items-center gap-2 rounded-md px-3 outline-none focus-visible:ring-2 focus-visible:ring-ring",
                tab === k ? "bg-foreground font-bold text-background" : "hover:bg-card",
              )}
            >
              {v.tabs[k]}
              <span className={cn("rounded-sm px-1.5 text-sm font-bold tabular", tab === k ? "bg-background/15" : "bg-muted")}>{k === "all" ? total : (counts[k] ?? 0)}</span>
            </button>
          ))}
        </div>
        {region && (
          <button
            type="button"
            onClick={() => go({ region: null })}
            aria-label={v.clearRegion(region)}
            className="inline-flex h-10 items-center gap-2 rounded-md border border-foreground bg-card px-3 text-sm font-bold outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <IconMapPin className="size-4" aria-hidden />
            {region}
            <IconX className="size-3.5" aria-hidden />
          </button>
        )}
        <Select value={beat ?? ALL} onValueChange={(x) => go({ theme: x === ALL ? null : x })}>
          <SelectTrigger aria-label={v.beat} className="h-10 w-auto min-w-40 bg-card">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{v.allBeats}</SelectItem>
            {(prefs.data?.beats_offered ?? []).map((b) => (
              <SelectItem key={b} value={b}>
                {b}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {feed.data && !feed.data.feeds_configured && <p className="mx-4 mb-5 text-sm text-muted-foreground lg:mx-0">{v.noFeeds}</p>}

      <div className="grid gap-x-10 gap-y-10 px-4 lg:px-0 @5xl:grid-cols-[minmax(0,1fr)_24rem]">
        <div className="min-w-0 space-y-8">
          <section aria-labelledby="carte" className="overflow-hidden rounded-md border border-border bg-card">
            <div className="flex flex-wrap items-start justify-between gap-3 px-4 pt-3 pb-3">
              <div className="min-w-0">
                <h2 id="carte" className="font-display text-lg font-bold">
                  {v.mapTitle}
                </h2>
                <p className="text-sm text-muted-foreground">{v.mapLead}</p>
              </div>
              {map.data && (
                <Select value={shown} onValueChange={(x) => go({ pays: x === map.data?.home ? null : x, region: null })}>
                  <SelectTrigger aria-label={v.country} className="h-10 w-auto min-w-40 bg-background font-bold">
                    <IconGlobe className="size-4" aria-hidden />
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {countryChoices.map((c) => (
                      <SelectItem key={c} value={c}>
                        {c}
                        {v.countryCount(countOf(c))}
                      </SelectItem>
                    ))}
                    <SelectItem value="monde">
                      {v.world}
                      {v.countryCount(map.data.countries.reduce((n, c) => n + c.last_7d, 0))}
                    </SelectItem>
                  </SelectContent>
                </Select>
              )}
            </div>
            <div className="isolate h-72 border-y border-border sm:h-[26rem]">
              <VeilleMap regions={map.data?.regions ?? []} selected={region} onSelect={(r) => go({ region: r })} country={shown} />
            </div>
            <div className="px-4 py-3">
              {regions.length > 0 && (
                <ul aria-label={v.mapList} className="flex flex-wrap gap-1.5">
                  {regions.map((r) => (
                    <li key={r.region}>
                      <button
                        type="button"
                        aria-pressed={r.region === region}
                        onClick={() => go({ region: r.region === region ? null : r.region })}
                        className={cn(
                          "inline-flex h-9 items-center gap-2 rounded-md border px-2.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring",
                          r.region === region ? "border-primary bg-primary font-bold text-primary-foreground" : "border-input hover:bg-raised",
                        )}
                      >
                        {r.region}
                        <span className="font-bold tabular">{r.last_7d}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <p className="mt-2 text-xs text-muted-foreground">
                {v.mapLegend}
                {map.data && map.data.unplaced > 0 && <> {v.unplaced(map.data.unplaced)}.</>}
              </p>
            </div>
          </section>

          <section aria-label={v.tabs[tab]}>
            {feed.error ? (
              <LoadFailed onRetry={() => void feed.mutate()} />
            ) : !feed.data ? (
              <div className="space-y-2">
                {Array.from({ length: 5 }, (_, i) => (
                  <Skeleton key={i} className="h-16 w-full" />
                ))}
              </div>
            ) : feed.data.entries.length === 0 ? (
              <p className="rounded-md border border-dashed border-border px-4 py-6 text-center font-bold">{v.empty}</p>
            ) : (
              <ul className="border-t border-foreground">
                {feed.data.entries.map((e, i) => (
                  <FeedRow key={`${e.kind}-${e.id}`} ws={ws} e={e} i={i} />
                ))}
              </ul>
            )}
          </section>
        </div>

        <aside className="min-w-0 space-y-10">
          <Section id="antenne" title={t.rubrique.antenne.title} lead={t.rubrique.antenne.lead}>
            {antenne.data ? <AntenneList ws={ws} rows={antenne.data} actions onChanged={reload} /> : <Skeleton className="h-32 w-full" />}
          </Section>
          <Section id="mots" title={t.rubrique.signals.title} lead={t.rubrique.signals.lead}>
            <SignalsPanel ws={ws} />
          </Section>
          {meteo.data && <MeteoPanel ws={ws} meteo={meteo.data} id="meteo-veille" />}
        </aside>
      </div>
    </div>
  );
}

/**
 * Veille: what circulates (tips, SMS questions, radio clips, press) on a map and in a feed, with
 * the radio grouped by claim, the watched words and the season. A veilleur sees only À l'antenne,
 * the recorder; anyone else reaches it with `?antenne=1`.
 */
export function VeilleView() {
  const { ws } = useParams<{ ws: string }>();
  const params = useSearchParams();
  const { joined } = useMe(ws);
  if (!joined) {
    return (
      <div className="mx-auto max-w-[90rem] space-y-3 px-4 pt-8 lg:px-8">
        <Skeleton className="h-12 w-48" />
        <Skeleton className="h-72 w-full" />
      </div>
    );
  }
  if (params.get("antenne") === "1") return <VeilleurView ws={ws} desk />;
  return <DeskVeille ws={ws} />;
}
