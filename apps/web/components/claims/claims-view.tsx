"use client";

import type { Item, ItemPage, Status } from "@checky/shared";
import {
  useParams,
  usePathname,
  useRouter,
  useSearchParams,
} from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";
import useSWRInfinite from "swr/infinite";
import {
  IconArrowRight,
  IconColumns,
  IconFolderOpen,
  IconMagnifyingGlass,
  IconRows,
  IconWifiSlash,
} from "@/lib/icons";
import { toast } from "sonner";
import { undoable } from "@/lib/undo";
import { Board } from "@/components/claims/board";
import { DossierList } from "@/components/claims/dossier-list";
import { NewClaimSheet } from "@/components/claims/new-claim-sheet";
import { type ClaimView, toClaim } from "@/components/claims/verdict";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkspaceSocket } from "@/hooks/use-workspace-socket";
import { useWorkspace } from "@/hooks/use-workspace";
import { api, ApiError, fetcher } from "@/lib/api";
import { dateFormat, t } from "@/lib/i18n/live";
import { LoadMore } from "@/components/ui/load-more";
import { PillTabs } from "@/components/ui/pill-tabs";

const ALL = "all";
const dayFmt = dateFormat({ weekday: "long", day: "numeric", month: "long" });

// The tabs follow the numbered line: still being worked on, an AI suggestion waiting, a confirmed verdict.
const TABS = ["all", "todo", "confirm", "done"] as const;
type Tab = (typeof TABS)[number];

/** Ticks every 30 s so "il y a…" keeps up. */
function useNow() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(id);
  }, []);
  return now;
}

// One page of the list. Waiting dossiers come oldest first (the rumour circulating longest without
// an answer leads); checked ones and « Tous » newest first.
const PAGE = 30;
const ORDER: Record<Tab, "newest" | "oldest"> = {
  all: "newest",
  todo: "oldest",
  confirm: "oldest",
  done: "newest",
};

/** The search as typed, settled after a short pause so each keystroke does not query the server. */
function useSettled(value: string, ms = 250) {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setSettled(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return settled;
}

/**
 * When the rumour was first seen, as the server sorts it (app/modules/items.py `SEEN`): a literal
 * date in `first_seen_at`, else the item's creation.
 */
function seenOf(item: Item): number {
  const raw = item.data.first_seen_at;
  const at =
    typeof raw === "string" && /^\d{4}-\d{2}-\d{2}/.test(raw)
      ? Date.parse(raw)
      : Number.NaN;
  return Number.isNaN(at) ? Date.parse(item.created_at) : at;
}

/** Above zero when `a` comes after `b` in time (ties broken by id, like the server's cursor). */
function rank(a: Item, b: Item): number {
  return seenOf(a) - seenOf(b) || (a.id > b.id ? 1 : a.id < b.id ? -1 : 0);
}

function Empty({
  title,
  lead,
  action,
}: {
  title: string;
  lead: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="mx-4 rounded-md border border-dashed border-border px-6 py-14 text-center lg:mx-0">
      <IconFolderOpen
        className="mx-auto size-6 text-muted-foreground"
        aria-hidden
      />
      <h2 className="mt-3 font-display text-lg font-bold">{title}</h2>
      <p className="mx-auto mt-1 max-w-sm text-muted-foreground">{lead}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function ClaimsView() {
  const { ws } = useParams<{ ws: string }>();
  const now = useNow();
  const [q, setQ] = useState("");
  const search = useSettled(q.trim());
  const [assignee, setAssignee] = useState<string>(ALL);
  const { me, members, names } = useWorkspace(ws);
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const view = params.get("vue") === "tableau" ? "board" : "list";
  const tab: Tab = (TABS as readonly string[]).includes(
    params.get("onglet") ?? "",
  )
    ? (params.get("onglet") as Tab)
    : "all";
  const go = (next: { vue?: "board" | "list"; onglet?: Tab }) => {
    const qs = new URLSearchParams();
    if ((next.vue ?? view) === "board") qs.set("vue", "tableau");
    const o = next.onglet ?? tab;
    if (o !== "all") qs.set("onglet", o);
    router.replace(qs.size ? `${pathname}?${qs}` : pathname, { scroll: false });
  };

  // The board's columns are the statuses: it shows every dossier at once (up to 200), as before.
  // Press articles read by the Veille job are items too (type "press"); the dossiers list shows claims.
  const boardKey =
    view === "board" ? `/workspaces/${ws}/items?limit=200&type=claim` : null;
  const board = useSWR<ItemPage>(boardKey, fetcher);
  const { mutate: mutateBoard } = board;

  const filters = useMemo(() => {
    const qs = new URLSearchParams();
    if (search) qs.set("q", search);
    if (assignee !== ALL) qs.set("assignee", assignee);
    return qs.toString();
  }, [search, assignee]);
  const base = `/workspaces/${ws}/items?type=claim`;
  // The list: pages of 30 from the server, in the tab's order. While another tab, search or
  // assignee loads, the previous rows stay on screen (keepPreviousData) under a thin moving line.
  const listQuery = `${base}&limit=${PAGE}&tab=${tab}&order=${ORDER[tab]}${filters ? `&${filters}` : ""}`;
  const pages = useSWRInfinite<ItemPage>(
    (index, previous: ItemPage | null) =>
      view !== "list"
        ? null
        : index === 0
          ? listQuery
          : previous?.next
            ? `${listQuery}&after=${encodeURIComponent(previous.next)}`
            : null,
    fetcher,
    { revalidateFirstPage: false, keepPreviousData: true },
  );
  const { mutate: mutatePages } = pages;
  // Every tab's count under the same search and assignee: one light request (a single row).
  const filtered = useSWR<ItemPage>(
    view === "list"
      ? `${base}&limit=1&tab=all&counts=true${filters ? `&${filters}` : ""}`
      : null,
    fetcher,
    {
      keepPreviousData: true,
    },
  );
  // The newsroom as a whole, whatever the filters: the header's total and the demo marker.
  const newsroom = useSWR<ItemPage>(
    `${base}&limit=1&tab=all&counts=true`,
    fetcher,
  );
  const { mutate: mutateFiltered } = filtered;
  const { mutate: mutateNewsroom } = newsroom;

  const last = pages.data?.[pages.data.length - 1];
  const loadingMore =
    pages.isValidating && pages.size > (pages.data?.length ?? 0);
  const refreshing =
    view === "list" &&
    Boolean(pages.data) &&
    (pages.isLoading || filtered.isLoading);

  const boardClaims = useMemo(() => {
    const needle = search.toLowerCase();
    return (board.data?.items ?? [])
      .map(toClaim)
      .filter(
        (c) =>
          (assignee === ALL ||
            (assignee === "me" && c.assigneeId === me?.id) ||
            (assignee === "none" && !c.assigneeId) ||
            c.assigneeId === assignee) &&
          (!needle ||
            `${c.ref} ${c.item.title} ${c.item.body} ${c.item.tags.join(" ")}`
              .toLowerCase()
              .includes(needle)),
      )
      .sort((x, y) => seenOf(y.item) - seenOf(x.item));
  }, [board.data, search, assignee, me?.id]);
  const listClaims = useMemo(
    () => (pages.data ?? []).flatMap((p) => p.items).map(toClaim),
    [pages.data],
  );
  const claims = view === "board" ? boardClaims : listClaims;
  const counts: Record<Tab, number> = {
    all: 0,
    todo: 0,
    confirm: 0,
    done: 0,
    ...(filtered.data?.counts ?? {}),
  };
  const total =
    view === "board" ? board.data?.total : newsroom.data?.counts?.all;
  const data = view === "board" ? board.data : pages.data?.[0];
  const error =
    view === "board"
      ? board.error
      : pages.error && !pages.data
        ? pages.error
        : undefined;
  const isLoading =
    view === "board"
      ? board.isLoading
      : !pages.data && (pages.isLoading || newsroom.isLoading);
  const nothingAtAll =
    view === "board"
      ? (board.data?.items.length ?? 0) === 0
      : newsroom.data?.counts?.all === 0;
  const hasDemo =
    view === "board"
      ? claims.some((c) => (c.item.data as { demo?: boolean }).demo)
      : (newsroom.data?.counts?.demo ?? 0) > 0;

  // Live events change counts in bursts (an analysis, a crew run): one recount per quiet moment.
  const recountTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const recount = useCallback(() => {
    clearTimeout(recountTimer.current);
    recountTimer.current = setTimeout(() => {
      void mutateFiltered();
      void mutateNewsroom();
    }, 400);
  }, [mutateFiltered, mutateNewsroom]);
  useEffect(() => () => clearTimeout(recountTimer.current), []);

  const reload = useCallback(() => {
    void mutatePages();
    void mutateBoard();
    void mutateFiltered();
    void mutateNewsroom();
  }, [mutatePages, mutateBoard, mutateFiltered, mutateNewsroom]);

  /** Does this dossier belong in the list on screen (tab, search, assignee), as the server reads it? */
  const fits = (item: Item) => {
    const c = toClaim(item);
    const inTab =
      tab === "all" ||
      (tab === "done"
        ? !!c.verdict
        : tab === "confirm"
          ? !c.verdict && !!c.suggested
          : !c.verdict && !c.suggested);
    const owner =
      typeof item.data.assignee_id === "string" ? item.data.assignee_id : null;
    const mine =
      assignee === ALL ||
      (assignee === "none"
        ? owner === null
        : owner === (assignee === "me" ? me?.id : assignee));
    const needle = search.toLowerCase();
    const found =
      !needle ||
      `${item.title} ${item.body} ${c.ref} ${item.tags.join(" ")}`
        .toLowerCase()
        .includes(needle);
    return item.type === "claim" && inTab && mine && found;
  };

  /**
   * Puts a dossier where the server would, without reloading every page: replaced in place, taken
   * out when it no longer fits the tab, or slotted at its rank. A rank past the last loaded row
   * while more pages remain is left to « Afficher les suivants » (the count already says it).
   */
  const placeInList = (item: Item) =>
    mutatePages(
      (current) => {
        if (!current) return current;
        const rows = current.map((p) =>
          p.items.filter((i) => i.id !== item.id),
        );
        if (!fits(item))
          return current.map((p, n) => ({ ...p, items: rows[n] }));
        const before = (x: Item) =>
          ORDER[tab] === "newest" ? rank(item, x) > 0 : rank(item, x) < 0;
        const hasMore = Boolean(current[current.length - 1]?.next);
        for (let n = 0; n < rows.length; n++) {
          const at = rows[n].findIndex(before);
          if (at !== -1) {
            rows[n] = [...rows[n].slice(0, at), item, ...rows[n].slice(at)];
            return current.map((p, k) => ({ ...p, items: rows[k] }));
          }
        }
        if (!hasMore) rows[rows.length - 1] = [...rows[rows.length - 1], item];
        return current.map((p, k) => ({ ...p, items: rows[k] }));
      },
      { revalidate: false },
    );

  const upsertBoard = useCallback(
    (item: Item) =>
      mutateBoard(
        (page) => {
          if (!page) return page;
          const rest = page.items.filter((i) => i.id !== item.id);
          const isNew = rest.length === page.items.length;
          return {
            ...page,
            items: [item, ...rest],
            total: page.total + (isNew ? 1 : 0),
          };
        },
        { revalidate: false },
      ),
    [mutateBoard],
  );

  const changed = (item: Item) => {
    void placeInList(item);
    void upsertBoard(item);
    recount();
  };

  const { online } = useWorkspaceSocket(ws, {
    "item.created": (item: Item) => {
      if (item.type !== "claim") return;
      changed(item);
      // The journalist who created it already had their confirmation.
      if (item.author_id !== me?.id)
        toast(t.claims.liveNew(toClaim(item).ref), { description: item.title });
    },
    "item.updated": (item: Item) => {
      if (item.type === "claim") changed(item);
    },
    "item.deleted": ({ id }: { id: string }) => {
      void mutatePages(
        (current) =>
          current?.map((p) => ({
            ...p,
            items: p.items.filter((i) => i.id !== id),
          })),
        { revalidate: false },
      );
      void mutateBoard(
        (page) =>
          page && {
            ...page,
            items: page.items.filter((i) => i.id !== id),
            total: Math.max(0, page.total - 1),
          },
        { revalidate: false },
      );
      recount();
    },
    "demo.reset": () => reload(),
    reconnected: () => reload(),
  });

  const canMove = useCallback(() => Boolean(me), [me]);

  /** Optimistic: the card lands in its new column now; the server confirms or it goes back. */
  const move = useCallback(
    async (c: ClaimView, to: Status) => {
      const previous = c.item;
      upsertBoard({ ...previous, status: to });
      try {
        upsertBoard(
          await api<Item>(`/workspaces/${ws}/items/${previous.id}`, {
            method: "PATCH",
            body: JSON.stringify({ status: to }),
          }),
        );
        undoable(t.claims.board.moved(c.ref, t.status[to]), async () =>
          upsertBoard(
            await api<Item>(`/workspaces/${ws}/items/${previous.id}`, {
              method: "PATCH",
              body: JSON.stringify({ status: previous.status }),
            }),
          ),
        );
      } catch (e) {
        upsertBoard(previous);
        toast.error(
          e instanceof ApiError && e.status === 403
            ? t.claims.board.cannotMove
            : t.detail.saveFailed,
        );
      }
    },
    [upsertBoard, ws],
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
            {total !== undefined && (
              <span className="tabular"> · {t.claims.total(total)}</span>
            )}
            {hasDemo && (
              <span className="ml-2 inline-block rounded-sm border border-border px-1.5 py-px align-[0.1em] text-xs whitespace-nowrap">
                {t.common.demoData}
              </span>
            )}
          </p>
        </div>
        <NewClaimSheet ws={ws} onCreated={changed} />
      </header>

      {!online && (
        <p
          role="status"
          className="mx-4 mb-4 flex items-center gap-2 rounded-md bg-verdict-misleading-soft px-3 py-2 text-sm text-verdict-misleading-ink lg:mx-0"
        >
          <IconWifiSlash className="size-4" aria-hidden />
          {t.claims.offline}
        </p>
      )}

      {view === "list" &&
        tab !== "confirm" &&
        counts.confirm > 0 &&
        !claims.some((c) => c.suggested && !c.verdict) && (
          <div className="mx-4 mb-5 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-md border-2 border-dashed border-foreground bg-card px-4 py-3 lg:mx-0">
            <p className="font-bold">{t.claims.waiting(counts.confirm)}</p>
            <button
              type="button"
              onClick={() => go({ onglet: "confirm" })}
              className="inline-flex items-center gap-1.5 font-bold underline underline-offset-4"
            >
              {t.claims.waitingAction}{" "}
              <IconArrowRight className="size-4" aria-hidden />
            </button>
          </div>
        )}

      <div className="flex flex-wrap items-center gap-2 px-4 pb-4 lg:px-0">
        {view === "list" && (
          <div className="-mx-4 basis-[calc(100%+2rem)] px-4 lg:mx-0 lg:px-0 @3xl:basis-auto">
            <PillTabs
              className="seg-scroll"
              label={t.claims.tabs.label}
              value={tab}
              onChange={(k) => go({ onglet: k })}
              items={TABS.map((k) => ({
                value: k,
                label: t.claims.tabs[k],
                count: counts[k],
                alert: k === "confirm" && counts.confirm > 0,
              }))}
            />
          </div>
        )}
        <div className="relative min-w-0 flex-1 basis-56">
          <IconMagnifyingGlass
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t.claims.search}
            aria-label={t.claims.search}
            className="h-10 bg-card pl-9"
          />
        </div>
        <Select value={assignee} onValueChange={setAssignee}>
          <SelectTrigger
            size="sm"
            aria-label={t.detail.assignee}
            className="w-auto min-w-40"
          >
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
        <PillTabs
          kind="radio"
          className="shrink-0"
          label={t.claims.views.label}
          value={view}
          onChange={(v) => go({ vue: v })}
          items={[
            { value: "list", label: t.claims.views.grid, icon: IconRows },
            { value: "board", label: t.claims.views.board, icon: IconColumns },
          ]}
        />
      </div>

      {/* The previous rows stay while another tab, search or assignee loads: a thin ink line says so. */}
      <div
        className="mx-4 mb-2 h-0.5 overflow-hidden rounded-full lg:mx-0"
        aria-hidden
      >
        {refreshing && (
          <div className="h-full w-full animate-pulse rounded-full bg-foreground motion-reduce:animate-none" />
        )}
      </div>
      <div aria-busy={refreshing || undefined}>
        {error ? (
          <Empty
            title={t.claims.errorTitle}
            lead={error.message}
            action={
              <Button variant="outline" onClick={reload}>
                {t.claims.retry}
              </Button>
            }
          />
        ) : isLoading || !data ? (
          <div
            className="space-y-3 px-4 lg:px-0"
            aria-busy
            aria-label={t.common.loading}
          >
            {Array.from({ length: 5 }, (_, i) => (
              <Skeleton key={i} className="h-20 w-full" />
            ))}
          </div>
        ) : nothingAtAll ? (
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
          <Board
            ws={ws}
            claims={claims}
            now={now}
            names={names}
            canMove={canMove}
            onMove={move}
          />
        ) : (
          <>
            <DossierList ws={ws} claims={claims} now={now} names={names} />
            <LoadMore
              shown={claims.length}
              total={last?.total ?? 0}
              pageSize={PAGE}
              hasMore={Boolean(last?.next)}
              loading={loadingMore}
              failed={Boolean(pages.error)}
              onMore={() => void pages.setSize((n) => n + 1)}
              words={t.claims.more}
            />
          </>
        )}
      </div>
    </div>
  );
}
