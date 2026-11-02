"use client";

import type { Item, ItemPage, Status, Verdict } from "@fanilo/shared";
import { STATUSES, VERDICTS } from "@fanilo/shared";
import { useCallback, useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { ListChecks, Search, WifiOff } from "lucide-react";
import { toast } from "sonner";
import { ClaimsTable } from "@/components/claims/claims-table";
import { DayGrid } from "@/components/claims/day-grid";
import { NewClaimSheet } from "@/components/claims/new-claim-sheet";
import { type ClaimView, toClaim, VERDICT_META } from "@/components/claims/verdict";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkspaceSocket } from "@/hooks/use-workspace-socket";
import { fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/fr";

const ALL = "all";
const dayFmt = new Intl.DateTimeFormat("fr-FR", { weekday: "long", day: "numeric", month: "long" });

/** Ticks every 30 s so blocks keep growing toward "maintenant". */
function useNow() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(id);
  }, []);
  return now;
}

function nextRef(claims: ClaimView[]) {
  const max = claims.reduce((n, c) => Math.max(n, Number(/^FAN-(\d+)$/.exec(c.ref)?.[1] ?? 0)), 136);
  return `FAN-${String(max + 1).padStart(4, "0")}`;
}

function Empty({ title, lead, action }: { title: string; lead: string; action?: React.ReactNode }) {
  return (
    <div className="mx-4 rounded-lg border border-dashed border-border px-6 py-14 text-center lg:mx-0">
      <ListChecks className="mx-auto size-6 text-muted-foreground" aria-hidden />
      <h2 className="mt-3 font-semibold">{title}</h2>
      <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">{lead}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function ClaimsView({ ws }: { ws: string }) {
  const key = `/workspaces/${ws}/items?limit=200`;
  const { data, error, isLoading, mutate } = useSWR<ItemPage>(key, fetcher);
  const now = useNow();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<string>(ALL);
  const [verdict, setVerdict] = useState<string>(ALL);
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const all = useMemo(() => (data?.items ?? []).map(toClaim), [data]);
  const claims = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return all.filter(
      (c) =>
        (status === ALL || c.status === status) &&
        (verdict === ALL || (c.verdict ?? c.suggested) === verdict) &&
        (!needle || `${c.ref} ${c.item.title} ${c.item.tags.join(" ")}`.toLowerCase().includes(needle)),
    );
  }, [all, q, status, verdict]);
  const hasDemo = all.some((c) => (c.item.data as { demo?: boolean }).demo);

  const upsert = useCallback(
    (item: Item) =>
      mutate(
        (page) => {
          if (!page) return page;
          const rest = page.items.filter((i) => i.id !== item.id);
          const isNew = rest.length === page.items.length;
          return { items: [item, ...rest], total: page.total + (isNew ? 1 : 0) };
        },
        { revalidate: false },
      ),
    [mutate],
  );

  const { online } = useWorkspaceSocket(ws, {
    "item.created": (item: Item) => {
      const known = data?.items.some((i) => i.id === item.id);
      upsert(item);
      if (!known) toast(t.claims.liveNew(toClaim(item).ref), { description: item.title });
    },
    "item.updated": (item: Item) => upsert(item),
    "item.deleted": ({ id }: { id: string }) =>
      mutate((page) => page && { items: page.items.filter((i) => i.id !== id), total: page.total - 1 }, {
        revalidate: false,
      }),
    "demo.reset": () => mutate(),
    reconnected: () => mutate(),
  });

  const select = useCallback((id: string) => {
    setSelectedId(id);
    const row = document.getElementById(`claim-${id}`) ?? document.getElementById(`claim-m-${id}`);
    row?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, []);

  const clear = () => {
    setQ("");
    setStatus(ALL);
    setVerdict(ALL);
  };

  return (
    <div className="mx-auto max-w-[90rem] pb-10 lg:px-8">
      <header className="flex flex-wrap items-end justify-between gap-4 px-4 pt-6 pb-5 lg:px-0 lg:pt-8">
        <div>
          <h1 className="text-[1.75rem] leading-tight font-semibold tracking-tight">{t.claims.title}</h1>
          <p className="mt-1 text-muted-foreground first-letter:uppercase">
            {dayFmt.format(now)}
            {data && <span className="tabular"> · {data.total} au total</span>}
            {hasDemo && (
              <span className="ml-2 inline-block rounded-sm border border-border px-1.5 py-px align-[0.1em] text-xs whitespace-nowrap">
                {t.common.demoData}
              </span>
            )}
          </p>
        </div>
        <NewClaimSheet ws={ws} nextRef={nextRef(all)} onCreated={upsert} />
      </header>

      {!online && (
        <p
          role="status"
          className="mx-4 mb-4 flex items-center gap-2 rounded-md bg-verdict-misleading-soft px-3 py-2 text-sm text-verdict-misleading-ink lg:mx-0"
        >
          <WifiOff className="size-4" aria-hidden />
          {t.claims.offline}
        </p>
      )}

      <div className="flex flex-wrap gap-2 px-4 pb-4 lg:px-0">
        <div className="relative min-w-0 flex-1 basis-full sm:basis-64">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t.claims.search}
            aria-label={t.claims.search}
            className="h-10 bg-card pl-9"
          />
        </div>
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger aria-label={t.claims.columns.status} className="h-10 flex-1 bg-card sm:w-44 sm:flex-none">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t.claims.allStatuses}</SelectItem>
            {STATUSES.map((s: Status) => (
              <SelectItem key={s} value={s}>
                {t.status[s]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={verdict} onValueChange={setVerdict}>
          <SelectTrigger aria-label={t.claims.columns.verdict} className="h-10 flex-1 bg-card sm:w-44 sm:flex-none">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t.claims.allVerdicts}</SelectItem>
            {VERDICTS.map((v: Verdict) => {
              const Icon = VERDICT_META[v].icon;
              return (
                <SelectItem key={v} value={v}>
                  <Icon className={`size-4 ${VERDICT_META[v].ink}`} aria-hidden />
                  {VERDICT_META[v].label}
                </SelectItem>
              );
            })}
          </SelectContent>
        </Select>
      </div>

      {error ? (
        <Empty
          title={t.claims.errorTitle}
          lead={error.message}
          action={
            <Button variant="outline" onClick={() => mutate()}>
              {t.claims.retry}
            </Button>
          }
        />
      ) : isLoading || !data ? (
        <div className="space-y-4 px-4 lg:px-0" aria-busy aria-label={t.common.loading}>
          <Skeleton className="h-60 w-full" />
          <Skeleton className="h-80 w-full" />
        </div>
      ) : all.length === 0 ? (
        <Empty title={t.claims.emptyTitle} lead={t.claims.emptyLead} />
      ) : claims.length === 0 ? (
        <Empty
          title={t.claims.noMatchTitle}
          lead={t.claims.noMatchLead}
          action={
            <Button variant="outline" onClick={clear}>
              {t.claims.clearFilters}
            </Button>
          }
        />
      ) : (
        <div className="space-y-5">
          <DayGrid
            claims={claims}
            now={now}
            focusedId={focusedId}
            onFocusChange={setFocusedId}
            onSelect={select}
          />
          <ClaimsTable
            claims={claims}
            now={now}
            focusedId={focusedId}
            selectedId={selectedId}
            onFocusChange={setFocusedId}
          />
        </div>
      )}
    </div>
  );
}
