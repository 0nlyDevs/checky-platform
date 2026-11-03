"use client";

import type { Item, ItemPage, Status } from "@checky/shared";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { IconArrowRight, IconColumns, IconFolderOpen, IconMagnifyingGlass, IconRows, IconWifiSlash } from "@/lib/icons";
import { toast } from "sonner";
import { undoable } from "@/lib/undo";
import { Board } from "@/components/claims/board";
import { DossierList } from "@/components/claims/dossier-list";
import { NewClaimSheet } from "@/components/claims/new-claim-sheet";
import { type ClaimView, toClaim } from "@/components/claims/verdict";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkspaceSocket } from "@/hooks/use-workspace-socket";
import { useWorkspace } from "@/hooks/use-workspace";
import { api, ApiError, fetcher } from "@/lib/api";
import { dateFormat, t } from "@/lib/i18n/live";
import { cn } from "@/lib/utils";

const ALL = "all";
const dayFmt = dateFormat({ weekday: "long", day: "numeric", month: "long" });

// The tabs follow the numbered line: still being worked on, an AI suggestion waiting, a confirmed verdict.
const TABS = ["all", "todo", "confirm", "done"] as const;
type Tab = (typeof TABS)[number];
const inTab = (c: ClaimView, tab: Tab) =>
  tab === "all" || (tab === "done" ? !!c.verdict : tab === "confirm" ? !c.verdict && !!c.suggested : !c.verdict && !c.suggested);

/** Ticks every 30 s so "il y a…" keeps up. */
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
    <div className="mx-4 rounded-md border border-dashed border-border px-6 py-14 text-center lg:mx-0">
      <IconFolderOpen className="mx-auto size-6 text-muted-foreground" aria-hidden />
      <h2 className="mt-3 font-display text-lg font-bold">{title}</h2>
      <p className="mx-auto mt-1 max-w-sm text-muted-foreground">{lead}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function ClaimsView() {
  const { ws } = useParams<{ ws: string }>();
  // Press articles read by the Veille job are items too (type "press"); the dossiers list shows claims.
  const key = `/workspaces/${ws}/items?limit=200&type=claim`;
  const { data, error, isLoading, mutate } = useSWR<ItemPage>(key, fetcher);
  const now = useNow();
  const [q, setQ] = useState("");
  const [assignee, setAssignee] = useState<string>(ALL);
  const { me, members, names } = useWorkspace(ws);
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const view = params.get("vue") === "tableau" ? "board" : "list";
  const tab: Tab = (TABS as readonly string[]).includes(params.get("onglet") ?? "") ? (params.get("onglet") as Tab) : "all";
  const go = (next: { vue?: "board" | "list"; onglet?: Tab }) => {
    const qs = new URLSearchParams();
    if ((next.vue ?? view) === "board") qs.set("vue", "tableau");
    const o = next.onglet ?? tab;
    if (o !== "all") qs.set("onglet", o);
    router.replace(qs.size ? `${pathname}?${qs}` : pathname, { scroll: false });
  };

  const all = useMemo(
    () =>
      (data?.items ?? [])
        .map(toClaim)
        .sort((a, b) => (b.firstSeen ?? new Date(b.item.created_at)).getTime() - (a.firstSeen ?? new Date(a.item.created_at)).getTime()),
    [data],
  );
  const matching = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return all.filter(
      (c) =>
        (assignee === ALL || (assignee === "me" && c.assigneeId === me?.id) || (assignee === "none" && !c.assigneeId) || c.assigneeId === assignee) &&
        (!needle || `${c.ref} ${c.item.title} ${c.item.tags.join(" ")}`.toLowerCase().includes(needle)),
    );
  }, [all, q, assignee, me?.id]);
  // The board's columns are the statuses, so the tabs only sort the list.
  const claims = useMemo(() => (view === "board" ? matching : matching.filter((c) => inTab(c, tab))), [matching, tab, view]);
  const counts = useMemo(() => Object.fromEntries(TABS.map((k) => [k, matching.filter((c) => inTab(c, k)).length])) as Record<Tab, number>, [matching]);
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
      mutate((page) => page && { items: page.items.filter((i) => i.id !== id), total: page.total - 1 }, { revalidate: false }),
    "demo.reset": () => mutate(),
    reconnected: () => mutate(),
  });

  const canMove = useCallback(
    () => Boolean(me),
    [me],
  );

  /** Optimistic: the card lands in its new column now; the server confirms or it goes back. */
  const move = useCallback(
    async (c: ClaimView, to: Status) => {
      const previous = c.item;
      upsert({ ...previous, status: to });
      try {
        upsert(await api<Item>(`/workspaces/${ws}/items/${previous.id}`, { method: "PATCH", body: JSON.stringify({ status: to }) }));
        undoable(t.claims.board.moved(c.ref, t.status[to]), async () =>
          upsert(await api<Item>(`/workspaces/${ws}/items/${previous.id}`, { method: "PATCH", body: JSON.stringify({ status: previous.status }) })),
        );
      } catch (e) {
        upsert(previous);
        toast.error(e instanceof ApiError && e.status === 403 ? t.claims.board.cannotMove : t.detail.saveFailed);
      }
    },
    [upsert, ws],
  );

  const clear = () => {
    setQ("");
    setAssignee(ALL);
    go({ onglet: "all" });
  };

  return (
    <div className="@container mx-auto max-w-[90rem] pb-10 lg:px-8">
      <header className="flex items-start justify-between gap-4 px-4 pt-6 pb-5 sm:items-end lg:px-0 lg:pt-8">
        <div>
          <h1 className="page-title">{t.claims.title}</h1>
          <p className="mt-1.5 text-muted-foreground first-letter:uppercase">
            {dayFmt.format(now)}
            {data && <span className="tabular"> · {t.claims.total(data.total)}</span>}
            {hasDemo && (
              <span className="ml-2 inline-block rounded-sm border border-border px-1.5 py-px align-[0.1em] text-xs whitespace-nowrap">{t.common.demoData}</span>
            )}
          </p>
        </div>
        <NewClaimSheet ws={ws} nextRef={nextRef(all)} onCreated={upsert} />
      </header>

      {!online && (
        <p role="status" className="mx-4 mb-4 flex items-center gap-2 rounded-md bg-verdict-misleading-soft px-3 py-2 text-sm text-verdict-misleading-ink lg:mx-0">
          <IconWifiSlash className="size-4" aria-hidden />
          {t.claims.offline}
        </p>
      )}

      {view === "list" && tab !== "confirm" && counts.confirm > 0 && !claims.some((c) => c.suggested && !c.verdict) && (
        <div className="mx-4 mb-5 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-md border-2 border-dashed border-foreground bg-card px-4 py-3 lg:mx-0">
          <p className="font-bold">{t.claims.waiting(counts.confirm)}</p>
          <button type="button" onClick={() => go({ onglet: "confirm" })} className="inline-flex items-center gap-1.5 font-bold underline underline-offset-4">
            {t.claims.waitingAction} <IconArrowRight className="size-4" aria-hidden />
          </button>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 px-4 pb-4 lg:px-0">
        {view === "list" && (
          <div role="tablist" aria-label={t.claims.tabs.label} className="-mx-4 flex basis-[calc(100%+2rem)] gap-1 overflow-x-auto px-4 pb-1 [scrollbar-width:none] lg:mx-0 lg:px-0 @3xl:basis-auto">
            {TABS.map((k) => (
              <button
                key={k}
                type="button"
                role="tab"
                aria-selected={tab === k}
                onClick={() => go({ onglet: k })}
                className={cn(
                  "inline-flex h-11 shrink-0 items-center gap-2 rounded-md px-3 outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  tab === k ? "bg-foreground font-bold text-background" : "hover:bg-card",
                )}
              >
                {t.claims.tabs[k]}
                <span
                  className={cn(
                    "rounded-sm px-1.5 text-sm font-bold tabular",
                    k === "confirm" && counts.confirm > 0 ? "bg-action text-action-foreground" : tab === k ? "bg-background/15" : "bg-muted",
                  )}
                >
                  {counts[k]}
                </span>
              </button>
            ))}
          </div>
        )}
        <div className="relative min-w-0 flex-1 basis-56">
          <IconMagnifyingGlass className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t.claims.search} aria-label={t.claims.search} className="h-10 bg-card pl-9" />
        </div>
        <Select value={assignee} onValueChange={setAssignee}>
          <SelectTrigger size="sm" aria-label={t.detail.assignee} className="w-auto min-w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t.claims.allAssignees}</SelectItem>
            <SelectItem value="me">{t.claims.mine}</SelectItem>
            <SelectItem value="none">{t.claims.unassigned}</SelectItem>
            {members
              ?.filter((m) => m.user_id !== me?.id)
              .map((m) => (
                <SelectItem key={m.user_id} value={m.user_id}>
                  {m.name ?? m.email ?? m.user_id}
                </SelectItem>
              ))}
          </SelectContent>
        </Select>
        <div role="radiogroup" aria-label={t.claims.views.label} className="flex h-10 shrink-0 rounded-md border border-input bg-card p-0.5">
          {(
            [
              ["list", t.claims.views.grid, IconRows],
              ["board", t.claims.views.board, IconColumns],
            ] as const
          ).map(([v, label, Icon]) => (
            <button
              key={v}
              type="button"
              role="radio"
              aria-checked={view === v}
              onClick={() => go({ vue: v })}
              className={cn(
                "flex items-center gap-1.5 rounded-[3px] px-3 text-sm font-bold outline-none transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-ring",
                view === v ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground",
              )}
            >
              <Icon className="size-4" aria-hidden />
              <span className="sr-only sm:not-sr-only">{label}</span>
            </button>
          ))}
        </div>
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
        <div className="space-y-3 px-4 lg:px-0" aria-busy aria-label={t.common.loading}>
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
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
      ) : view === "board" ? (
        <Board ws={ws} claims={claims} now={now} names={names} canMove={canMove} onMove={move} />
      ) : (
        <DossierList ws={ws} claims={claims} now={now} names={names} />
      )}
    </div>
  );
}
