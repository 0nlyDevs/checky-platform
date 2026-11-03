"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { VERDICT_META } from "@/components/claims/verdict";
import { ORIGIN_ICON, ThemedSelect } from "@/components/site/public/kit";
import { useDay, useT } from "@/lib/i18n";
import { IconArrowUpRight, IconCircleNotch, IconMagnifyingGlass, IconNewspaper } from "@/lib/icons";
import { type Newsroom, type PublicVerdict, publicApi, visitorCountry } from "@/lib/public-api";
import { tidy } from "@/lib/typo";
import { cn } from "@/lib/utils";

/**
 * One published verdict as a card. Public verdicts carry no picture, so every card is built the same
 * way: the verdict on its own wash (icon and word, never colour alone) with the reference, the claim
 * as it circulated, why, then where it was seen (the platform's logo), who checked it and when.
 */
export function VerdictCard({ v, index = 0 }: { v: PublicVerdict; index?: number }) {
  const t = useT();
  const p = t.site.pub.file;
  const day = useDay();
  const m = VERDICT_META[v.verdict];
  const Mark = m.icon;
  const Origin = v.origin ? ORIGIN_ICON[v.origin] : null;
  const where = v.origin ? ((t.origins as Record<string, string>)[v.origin] ?? null) : null;
  return (
    <li className="arrive flex" style={{ "--i": index } as React.CSSProperties}>
      <Link href={`/verifies/${v.id}`} className="vcard group">
        <span className={cn("vcard-head", m.soft, m.ink)}>
          <span className="vcard-word">
            <Mark className="size-6 shrink-0" aria-hidden />
            {t.verdict[v.verdict]}
          </span>
          {v.ref && <span className="text-sm font-medium text-foreground tabular">{v.ref}</span>}
        </span>
        <span className="vcard-body">
          <span className="vcard-claim">«&nbsp;{tidy(v.title)}&nbsp;»</span>
          {v.reason && <span className="vcard-reason">{v.reason}</span>}
        </span>
        <span className="vcard-foot">
          {Origin && where && (
            <span className="vcard-origin" title={t.look.verifies.seenOn(where)}>
              <Origin className="size-[18px]" aria-hidden />
              <span className="sr-only">{t.look.verifies.seenOn(where)}</span>
            </span>
          )}
          <span className="min-w-0 flex-1 text-sm text-muted-foreground">
            <span className="block truncate font-medium text-foreground">{v.newsroom.name}</span>
            <time dateTime={v.published_at}>{day(v.published_at)}</time>
          </span>
          <span className="vcard-go" aria-hidden>
            <IconArrowUpRight className="size-5" />
          </span>
          <span className="sr-only">{p.open}</span>
        </span>
      </Link>
    </li>
  );
}

/** The latest verdicts the newsrooms published, as cards, with a word filter, a newsroom and more. */
export function VerdictList({ limit: first = 9, title }: { limit?: number; title?: React.ReactNode }) {
  const t = useT();
  const a = t.site.pub.archive;
  const l = t.look.verifies;
  const [q, setQ] = useState("");
  const [room, setRoom] = useState("");
  const [rooms, setRooms] = useState<Newsroom[]>([]);
  const [limit, setLimit] = useState(first);
  const [page, setPage] = useState<{ items: PublicVerdict[]; total: number } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    publicApi<Newsroom[]>("/newsrooms")
      .then(setRooms)
      .catch(() => setRooms([]));
  }, []);

  useEffect(() => {
    const id = setTimeout(() => {
      setLoading(true);
      const qs = new URLSearchParams({ limit: String(limit) });
      if (q) qs.set("q", q);
      if (room) qs.set("newsroom", room);
      if (visitorCountry()) qs.set("country", visitorCountry()!);
      publicApi<{ items: PublicVerdict[]; total: number }>(`/verdicts?${qs}`)
        .then(setPage)
        .catch(() => setPage({ items: [], total: 0 }))
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(id);
  }, [q, room, limit]);

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-5">
        <div>
          {title}
          <p className="mt-3 text-muted-foreground" aria-live="polite">
            {page ? a.count(page.total) : " "}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2.5 lg:flex-nowrap">
          {rooms.length > 1 && (
            <ThemedSelect
              value={room}
              onValueChange={setRoom}
              label={l.newsroom}
              icon={IconNewspaper}
              options={[{ value: "", label: l.allNewsrooms }, ...rooms.map((n) => ({ value: n.slug, label: n.name }))]}
            />
          )}
          <label className="pub-search">
            <span className="sr-only">{a.filter}</span>
            <IconMagnifyingGlass className="size-5 shrink-0 text-muted-foreground" aria-hidden />
            <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={a.filter} />
          </label>
        </div>
      </div>
      {page && !page.items.length && !loading && <p className="mt-8 text-lg">{a.empty}</p>}
      <ul className="vcard-grid mt-6">
        {page?.items.map((v, i) => (
          <VerdictCard key={v.id} v={v} index={i} />
        ))}
      </ul>
      {page && page.total > page.items.length && (
        <div className="mt-8 flex justify-center">
          <button type="button" onClick={() => setLimit((n) => n + 9)} className="pub-ghost-btn" disabled={loading}>
            {loading && <IconCircleNotch className="size-4 animate-spin" aria-hidden />}
            {a.more}
          </button>
        </div>
      )}
    </div>
  );
}
