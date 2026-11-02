"use client";

import type { Activity, Comment, Item, ItemPatch, Status, Verdict } from "@fanilo/shared";
import { STATUSES, VERDICTS } from "@fanilo/shared";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { ArrowLeft, LoaderCircle, Pencil, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { AirtimeStrip } from "@/components/claims/airtime-strip";
import { formatTime } from "@/components/claims/day-grid";
import { StatusLabel, toClaim, VERDICT_META, VerdictBadge } from "@/components/claims/verdict";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkspace } from "@/hooks/use-workspace";
import { useWorkspaceSocket } from "@/hooks/use-workspace-socket";
import { api, ApiError, fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/fr";
import { cn } from "@/lib/utils";

const dayFmt = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short" });
const rtf = new Intl.RelativeTimeFormat("fr-FR", { numeric: "auto" });

function ago(iso: string, now: Date) {
  const s = (new Date(iso).getTime() - now.getTime()) / 1000;
  if (s > -60) return "à l'instant";
  if (s > -3600) return rtf.format(Math.round(s / 60), "minute");
  if (s > -86400) return rtf.format(Math.round(s / 3600), "hour");
  return rtf.format(Math.round(s / 86400), "day");
}

const textareaClass =
  "w-full resize-none rounded-md border border-input bg-card px-3 py-2 text-base outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30";

/** One activity row in plain French: who did what. */
function describe(a: Activity, nameOf: (id: string) => string): string {
  if (a.action === "create") return t.detail.events.created;
  if (a.action === "comment") return t.detail.events.commented;
  if (a.action === "delete") return t.detail.events.deleted;
  const diff = a.diff as Record<string, { from: unknown; to: unknown }>;
  if (diff.status) {
    const s = (v: unknown) => t.status[v as Status] ?? String(v);
    return t.detail.events.status(s(diff.status.from), s(diff.status.to));
  }
  if (diff.data) {
    const from = (diff.data.from as Record<string, unknown> | null)?.verdict;
    const to = (diff.data.to as Record<string, unknown> | null)?.verdict;
    if (from !== to) {
      return typeof to === "string" && to in VERDICT_META
        ? t.detail.events.verdictSet(VERDICT_META[to as Verdict].label)
        : t.detail.events.verdictCleared;
    }
    const fromA = (diff.data.from as Record<string, unknown> | null)?.assignee_id;
    const toA = (diff.data.to as Record<string, unknown> | null)?.assignee_id;
    if (fromA !== toA) {
      return typeof toA === "string" ? t.detail.events.assigned(nameOf(toA)) : t.detail.events.unassigned;
    }
  }
  return t.detail.events.edited;
}

function Section({ title, children, aside }: { title: string; children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <section className="border-t border-border pt-5">
      <div className="mb-3 flex items-center justify-between gap-4">
        <h2 className="font-semibold">{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

export function ClaimDetail() {
  const { ws, id } = useParams<{ ws: string; id: string }>();
  const router = useRouter();
  const base = `/workspaces/${ws}/items/${id}`;
  const { data: item, error, mutate } = useSWR<Item>(base, fetcher);
  const { data: comments, mutate: mutateComments } = useSWR<Comment[]>(`${base}/comments`, fetcher);
  const { data: history, mutate: mutateHistory } = useSWR<Activity[]>(
    `/workspaces/${ws}/activity?entity_id=${id}&limit=50`,
    fetcher,
  );
  const { me, role, names, members } = useWorkspace(ws);
  const [now, setNow] = useState(() => new Date());
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [comment, setComment] = useState("");
  const [posting, setPosting] = useState(false);

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(timer);
  }, []);

  useWorkspaceSocket(ws, {
    "item.updated": (updated: Item) => {
      if (updated.id !== id) return;
      mutate(updated, { revalidate: false });
      mutateHistory();
    },
    "item.deleted": ({ id: gone }: { id: string }) => {
      if (gone !== id) return;
      toast(t.detail.deleted);
      router.replace(`/w/${ws}/affirmations`);
    },
    "comment.created": (c: Comment) => {
      if (c.item_id !== id) return;
      mutateComments((list) => (list?.some((x) => x.id === c.id) ? list : [...(list ?? []), c]), {
        revalidate: false,
      });
      mutateHistory();
    },
    reconnected: () => {
      mutate();
      mutateComments();
      mutateHistory();
    },
  });

  const claim = useMemo(() => (item ? toClaim(item) : null), [item]);
  const canEdit = Boolean(item && me && (item.author_id === me.id || role === "editor" || role === "admin"));
  const name = (userId: string) => (userId === me?.id ? t.detail.you : (names.get(userId) ?? t.detail.someone));

  /** Optimistic patch: the screen changes now, the server confirms or we roll back. */
  async function patch(change: ItemPatch, optimistic: Partial<Item>) {
    if (!item) return;
    const previous = item;
    mutate({ ...item, ...optimistic }, { revalidate: false });
    try {
      const saved = await api<Item>(base, { method: "PATCH", body: JSON.stringify(change) });
      mutate(saved, { revalidate: false });
      mutateHistory();
      return true;
    } catch (e) {
      mutate(previous, { revalidate: false });
      toast.error(e instanceof ApiError && e.status === 403 ? t.detail.forbidden : t.detail.saveFailed);
      return false;
    }
  }

  const setVerdict = (verdict: Verdict | null) =>
    patch({ data: { verdict } }, { data: { ...item!.data, verdict } });

  async function saveText(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const title = String(form.get("title")).trim();
    const body = String(form.get("body") ?? "").trim();
    setSaving(true);
    if (await patch({ title, body }, { title, body })) {
      setEditing(false);
      toast.success(t.detail.saved);
    }
    setSaving(false);
  }

  async function postComment(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const body = comment.trim();
    if (!body) return;
    setPosting(true);
    try {
      const c = await api<Comment>(`${base}/comments`, { method: "POST", body: JSON.stringify({ body }) });
      mutateComments((list) => (list?.some((x) => x.id === c.id) ? list : [...(list ?? []), c]), {
        revalidate: false,
      });
      mutateHistory();
      setComment("");
    } catch {
      toast.error(t.detail.saveFailed);
    } finally {
      setPosting(false);
    }
  }

  if (error) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10 lg:px-8">
        <BackLink ws={ws} />
        <p className="mt-6 text-muted-foreground">
          {error instanceof ApiError && error.status === 404 ? t.detail.notFound : t.claims.errorTitle}
        </p>
        {!(error instanceof ApiError && error.status === 404) && (
          <Button variant="outline" className="mt-4" onClick={() => mutate()}>
            {t.claims.retry}
          </Button>
        )}
      </div>
    );
  }

  if (!item || !claim) {
    return (
      <div className="mx-auto max-w-[90rem] space-y-5 px-4 py-8 lg:px-8" aria-busy aria-label={t.common.loading}>
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const seen = claim.firstSeen;
  const seenText = seen
    ? seen.toDateString() === now.toDateString()
      ? t.detail.seenAt(formatTime(seen))
      : t.detail.seenOn(dayFmt.format(seen), formatTime(seen))
    : null;
  const originLabel = claim.origin ? (t.origins[claim.origin as keyof typeof t.origins] ?? claim.origin) : null;
  const pendingSuggestion = claim.suggested && !claim.verdict ? claim.suggested : null;

  return (
    <div className="mx-auto max-w-[90rem] px-4 pt-6 pb-12 lg:px-8 lg:pt-8">
      <BackLink ws={ws} />

      <header className="mt-4">
        <p className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-muted-foreground">
          <span className="font-display text-lg font-semibold tracking-wide text-foreground tabular">{claim.ref}</span>
          {seenText && <span className="ml-1 tabular">{seenText}</span>}
          {originLabel && <span>· {originLabel}</span>}
        </p>
        {editing ? (
          <form id="edit-claim" onSubmit={saveText} className="mt-3 max-w-3xl space-y-4">
            <div className="space-y-2">
              <Label htmlFor="edit-title">{t.claims.form.claim}</Label>
              <textarea id="edit-title" name="title" required maxLength={300} rows={2} defaultValue={item.title} className={cn(textareaClass, "text-lg font-medium")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-body">{t.detail.context}</Label>
              <textarea id="edit-body" name="body" rows={4} defaultValue={item.body} placeholder={t.claims.form.contextPlaceholder} className={textareaClass} />
            </div>
            <div className="flex gap-2">
              <Button type="submit" disabled={saving}>
                {saving && <LoaderCircle className="animate-spin" aria-hidden />}
                {t.detail.save}
              </Button>
              <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
                {t.detail.cancel}
              </Button>
            </div>
          </form>
        ) : (
          <div className="mt-2 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <h1 className="max-w-4xl text-2xl leading-snug font-semibold tracking-tight text-balance lg:text-[1.75rem]">
              {item.title}
            </h1>
            <div className="flex shrink-0 items-center gap-2">
              <Label htmlFor="claim-status" className="sr-only">
                {t.detail.status}
              </Label>
              <Select
                value={claim.status}
                disabled={!canEdit}
                onValueChange={(status) => patch({ status }, { status })}
              >
                <SelectTrigger id="claim-status" aria-label={t.detail.status} className="h-9 min-w-40 flex-1 bg-card lg:flex-none">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {STATUSES.map((s) => (
                    <SelectItem key={s} value={s}>
                      <StatusLabel status={s} />
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {canEdit && (
                <Button variant="outline" className="h-9 shrink-0" onClick={() => setEditing(true)}>
                  <Pencil aria-hidden />
                  {t.detail.edit}
                </Button>
              )}
            </div>
          </div>
        )}
        <div className="max-w-4xl">
          <AirtimeStrip claim={claim} now={now} />
        </div>
      </header>

      <div className="mt-12 grid gap-10 lg:grid-cols-[minmax(0,1fr)_20rem] lg:gap-12">
        <div className="min-w-0 space-y-8">
          {!editing && (
            <Section title={t.detail.context}>
              {item.body ? (
                <p className="max-w-[70ch] whitespace-pre-line text-pretty">{item.body}</p>
              ) : (
                <p className="text-muted-foreground">{t.detail.noContext}</p>
              )}
            </Section>
          )}

          <Section title={t.detail.verdictTitle} aside={<VerdictBadge claim={claim} />}>
            <p className="text-sm text-muted-foreground">{t.detail.verdictLead}</p>

            {pendingSuggestion && (
              <div className={cn("mt-4 flex flex-wrap items-center gap-x-4 gap-y-3 rounded-md border border-dashed p-3.5", VERDICT_META[pendingSuggestion].soft, VERDICT_META[pendingSuggestion].ink, "border-current")}>
                <Sparkles className="size-4 shrink-0" aria-hidden />
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{t.detail.suggestion(VERDICT_META[pendingSuggestion].label)}</p>
                  <p className="text-sm opacity-90">{t.detail.suggestionLead}</p>
                </div>
                {canEdit && (
                  <Button size="sm" onClick={() => setVerdict(pendingSuggestion)}>
                    {t.detail.confirm}
                  </Button>
                )}
              </div>
            )}

            <div role="radiogroup" aria-label={t.detail.verdictTitle} className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
              {VERDICTS.map((v) => {
                const m = VERDICT_META[v];
                const Icon = m.icon;
                const active = claim.verdict === v;
                return (
                  <button
                    key={v}
                    type="button"
                    role="radio"
                    aria-checked={active}
                    disabled={!canEdit}
                    onClick={() => setVerdict(v)}
                    className={cn(
                      "flex h-11 items-center justify-center gap-2 rounded-md border text-sm font-medium transition-colors duration-150 outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60",
                      active ? cn(m.fill, m.on, "border-transparent") : cn("border-border bg-card hover:bg-accent", m.ink),
                    )}
                  >
                    <Icon className="size-4" aria-hidden />
                    {m.label}
                  </button>
                );
              })}
            </div>
            {canEdit && claim.verdict && (
              <button
                type="button"
                onClick={() => setVerdict(null)}
                className="mt-3 text-sm text-muted-foreground underline decoration-border underline-offset-4 hover:text-foreground"
              >
                {t.detail.clearVerdict}
              </button>
            )}
            {!canEdit && <p className="mt-3 text-sm text-muted-foreground">{t.detail.readOnly}</p>}
          </Section>

          <Section title={`${t.detail.comments}${comments?.length ? ` (${comments.length})` : ""}`}>
            {comments && comments.length === 0 && <p className="text-muted-foreground">{t.detail.noComments}</p>}
            <ol className="space-y-4">
              {comments?.map((c) => (
                <li key={c.id} className="animate-in fade-in-0 duration-200">
                  <p className="flex items-baseline gap-2 text-sm">
                    <span className="font-medium">{name(c.author_id)}</span>
                    <time dateTime={c.created_at} className="text-muted-foreground tabular">
                      {ago(c.created_at, now)}
                    </time>
                  </p>
                  <p className="mt-0.5 max-w-[70ch] whitespace-pre-line text-pretty">{c.body}</p>
                </li>
              ))}
            </ol>
            <form onSubmit={postComment} className="mt-5 space-y-2">
              <Label htmlFor="new-comment" className="sr-only">
                {t.detail.commentPlaceholder}
              </Label>
              <textarea
                id="new-comment"
                rows={3}
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) e.currentTarget.form?.requestSubmit();
                }}
                placeholder={t.detail.commentPlaceholder}
                className={textareaClass}
              />
              <div className="flex justify-end">
                <Button type="submit" disabled={posting || !comment.trim()}>
                  {posting && <LoaderCircle className="animate-spin" aria-hidden />}
                  {t.detail.post}
                </Button>
              </div>
            </form>
          </Section>
        </div>

        <aside className="space-y-8">
          <Section title={t.detail.details}>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2.5 text-sm">
              <dt className="text-muted-foreground">{t.claims.columns.ref}</dt>
              <dd className="font-display text-base font-semibold tracking-wide tabular">{claim.ref}</dd>
              <dt className="text-muted-foreground">{t.detail.addedBy}</dt>
              <dd>{name(item.author_id)}</dd>
              <dt className="self-center text-muted-foreground">
                <label htmlFor="claim-assignee">{t.detail.assignee}</label>
              </dt>
              <dd>
                <Select
                  value={claim.assigneeId ?? "none"}
                  disabled={!canEdit}
                  onValueChange={(v) => {
                    const assignee_id = v === "none" ? null : v;
                    patch({ data: { assignee_id } }, { data: { ...item.data, assignee_id } });
                  }}
                >
                  <SelectTrigger id="claim-assignee" className="h-8 w-full bg-card">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">{t.detail.nobody}</SelectItem>
                    {members?.map((m) => (
                      <SelectItem key={m.user_id} value={m.user_id}>
                        {m.user_id === me?.id ? `${m.name ?? m.email} (${t.detail.you.toLowerCase()})` : (m.name ?? m.email)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </dd>
              {seenText && (
                <>
                  <dt className="text-muted-foreground">{t.claims.columns.seenAt}</dt>
                  <dd className="font-display text-base tabular">{seenText.replace(/^vue (à |le )/, "")}</dd>
                </>
              )}
              {originLabel && (
                <>
                  <dt className="text-muted-foreground">{t.detail.origin}</dt>
                  <dd>{originLabel}</dd>
                </>
              )}
              <dt className="text-muted-foreground">{t.detail.sources}</dt>
              <dd className="tabular">{t.claims.sources(claim.sources)}</dd>
              <dt className="text-muted-foreground">{t.detail.tags}</dt>
              <dd>{item.tags.length ? item.tags.join(" · ") : <span className="text-muted-foreground">{t.detail.noTags}</span>}</dd>
            </dl>
          </Section>

          <Section title={t.detail.history}>
            {!history ? (
              <Skeleton className="h-24 w-full" />
            ) : (
              <ol className="space-y-3 border-l border-border pl-4">
                {history.map((a) => (
                  <li key={a.id} className="relative text-sm">
                    <span className="absolute top-1.5 -left-[1.3125rem] size-2 rounded-full border border-border bg-card" aria-hidden />
                    <p>
                      <span className="font-medium">{name(a.actor_id)}</span> {describe(a, (id) => names.get(id) ?? t.detail.someone)}
                    </p>
                    <time dateTime={a.created_at} className="text-muted-foreground tabular">
                      {ago(a.created_at, now)}
                    </time>
                  </li>
                ))}
              </ol>
            )}
          </Section>
        </aside>
      </div>
    </div>
  );
}

function BackLink({ ws }: { ws: string }) {
  return (
    <Link
      href={`/w/${ws}/affirmations`}
      className="inline-flex items-center gap-1.5 rounded-sm text-sm text-muted-foreground hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
    >
      <ArrowLeft className="size-4" aria-hidden />
      {t.detail.back}
    </Link>
  );
}
