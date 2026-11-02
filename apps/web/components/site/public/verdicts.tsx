"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { IconArrowRight } from "@/lib/icons";
import { VerdictChip } from "@/components/claims/verdict";
import { t } from "@/lib/i18n/fr";
import { type PublicVerdict, publicApi } from "@/lib/public-api";
import { tidy } from "@/lib/typo";

const p = t.site.pub.file;
const a = t.site.pub.archive;
export const day = (iso: string) => new Date(iso).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });

/** One published verdict on a line: the claim and why, the verdict word, who checked it and when.
 *  `compact` keeps only the verdict and the claim, for a short list under the check field. */
export function VerdictRow({ v, index = 0, compact = false }: { v: PublicVerdict; index?: number; compact?: boolean }) {
  if (compact)
    return (
      <li className="arrive" style={{ "--i": index } as React.CSSProperties}>
        <Link
          href={`/verifies/${v.id}`}
          className="group flex items-center gap-3 border-b border-border py-2.5 outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <VerdictChip verdict={v.verdict} className="w-[8.5rem] shrink-0" />
          <span className="min-w-0 flex-1 truncate font-bold group-hover:underline">{tidy(v.title)}</span>
          <IconArrowRight className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-1" aria-hidden />
        </Link>
      </li>
    );
  return (
    <li className="arrive" style={{ "--i": index } as React.CSSProperties}>
      <Link
        href={`/verifies/${v.id}`}
        className="group grid gap-x-8 gap-y-2 border-b border-border py-5 outline-none focus-visible:ring-2 focus-visible:ring-ring md:grid-cols-[minmax(0,1fr)_auto]"
      >
        <span className="min-w-0">
          <span className="block font-display text-lg leading-snug font-bold text-pretty group-hover:underline md:text-xl">«&nbsp;{tidy(v.title)}&nbsp;»</span>
          {v.reason && <span className="mt-1.5 block max-w-[70ch] text-pretty text-muted-foreground">{v.reason}</span>}
          <span className="mt-2 block text-sm text-muted-foreground">
            {p.by(v.newsroom.name)} · {day(v.published_at)}
            {v.ref && <span className="tabular"> · {v.ref}</span>}
          </span>
        </span>
        <span className="flex items-center gap-3 md:self-center">
          <VerdictChip verdict={v.verdict} className="text-base" />
          <IconArrowRight className="size-5 text-muted-foreground transition-transform group-hover:translate-x-1" aria-hidden />
        </span>
      </Link>
    </li>
  );
}

/** The latest verdicts the newsrooms published, `limit` of them, with an optional filter and more. */
export function VerdictList({ limit: first = 3, filter = false, compact = false }: { limit?: number; filter?: boolean; compact?: boolean }) {
  const [q, setQ] = useState("");
  const [limit, setLimit] = useState(first);
  const [page, setPage] = useState<{ items: PublicVerdict[]; total: number } | null>(null);

  useEffect(() => {
    const id = setTimeout(() => {
      publicApi<{ items: PublicVerdict[]; total: number }>(`/verdicts?limit=${limit}${q ? `&q=${encodeURIComponent(q)}` : ""}`)
        .then(setPage)
        .catch(() => setPage({ items: [], total: 0 }));
    }, 250);
    return () => clearTimeout(id);
  }, [q, limit]);

  return (
    <div>
      {filter && (
        <div className="flex flex-wrap items-end justify-between gap-4 border-b border-foreground pb-4">
          {page && <p className="text-muted-foreground">{a.count(page.total)}</p>}
          <label className="block w-full max-w-sm">
            <span className="text-sm font-bold">{a.filter}</span>
            <input
              type="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className="mt-1 h-11 w-full rounded-md border border-input bg-card px-3 outline-none focus-visible:border-foreground focus-visible:ring-2 focus-visible:ring-foreground/15"
            />
          </label>
        </div>
      )}
      {page && !page.items.length && <p className="mt-6 text-lg">{a.empty}</p>}
      <ul className={filter ? undefined : "border-t border-foreground"}>
        {page?.items.map((v, i) => (
          <VerdictRow key={v.id} v={v} index={i} compact={compact} />
        ))}
      </ul>
      {filter && page && page.total > page.items.length && (
        <button type="button" onClick={() => setLimit((l) => l + 9)} className="mt-6 h-11 rounded-md border border-foreground px-4 font-bold hover:bg-accent">
          {a.more}
        </button>
      )}
    </div>
  );
}
