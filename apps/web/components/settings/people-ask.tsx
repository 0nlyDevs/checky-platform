"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { MG_REGIONS } from "@/components/settings/regions";
import { Skeleton } from "@/components/ui/skeleton";
import { fetcher } from "@/lib/api";
import { dateFormat, t } from "@/lib/i18n/live";
import { IconArrowRight, IconChatCircle } from "@/lib/icons";

const q = t.team.settings.questions;
const day = dateFormat({ day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });
const PERIODS = [1, 7, 30] as const;
const select =
  "mt-1 h-9 rounded-md border border-input bg-background px-2.5 text-sm outline-none focus-visible:border-foreground focus-visible:ring-2 focus-visible:ring-foreground/15";

type Group = {
  text: string;
  count: number;
  regions: Record<string, number>;
  channels: Record<string, number>;
  waiting: number;
  last_at: string;
  item_id: string | null;
  item_ref: string | null;
  item_status: string | null;
};

/**
 * « Ce que les gens demandent »: the public's questions (SMS line, « Me prévenir » on the site)
 * routed to this newsroom, grouped when they ask the same thing. Contacts never appear here.
 * Exported for other desk pages (Ma rubrique, Veille) to embed.
 */
export function PeopleAsk({ ws }: { ws: string }) {
  const [region, setRegion] = useState("");
  const [days, setDays] = useState<(typeof PERIODS)[number]>(7);
  const { data, error } = useSWR<Group[]>(`/workspaces/${ws}/questions?days=${days}${region ? `&region=${encodeURIComponent(region)}` : ""}`, fetcher);

  return (
    <section aria-labelledby="ask-title" className="rounded-lg border border-border bg-card p-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0 flex-1 basis-72">
          <h2 id="ask-title" className="font-semibold">
            {q.title}
          </h2>
          <p className="mt-1 max-w-prose text-sm text-muted-foreground">{q.lead}</p>
        </div>
        <div className="flex flex-wrap gap-3">
          <label className="block text-sm font-medium">
            {q.region}
            <select value={region} onChange={(e) => setRegion(e.target.value)} className={`block ${select}`}>
              <option value="">{q.allRegions}</option>
              {MG_REGIONS.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm font-medium">
            {q.period}
            <select value={days} onChange={(e) => setDays(Number(e.target.value) as (typeof PERIODS)[number])} className={`block ${select}`}>
              {PERIODS.map((d) => (
                <option key={d} value={d}>
                  {q.days(d)}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
      {error ? (
        <p className="mt-4 text-sm" role="alert">
          {q.failed}
        </p>
      ) : !data ? (
        <Skeleton className="mt-4 h-28 w-full" />
      ) : !data.length ? (
        <p className="mt-4 text-sm text-muted-foreground">{q.empty}</p>
      ) : (
        <ol className="mt-4 divide-y divide-border rounded-md border border-border">
          {data.map((g, i) => (
            <li key={`${g.text}-${i}`} className="flex flex-wrap items-start gap-x-4 gap-y-2 px-4 py-3">
              <IconChatCircle className="mt-1 size-4 shrink-0" aria-hidden />
              <div className="min-w-0 flex-1 basis-64">
                <p className="text-pretty">{t.common.quote(g.text)}</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  <span className="font-display font-bold text-foreground tabular">{q.count(g.count)}</span>
                  {" · "}
                  {Object.entries(g.channels)
                    .map(([c, n]) => `${q.channels[c] ?? c} ${n}`)
                    .join(", ")}
                  {" · "}
                  {Object.entries(g.regions)
                    .map(([r, n]) => `${r} ${n}`)
                    .join(", ")}
                </p>
                <p className="text-sm text-muted-foreground">
                  {g.waiting > 0 && <span className="font-medium text-foreground">{q.waiting(g.waiting)} · </span>}
                  {q.latest(day.format(new Date(g.last_at)))}
                </p>
              </div>
              {g.item_id && (
                <Link href={`/w/${ws}/claims/${g.item_id}`} className="inline-flex items-center gap-1.5 self-center text-sm font-bold underline underline-offset-4">
                  {q.open(g.item_ref)} <IconArrowRight className="size-4" aria-hidden />
                </Link>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
