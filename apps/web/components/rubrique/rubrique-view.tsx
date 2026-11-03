"use client";

import type { Item } from "@checky/shared";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { IconArrowRight, IconArrowSquareOut, IconCopy, IconMapPin, IconPencilSimple, IconRadio, IconScan, IconWarning } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusLabel, toClaim, VerdictBadge } from "@/components/claims/verdict";
import { AlertLevel, AlertsList } from "@/components/veille/alerts-panel";
import { AntenneList } from "@/components/veille/antenne-list";
import { useSignalToasts } from "@/components/veille/signals-panel";
import { useMe } from "@/components/rubrique/use-me";
import { useWorkspaceSocket } from "@/hooks/use-workspace-socket";
import { api, fetcher } from "@/lib/api";
import { dateFormat, getLang, t } from "@/lib/i18n/live";
import { BeatPicker } from "./beat-picker";
import { CheckedLine, DemoTag, KindLabel, LoadFailed, Section, when } from "./bits";
import { MeteoPanel } from "./meteo-panel";
import type { Alert, AngleCard, AntenneRow, Circulating, ContactCard, FigureCard, Rubrique } from "./types";

const r = t.rubrique;
// The API says the day in French (« mardi 3 novembre 2026 »); other languages format `today` themselves.
const todayFmt = dateFormat({ weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });

/** Where a line of « Ce qui circule » leads: the dossier, the article, or the Veille. */
function target(ws: string, c: Circulating): { href: string; external: boolean } {
  if (c.item_id) return { href: `/w/${ws}/claims/${c.item_id}`, external: false };
  if (c.kind === "press" && c.url) return { href: c.url, external: true };
  return { href: `/w/${ws}/watch?type=${c.kind}`, external: false };
}

/** What else Checky gathered about the rumour of a row: its alert, or what the radio said. */
type Echo = { alert: Alert | null; antenne: AntenneRow | null };

/** One rumour, one line: a dossier and the radio, SMS or tips that repeat it share their first row. */
function oneRowPerRumour(list: Circulating[]): Circulating[] {
  const best = new Map<string, Circulating>();
  for (const c of list) {
    if (!c.item_id) continue;
    const kept = best.get(c.item_id);
    if (!kept || (!kept.item && c.item)) best.set(c.item_id, c);
  }
  const out: Circulating[] = [];
  const placed = new Set<string>();
  for (const c of list) {
    if (!c.item_id) out.push(c);
    else if (!placed.has(c.item_id)) {
      placed.add(c.item_id);
      out.push(best.get(c.item_id) ?? c);
    }
  }
  return out;
}

function channels(kinds: Record<string, number>): string {
  return Object.keys(kinds)
    .map((k) => r.circulating.channel[k as keyof typeof r.circulating.channel] ?? k)
    .join(", ");
}

function CirculatingRow({ ws, c, i, echo }: { ws: string; c: Circulating; i: number; echo: Echo }) {
  const go = target(ws, c);
  const claim = c.item ? toClaim(c.item) : null;
  const linkClass =
    "block font-bold text-pretty outline-none after:absolute after:inset-0 hover:underline focus-visible:after:ring-2 focus-visible:after:ring-ring focus-visible:after:ring-inset md:text-lg md:leading-snug";
  const { alert, antenne } = echo;
  // One state per row: the workflow word on the left; on the right only a verdict, when there is one.
  const verdict = claim && (claim.verdict || claim.suggested);
  return (
    <li className="arrive relative border-b border-border" style={{ "--i": Math.min(i, 12) } as React.CSSProperties}>
      <div className="grid gap-x-5 gap-y-2 py-3.5 transition-colors hover:bg-card sm:grid-cols-[5.5rem_minmax(0,1fr)] sm:px-2 @4xl:grid-cols-[5.5rem_minmax(0,1fr)_auto]">
        <p className="flex items-baseline gap-3 sm:block">
          <time dateTime={c.at} className="block text-sm font-medium tabular">
            {when(c.at)}
          </time>
          <KindLabel kind={c.kind} className="font-normal text-muted-foreground sm:mt-0.5" />
        </p>
        <div className="min-w-0">
          {go.external ? (
            <a href={go.href} target="_blank" rel="noreferrer" className={linkClass}>
              {c.title}
              <IconArrowSquareOut className="ml-1.5 inline size-4 align-[-0.1em]" aria-label={r.circulating.read} />
            </a>
          ) : (
            <Link href={go.href as never} className={linkClass}>
              {c.title}
            </Link>
          )}
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
            {claim && <StatusLabel status={claim.status} />}
            {claim && <span className="text-foreground tabular">{r.circulating.dossier(claim.ref)}</span>}
            {c.place?.name && (
              <span className="inline-flex items-center gap-1">
                <IconMapPin className="size-3.5" aria-hidden />
                {c.place.name}
              </span>
            )}
            {c.station && <span>{c.station}</span>}
            {c.beats.length > 0 && <span>{c.beats.join(", ")}</span>}
            {c.seasons.map((s) => (
              <span key={s}>{r.circulating.seasonal(s)}</span>
            ))}
            {c.demo && <DemoTag />}
          </p>
          {alert ? (
            <Link
              href={`/w/${ws}/watch#alerte-${alert.id}` as never}
              className="relative z-10 mt-2 inline-flex flex-wrap items-center gap-x-2 gap-y-1 text-sm hover:underline"
            >
              <span className="font-medium">{r.circulating.alert}</span>
              <AlertLevel level={alert.level} adjusted={Boolean(alert.override)} />
              <span className="text-muted-foreground">{r.circulating.alertSeen(alert.facts.reports, channels(alert.facts.kinds))}</span>
            </Link>
          ) : (
            antenne &&
            c.kind !== "clip" && (
              <Link
                href={`/w/${ws}/watch?type=clip` as never}
                className="relative z-10 mt-2 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:underline"
              >
                <IconRadio className="size-4" aria-hidden />
                {r.circulating.heard(antenne.stations.length)}
              </Link>
            )
          )}
          {c.already_checked && (
            <div className="mt-1.5">
              <CheckedLine checked={c.already_checked} ws={ws} />
            </div>
          )}
        </div>
        {verdict && (
          <div className="flex items-center sm:col-start-2 @4xl:col-start-auto @4xl:justify-end">
            <VerdictBadge claim={claim} />
          </div>
        )}
      </div>
    </li>
  );
}

function DossierShort({ ws, items, empty }: { ws: string; items: Item[]; empty: string }) {
  if (items.length === 0) return <p className="text-sm text-muted-foreground">{empty}</p>;
  return (
    <ul className="space-y-4">
      {items.map((item) => {
        const c = toClaim(item);
        return (
          <li key={item.id} className="relative">
            <Link href={`/w/${ws}/claims/${item.id}` as never} className="block font-bold text-pretty outline-none after:absolute after:inset-0 hover:underline focus-visible:after:ring-2 focus-visible:after:ring-ring">
              {item.title}
            </Link>
            <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
              <span className="tabular">{c.ref}</span>
              <StatusLabel status={c.status} />
              <VerdictBadge claim={c} />
            </p>
          </li>
        );
      })}
    </ul>
  );
}

function Figures({ figures }: { figures: FigureCard[] }) {
  if (figures.length === 0) return <p className="text-sm text-muted-foreground">{r.figures.empty}</p>;
  return (
    <ul className="space-y-5">
      {figures.map((f) => (
        <li key={f.id}>
          <p className="flex items-baseline gap-2">
            <span className="font-display text-2xl leading-none font-bold tabular">{f.value}</span>
            {f.unit && <span className="font-medium">{f.unit}</span>}
          </p>
          <p className="mt-1 text-sm font-medium text-pretty">{f.label}</p>
          <p className="text-sm text-muted-foreground">
            {f.as_of && <span className="tabular">{r.figures.asOf(f.as_of)} · </span>}
            {f.source_url ? (
              <a href={f.source_url} target="_blank" rel="noreferrer" className="underline underline-offset-2">
                {f.source_name}
              </a>
            ) : (
              f.source_name
            )}
            {f.is_demo && <DemoTag className="ml-2" />}
          </p>
          {f.old && (
            <p className="mt-1 inline-flex items-center gap-1.5 text-sm font-bold">
              <IconWarning className="size-4 shrink-0" aria-hidden />
              {r.figures.old}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}

function Contacts({ contacts }: { contacts: ContactCard[] }) {
  if (contacts.length === 0) return <p className="text-sm text-muted-foreground">{r.contacts.empty}</p>;
  return (
    <>
      <ul className="space-y-5">
        {contacts.map((c) => (
          <li key={c.id}>
            <p className="font-bold">
              {c.name}
              {c.is_demo && <DemoTag className="ml-2 align-[0.1em]" />}
            </p>
            <p className="text-sm text-muted-foreground">{[c.role, c.institution].filter(Boolean).join(" · ")}</p>
            <p className="mt-1 flex flex-wrap gap-x-4 text-sm">
              {c.phone && (
                <a href={`tel:${c.phone.replace(/\s+/g, "")}`} className="font-medium underline underline-offset-4">
                  {r.contacts.call} <span className="font-normal tabular">{c.phone}</span>
                </a>
              )}
              {c.email && (
                <a href={`mailto:${c.email}`} className="font-medium underline underline-offset-4">
                  {r.contacts.write}
                </a>
              )}
            </p>
          </li>
        ))}
      </ul>
      <p className="mt-4 text-xs text-muted-foreground">{r.contacts.declared}</p>
    </>
  );
}

function Angles({ ws, angles }: { ws: string; angles: AngleCard[] }) {
  return (
    <ul className="grid gap-3 @3xl:grid-cols-3">
      {angles.map((a) => (
        <li
          key={`${a.kind}-${a.title}`}
          className="relative flex flex-col rounded-md border border-border bg-card p-4 transition-colors hover:border-input hover:bg-raised"
        >
          <p className="text-sm text-muted-foreground">
            {a.kind === "kept" && a.item_id ? (
              <Link href={`/w/${ws}/claims/${a.item_id}` as never} className="relative z-10 font-bold text-foreground underline underline-offset-4">
                {r.anglesBox.kept(a.ref ?? "")}
              </Link>
            ) : (
              r.anglesBox.piste
            )}
          </p>
          {/* The whole card opens the angle: one link per card, named by its title. */}
          <Link
            href={`/w/${ws}/angles?sujet=${encodeURIComponent(a.title)}` as never}
            className="mt-1 font-display text-lg leading-snug font-bold text-pretty outline-none after:absolute after:inset-0 after:rounded-md focus-visible:after:ring-2 focus-visible:after:ring-ring"
          >
            {a.title}
          </Link>
          {a.why && <p className="mt-1 text-sm text-pretty text-muted-foreground">{a.why}</p>}
          <span className="mt-auto flex justify-end pt-3 text-muted-foreground">
            <IconArrowRight className="size-4" aria-hidden />
          </span>
        </li>
      ))}
    </ul>
  );
}

function PageSkeleton() {
  return (
    <div className="grid gap-8 px-4 lg:px-0 @5xl:grid-cols-[minmax(0,1fr)_22rem]">
      <div className="space-y-3">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
      <div className="space-y-3">
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    </div>
  );
}

/**
 * Ma rubrique: a journalist's morning page, read like the front of a newspaper. What circulates on
 * my beats and places, the rumours the season brings back, what the radio says, my dossiers and
 * those waiting for a signature, the figures and the people to call. One action: Vérifier.
 */
export function RubriqueView() {
  const { ws } = useParams<{ ws: string }>();
  const { joined } = useMe(ws);
  const [all, setAll] = useState(false);
  const [editing, setEditing] = useState(false);
  const query = all ? "?beat=*&region=*" : "";
  const key = joined ? `/workspaces/${ws}/rubrique${query}` : null;
  const { data, error, mutate } = useSWR<Rubrique>(key, fetcher, { refreshInterval: 120_000 });
  const alerts = useSWR<Alert[]>(joined ? `/workspaces/${ws}/alerts` : null, fetcher, { refreshInterval: 120_000 });

  const refresh = () => void mutate();
  const toastSignal = useSignalToasts();
  useWorkspaceSocket(joined ? ws : undefined, {
    "item.created": refresh,
    "item.updated": refresh,
    "clip.created": refresh,
    "clip.updated": refresh,
    "alert.updated": () => void alerts.mutate(),
    "signal.matched": toastSignal,
    reconnected: refresh,
  });

  async function copyBrief() {
    try {
      const { text } = await api<{ text: string }>(`/workspaces/${ws}/rubrique/brief${query}`);
      await navigator.clipboard.writeText(text);
      toast(r.page.briefCopied);
    } catch {
      toast.error(r.page.briefFailed);
    }
  }

  const beats = data?.beats.length ? data.beats.join(", ") : null;
  const places = data?.regions.length ? data.regions.join(", ") : null;

  // One rumour, one place on the page: a dossier's alert and radio passages go on its row, and the
  // context column keeps only what « Ce qui circule » does not already show.
  const rows = data ? oneRowPerRumour(data.circulating) : [];
  // A row is known by its dossier (`item_id`) and by its feed key (`clip:<id>`, `sms:<id>`), the
  // same keys the alerts and the radio groups use.
  const onPage = new Set(rows.map((c) => c.item_id).filter((id): id is string => Boolean(id)));
  const onPageKeys = new Set(rows.map((c) => c.id));
  const openAlerts = (alerts.data ?? []).filter((a) => a.state === "open");
  // An alert sits on the row of its own dossier (the one it is titled after), else on the row of a
  // report it gathered: never on every row it touches.
  const homeOf = (a: Alert) =>
    a.members.find((m) => m.kind === "item" && m.item_id && m.title === a.title)?.item_id ??
    a.members.find((m) => m.kind === "item" && m.item_id)?.item_id ??
    null;
  const alertOn = (a: Alert, c: Circulating) => {
    const home = homeOf(a);
    return home ? c.item_id === home : a.members.some((m) => m.key === c.id);
  };
  const echo = (c: Circulating): Echo => ({
    alert: openAlerts.find((a) => alertOn(a, c)) ?? null,
    antenne: data?.antenne.find((x) => (c.item_id !== null && x.item_id === c.item_id) || x.clip_ids.some((id) => `clip:${id}` === c.id)) ?? null,
  });
  const otherAlerts = openAlerts.filter((a) => !rows.some((c) => alertOn(a, c)));
  const otherRadio = (data?.antenne ?? []).filter((x) => !((x.item_id && onPage.has(x.item_id)) || x.clip_ids.some((id) => onPageKeys.has(`clip:${id}`))));
  // The calendar's angles belong to their season in the Météo; the Angles block keeps the rest.
  const seasonOf = (a: AngleCard) => (a.kind === "piste" ? data?.meteo.seasons.find((s) => a.title.startsWith(s.name)) : undefined);
  const angleHref = (season: string) => {
    const a = data?.angles.find((x) => seasonOf(x)?.name === season);
    return `/w/${ws}/angles?sujet=${encodeURIComponent(a?.title ?? season)}`;
  };
  const otherAngles = (data?.angles ?? []).filter((a) => !seasonOf(a));

  return (
    <div className="@container mx-auto max-w-[90rem] pb-12 lg:px-8">
      <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4 border-b border-foreground px-4 pt-6 pb-4 lg:px-0 lg:pt-8">
        <div className="min-w-0">
          <h1 className="page-title">{r.page.title}</h1>
          <p className="mt-2 text-muted-foreground first-letter:uppercase">
            {data ? (getLang() === "fr" ? data.today_label : todayFmt.format(new Date(`${data.today.slice(0, 10)}T12:00:00Z`))) : " "}
            {data && (
              <>
                {" · "}
                {beats ? (
                  <>
                    {r.page.themes} <span className="font-bold text-foreground">{beats}</span>
                  </>
                ) : (
                  r.page.allBeats
                )}
                {" · "}
                {places ? (
                  <>
                    {r.page.places} <span className="font-bold text-foreground">{places}</span>
                  </>
                ) : (
                  r.page.allPlaces
                )}
              </>
            )}
          </p>
          {data && (
            <p className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-sm">
              <button type="button" onClick={() => setEditing((v) => !v)} aria-expanded={editing} className="inline-flex items-center gap-1.5 font-bold underline underline-offset-4">
                <IconPencilSimple className="size-4" aria-hidden />
                {r.page.edit}
              </button>
              <button type="button" onClick={() => setAll((v) => !v)} className="font-bold underline underline-offset-4">
                {all ? r.page.backToMine : r.page.showAll}
              </button>
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="xl" onClick={copyBrief} disabled={!data} title={r.page.briefHint}>
            <IconCopy aria-hidden />
            {r.page.brief}
          </Button>
          <Button asChild variant="action" size="xl">
            <Link href={`/w/${ws}/verify` as never}>
              <IconScan aria-hidden />
              {r.page.verify}
            </Link>
          </Button>
        </div>
      </header>

      {editing && data && (
        <div className="px-4 pt-5 lg:px-0">
          <BeatPicker
            ws={ws}
            prefs={data.prefs}
            onCancel={() => setEditing(false)}
            onSaved={() => {
              setEditing(false);
              setAll(false);
              void mutate();
            }}
          />
        </div>
      )}

      <div className="pt-8">
        {error ? (
          <LoadFailed onRetry={refresh} />
        ) : !data ? (
          <PageSkeleton />
        ) : (
          // Phone order (DOM): what circulates, my dossiers, the context, the references, the angles.
          // From @5xl the context column stands on the right beside the first four rows.
          <div className="grid gap-x-10 gap-y-10 px-4 sm:gap-y-14 lg:px-0 @5xl:grid-cols-[minmax(0,1fr)_22rem] @5xl:grid-rows-[auto_auto_auto_1fr]">
            <Section id="circule" tone="lead" title={r.circulating.title} lead={r.circulating.lead} className="min-w-0 @5xl:col-start-1 @5xl:row-start-1">
              {data.circulating.length === 0 ? (
                <div className="rounded-md border border-dashed border-border px-4 py-6 text-center">
                  <p className="font-bold">{r.circulating.empty}</p>
                  <p className="mt-1 text-sm text-muted-foreground">{r.circulating.emptyHint}</p>
                </div>
              ) : (
                <ul className="border-t border-border">
                  {rows.map((c, i) => (
                    <CirculatingRow key={`${c.kind}-${c.id}`} ws={ws} c={c} i={i} echo={echo(c)} />
                  ))}
                </ul>
              )}
            </Section>

            <div className="grid min-w-0 gap-x-8 gap-y-10 sm:gap-y-14 @3xl:grid-cols-2 @5xl:col-start-1 @5xl:row-start-2">
              <Section id="a-signer" title={r.toSign.title} lead={data.to_sign.length > 0 ? r.toSign.lead : undefined}>
                <DossierShort ws={ws} items={data.to_sign} empty={r.toSign.empty} />
              </Section>
              <Section id="mes-dossiers" title={r.mineList.title}>
                {/* A dossier waiting for a signature is listed once, under « À signer ». */}
                <DossierShort
                  ws={ws}
                  items={data.mine.filter((m) => !data.to_sign.some((s) => s.id === m.id))}
                  empty={data.mine.length > 0 ? r.mineList.allToSign : r.mineList.empty}
                />
              </Section>
            </div>

            <aside className="min-w-0 space-y-10 sm:space-y-12 @5xl:col-start-2 @5xl:row-span-4 @5xl:row-start-1">
              {otherAlerts.length > 0 && (
                <Section
                  id="alertes"
                  tone="aside"
                  title={t.rubrique.alerts.title}
                  lead={r.alerts.leadRubrique}
                  action={
                    <Link href={`/w/${ws}/watch#alertes` as never} className="shrink-0 text-sm font-bold underline underline-offset-4">
                      {t.rubrique.alerts.all}
                    </Link>
                  }
                >
                  <AlertsList ws={ws} alerts={otherAlerts} limit={3} />
                </Section>
              )}
              <MeteoPanel ws={ws} meteo={data.meteo} tone="aside" angleHref={angleHref} />
              {otherRadio.length > 0 && (
                <Section
                  id="antenne"
                  tone="aside"
                  title={r.antenne.title}
                  lead={r.antenne.leadRubrique}
                  action={
                    <Link href={`/w/${ws}/watch?type=clip` as never} className="shrink-0 text-sm font-bold underline underline-offset-4">
                      {r.antenne.all}
                    </Link>
                  }
                >
                  <AntenneList ws={ws} rows={otherRadio} limit={3} />
                </Section>
              )}
            </aside>

            <div className="grid min-w-0 gap-x-8 gap-y-10 sm:gap-y-14 @3xl:grid-cols-2 @5xl:col-start-1 @5xl:row-start-3">
              <Section id="chiffres" title={r.figures.title}>
                <Figures figures={data.figures} />
              </Section>
              <Section id="contacts" title={r.contacts.title}>
                <Contacts contacts={data.contacts} />
              </Section>
            </div>

            {otherAngles.length > 0 && (
              <Section
                id="angles"
                title={r.anglesBox.title}
                className="min-w-0 self-start @5xl:col-start-1 @5xl:row-start-4"
                action={
                  <Link href={`/w/${ws}/angles` as never} className="shrink-0 text-sm font-bold underline underline-offset-4">
                    {r.anglesBox.explore}
                  </Link>
                }
              >
                <Angles ws={ws} angles={otherAngles} />
              </Section>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
