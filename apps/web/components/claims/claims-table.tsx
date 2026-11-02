"use client";

import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { formatTime } from "@/components/claims/day-grid";
import { type ClaimView, StatusLabel, VerdictBadge } from "@/components/claims/verdict";
import { t } from "@/lib/i18n/fr";
import { cn } from "@/lib/utils";

type SortKey = "ref" | "seen" | "sources";
type Sort = { key: SortKey; dir: "asc" | "desc" };

const dateFmt = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short" });

function seenLabel(d: Date | null, now: Date) {
  if (!d) return "—";
  return d.toDateString() === now.toDateString() ? formatTime(d) : `${dateFmt.format(d)}, ${formatTime(d)}`;
}

function value(c: ClaimView, key: SortKey): number | string {
  if (key === "ref") return c.ref;
  if (key === "sources") return c.sources;
  return c.firstSeen?.getTime() ?? 0;
}

function SortHeader({
  label,
  k,
  sort,
  onSort,
  className,
}: {
  label: string;
  k: SortKey;
  sort: Sort;
  onSort: (k: SortKey) => void;
  className?: string;
}) {
  const active = sort.key === k;
  const Icon = !active ? ArrowUpDown : sort.dir === "asc" ? ArrowUp : ArrowDown;
  return (
    <th
      scope="col"
      aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}
      className={className}
    >
      <button
        type="button"
        onClick={() => onSort(k)}
        className="-mx-1 inline-flex items-center gap-1 rounded-sm px-1 py-0.5 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
      >
        {label}
        <Icon className={cn("size-3.5", !active && "opacity-50")} aria-hidden />
      </button>
    </th>
  );
}

type Props = {
  claims: ClaimView[];
  now: Date;
  focusedId: string | null;
  selectedId: string | null;
  onFocusChange: (id: string | null) => void;
};

export function ClaimsTable({ claims, now, focusedId, selectedId, onFocusChange }: Props) {
  const [sort, setSort] = useState<Sort>({ key: "seen", dir: "desc" });
  const rows = useMemo(() => {
    const sign = sort.dir === "asc" ? 1 : -1;
    return [...claims].sort((a, b) => {
      const va = value(a, sort.key);
      const vb = value(b, sort.key);
      return va < vb ? -sign : va > vb ? sign : 0;
    });
  }, [claims, sort]);

  const onSort = (key: SortKey) =>
    setSort((s) => ({ key, dir: s.key === key && s.dir === "desc" ? "asc" : "desc" }));

  const rowState = (id: string) =>
    cn(
      "scroll-mt-28 transition-colors duration-150",
      selectedId === id && "bg-signal/15",
      focusedId === id && selectedId !== id && "bg-accent",
    );

  return (
    <>
      {/* Desktop: the programme listing under the grid */}
      <div className="hidden overflow-hidden rounded-lg border border-border bg-card md:block">
        <table className="w-full text-left text-[0.9375rem]">
          <thead className="border-b border-border text-sm text-muted-foreground">
            <tr className="[&>th]:px-4 [&>th]:py-2.5 [&>th]:font-medium">
              <SortHeader label={t.claims.columns.ref} k="ref" sort={sort} onSort={onSort} className="w-28" />
              <th scope="col">{t.claims.columns.claim}</th>
              <th scope="col" className="w-32">
                {t.claims.columns.status}
              </th>
              <th scope="col" className="w-48">
                {t.claims.columns.verdict}
              </th>
              <SortHeader label={t.claims.columns.sources} k="sources" sort={sort} onSort={onSort} className="w-24" />
              <SortHeader label={t.claims.columns.seenAt} k="seen" sort={sort} onSort={onSort} className="w-36" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map((c) => (
              <tr
                key={c.item.id}
                id={`claim-${c.item.id}`}
                onMouseEnter={() => onFocusChange(c.item.id)}
                onMouseLeave={() => onFocusChange(null)}
                className={cn(rowState(c.item.id), "[&>td]:px-4 [&>td]:py-2.5 [&>td]:align-top")}
              >
                <td className="font-display text-base font-semibold tracking-wide whitespace-nowrap tabular">{c.ref}</td>
                <td>
                  <p className="max-w-[44rem] truncate font-medium" title={c.item.title}>
                    {c.item.title}
                  </p>
                  {(c.origin || c.item.tags.length > 0) && (
                    <p className="mt-0.5 text-sm text-muted-foreground">
                      {[c.origin && (t.origins[c.origin as keyof typeof t.origins] ?? c.origin), ...c.item.tags]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                  )}
                </td>
                <td>
                  <StatusLabel status={c.status} />
                </td>
                <td>
                  <VerdictBadge claim={c} />
                </td>
                <td className="text-sm tabular">{t.claims.sources(c.sources)}</td>
                <td className="font-display text-base font-medium whitespace-nowrap tabular">
                  <time dateTime={c.firstSeen?.toISOString()}>{seenLabel(c.firstSeen, now)}</time>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Phone: one stacked row per claim */}
      <ul className="divide-y divide-border border-y border-border bg-card md:hidden">
        {rows.map((c) => (
          <li key={c.item.id} id={`claim-m-${c.item.id}`} className={cn(rowState(c.item.id), "px-4 py-3.5")}>
            <div className="flex items-baseline justify-between gap-3 text-sm text-muted-foreground">
              <span className="font-display text-base font-semibold tracking-wide text-foreground tabular">{c.ref}</span>
              <time dateTime={c.firstSeen?.toISOString()} className="font-display text-base font-medium text-foreground tabular">
                {seenLabel(c.firstSeen, now)}
              </time>
            </div>
            <p className="mt-1 font-medium text-pretty">{c.item.title}</p>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2">
              <StatusLabel status={c.status} />
              <VerdictBadge claim={c} />
              <span className="text-sm text-muted-foreground tabular">{t.claims.sources(c.sources)}</span>
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}
