"use client";

import type { Item } from "@fanilo/shared";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { IconArrowRight, IconArrowSquareOut, IconCopy, IconMapPin, IconPencilSimple, IconScan, IconWarning } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { claimSteps, StepLine } from "@/components/flow/step-line";
import { StatusLabel, toClaim, VerdictBadge } from "@/components/claims/verdict";
import { AntenneList } from "@/components/veille/antenne-list";
import { useSignalToasts } from "@/components/veille/signals-panel";
import { useMe } from "@/components/rubrique/use-me";
import { useWorkspaceSocket } from "@/hooks/use-workspace-socket";
import { api, fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/fr";
import { cn } from "@/lib/utils";
import { BeatPicker } from "./beat-picker";
import { CheckedLine, DemoTag, KindLabel, LoadFailed, Section, when } from "./bits";
import { MeteoPanel } from "./meteo-panel";
import type { AngleCard, Circulating, ContactCard, FigureCard, Rubrique } from "./types";

const r = t.rubrique;

/** Where a line of « Ce qui circule » leads: the dossier, the article, or the Veille. */
function target(ws: string, c: Circulating): { href: string; external: boolean } {
  if (c.item_id) return { href: `/w/${ws}/affirmations/${c.item_id}`, external: false };
  if (c.kind === "press" && c.url) return { href: c.url, external: true };
  return { href: `/w/${ws}/veille?type=${c.kind}`, external: false };
}

function CirculatingRow({ ws, c, i }: { ws: string; c: Circulating; i: number }) {
  const go = target(ws, c);
  const claim = c.item ? toClaim(c.item) : null;
  const linkClass =
    "block font-bold text-pretty outline-none after:absolute after:inset-0 hover:underline focus-visible:after:ring-2 focus-visible:after:ring-ring focus-visible:after:ring-inset md:text-[1.05rem]";
  return (
    <li className="arrive relative border-b border-border" style={{ "--i": Math.min(i, 12) } as React.CSSProperties}>
      <div className="grid gap-x-5 gap-y-2 py-3.5 transition-colors hover:bg-card sm:grid-cols-[5.5rem_minmax(0,1fr)] sm:px-2 @4xl:grid-cols-[5.5rem_minmax(0,1fr)_13rem]">
        <p className="flex items-baseline gap-3 sm:block">
          <time dateTime={c.at} className="block font-display font-bold tabular">
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
            {claim && <span className="font-bold text-foreground tabular">{claim.ref}</span>}
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
          {c.already_checked && (
            <div className="mt-1.5">
              <CheckedLine checked={c.already_checked} ws={ws} />
            </div>
          )}
        </div>
        {claim && (
          <div className="flex items-center gap-3 sm:col-start-2 @4xl:col-start-auto @4xl:flex-col @4xl:items-end @4xl:justify-center">
            <StepLine variant="mini" states={claimSteps(claim)} />
            <VerdictBadge claim={claim} compact />
          </div>
        )}
      </div>
    </li>
  );
}

function DossierShort({ ws, items, empty }: { ws: string; items: Item[]; empty: string }) {
  if (items.length === 0) return <p className="text-sm text-muted-foreground">{empty}</p>;
  return (
    <ul className="divide-y divide-border">
      {items.map((item) => {
        const c = toClaim(item);
        return (
          <li key={item.id} className="relative py-2.5 first:pt-0">
            <Link href={`/w/${ws}/affirmations/${item.id}` as never} className="block font-bold text-pretty outline-none after:absolute after:inset-0 hover:underline focus-visible:after:ring-2 focus-visible:after:ring-ring">
              {item.title}
            </Link>
            <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
              <span className="font-display font-bold tabular">{c.ref}</span>
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
    <ul className="divide-y divide-border">
      {figures.map((f) => (
        <li key={f.id} className="py-2.5 first:pt-0">
          <p className="flex items-baseline gap-2">
            <span className="font-display text-2xl leading-none font-bold tabular">{f.value}</span>
            {f.unit && <span className="font-bold">{f.unit}</span>}
          </p>
          <p className="mt-1 text-sm font-bold text-pretty">{f.label}</p>
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
      <ul className="divide-y divide-border">
        {contacts.map((c) => (
          <li key={c.id} className="py-2.5 first:pt-0">
            <p className="font-bold">
              {c.name}
              {c.is_demo && <DemoTag className="ml-2 align-[0.1em]" />}
            </p>
            <p className="text-sm text-muted-foreground">{[c.role, c.institution].filter(Boolean).join(" · ")}</p>
            <p className="mt-1 flex flex-wrap gap-x-4 text-sm">
              {c.phone && (
                <a href={`tel:${c.phone.replace(/\s+/g, "")}`} className="font-bold underline underline-offset-4">
                  {r.contacts.call} <span className="font-normal tabular">{c.phone}</span>
                </a>
              )}
              {c.email && (
                <a href={`mailto:${c.email}`} className="font-bold underline underline-offset-4">
                  {r.contacts.write}
                </a>
              )}
            </p>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-muted-foreground">{r.contacts.declared}</p>
    </>
  );
}

function Angles({ ws, angles }: { ws: string; angles: AngleCard[] }) {
  return (
    <ul className="grid gap-3 @3xl:grid-cols-3">
      {angles.map((a) => (
        <li key={`${a.kind}-${a.title}`} className="flex flex-col rounded-md border border-border bg-card p-4">
          <p className="text-sm text-muted-foreground">
            {a.kind === "kept" && a.item_id ? (
              <Link href={`/w/${ws}/affirmations/${a.item_id}` as never} className="font-bold text-foreground underline underline-offset-4">
                {r.anglesBox.kept(a.ref ?? "")}
              </Link>
            ) : (
              r.anglesBox.piste
            )}
          </p>
          <p className="mt-1 font-display text-lg leading-snug font-bold text-pretty">{a.title}</p>
          {a.why && <p className="mt-1 text-sm text-pretty text-muted-foreground">{a.why}</p>}
          <Link
            href={`/w/${ws}/angles?sujet=${encodeURIComponent(a.title)}` as never}
            className="mt-auto inline-flex items-center gap-1.5 pt-3 text-sm font-bold underline underline-offset-4"
          >
            {r.anglesBox.explore}
            <IconArrowRight className="size-4" aria-hidden />
          </Link>
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
  const router = useRouter();
  const { role } = useMe(ws);
  const [all, setAll] = useState(false);
  const [editing, setEditing] = useState(false);
  const query = all ? "?beat=*&region=*" : "";
  const key = role && role !== "veilleur" ? `/workspaces/${ws}/rubrique${query}` : null;
  const { data, error, mutate } = useSWR<Rubrique>(key, fetcher, { refreshInterval: 120_000 });

  // A veilleur's only screen is À l'antenne.
  useEffect(() => {
    if (role === "veilleur") router.replace(`/w/${ws}/veille` as never);
  }, [role, router, ws]);

  const refresh = () => void mutate();
  const toastSignal = useSignalToasts();
  useWorkspaceSocket(role && role !== "veilleur" ? ws : undefined, {
    "item.created": refresh,
    "item.updated": refresh,
    "clip.created": refresh,
    "clip.updated": refresh,
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

  const beats = data?.beats.length ? data.beats.join(", ") : r.page.allBeats;
  const places = data?.regions.length ? data.regions.join(", ") : r.page.allPlaces;

  return (
    <div className="@container mx-auto max-w-[90rem] pb-12 lg:px-8">
      <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4 border-b border-foreground px-4 pt-6 pb-4 lg:px-0 lg:pt-8">
        <div className="min-w-0">
          <h1 className="page-title">{r.page.title}</h1>
          <p className="mt-2 text-muted-foreground first-letter:uppercase">
            {data?.today_label ?? " "}
            {data && (
              <>
                {" · "}
                <span className="font-bold text-foreground">{beats}</span>
                {" · "}
                <span className="font-bold text-foreground">{places}</span>
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
          <Button variant="outline" size="xl" onClick={copyBrief} disabled={!data}>
            <IconCopy aria-hidden />
            {r.page.brief}
          </Button>
          <Button asChild variant="action" size="xl">
            <Link href={`/w/${ws}/verifier` as never}>
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

      <div className="pt-6">
        {error ? (
          <LoadFailed onRetry={refresh} />
        ) : !data ? (
          <PageSkeleton />
        ) : (
          <div className="grid gap-x-10 gap-y-10 px-4 lg:px-0 @5xl:grid-cols-[minmax(0,1fr)_22rem]">
            <div className="min-w-0 space-y-10">
              <Section id="circule" title={r.circulating.title} lead={r.circulating.lead}>
                {data.circulating.length === 0 ? (
                  <div className="rounded-md border border-dashed border-border px-4 py-6 text-center">
                    <p className="font-bold">{r.circulating.empty}</p>
                    <p className="mt-1 text-sm text-muted-foreground">{r.circulating.emptyHint}</p>
                  </div>
                ) : (
                  <ul className="border-t border-border">
                    {data.circulating.map((c, i) => (
                      <CirculatingRow key={`${c.kind}-${c.id}`} ws={ws} c={c} i={i} />
                    ))}
                  </ul>
                )}
              </Section>

              <div className="grid gap-x-8 gap-y-10 @3xl:grid-cols-2">
                <Section id="mes-dossiers" title={r.mineList.title}>
                  <DossierShort ws={ws} items={data.mine} empty={r.mineList.empty} />
                </Section>
                <Section id="a-signer" title={r.toSign.title} lead={data.to_sign.length > 0 ? r.toSign.lead : undefined}>
                  <DossierShort ws={ws} items={data.to_sign} empty={r.toSign.empty} />
                </Section>
              </div>

              {data.angles.length > 0 && (
                <Section
                  id="angles"
                  title={r.anglesBox.title}
                  action={
                    <Link href={`/w/${ws}/angles` as never} className="shrink-0 text-sm font-bold underline underline-offset-4">
                      {r.anglesBox.explore}
                    </Link>
                  }
                >
                  <Angles ws={ws} angles={data.angles} />
                </Section>
              )}
            </div>

            <aside className={cn("min-w-0 space-y-10")}>
              <MeteoPanel ws={ws} meteo={data.meteo} />
              <Section
                id="antenne"
                title={r.antenne.title}
                action={
                  <Link href={`/w/${ws}/veille?type=clip` as never} className="shrink-0 text-sm font-bold underline underline-offset-4">
                    {r.antenne.all}
                  </Link>
                }
              >
                <AntenneList ws={ws} rows={data.antenne} limit={3} />
              </Section>
              <Section id="chiffres" title={r.figures.title}>
                <Figures figures={data.figures} />
              </Section>
              <Section id="contacts" title={r.contacts.title}>
                <Contacts contacts={data.contacts} />
              </Section>
            </aside>
          </div>
        )}
      </div>
    </div>
  );
}
