"use client";

import type { Activity, Comment, Item, ItemPatch, Status, Verdict } from "@fanilo/shared";
import { STATUSES } from "@fanilo/shared";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { ArrowLeft, ImageIcon, LoaderCircle, Pencil } from "lucide-react";
import { toast } from "sonner";
import { RoutePanel } from "@/components/claims/route-panel";
import { PublicationPanel } from "@/components/claims/publication-panel";
import { AnalysisPanel } from "@/components/claims/analysis-panel";
import { VerdictCard } from "@/components/claims/verdict-card";
import { claimSteps, StepDisc, type StepState } from "@/components/flow/step-line";
import { formatDuration, formatTime } from "@/lib/time";
import { StatusLabel, toClaim, VERDICT_META } from "@/components/claims/verdict";
import { statusAfter, VerdictDecision } from "@/components/claims/verdict-decision";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkspace } from "@/hooks/use-workspace";
import { SourcesPanel } from "@/components/sources/sources-panel";
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
  if (a.action === "source") return t.detail.events.sourceAdded;
  if (a.action === "analysis") {
    const v = (a.diff as { verdict_suggested?: string }).verdict_suggested;
    return t.detail.events.analysed(v && v in VERDICT_META ? VERDICT_META[v as Verdict].label : "—");
  }
  const diff = a.diff as Record<string, { from: unknown; to: unknown }>;
  const verdictFrom = (diff.data?.from as Record<string, unknown> | null)?.verdict;
  const verdictTo = (diff.data?.to as Record<string, unknown> | null)?.verdict;
  if (diff.data && verdictFrom !== verdictTo) {
    return typeof verdictTo === "string" && verdictTo in VERDICT_META
      ? t.detail.events.verdictSet(VERDICT_META[verdictTo as Verdict].label)
      : t.detail.events.verdictCleared;
  }
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

function Section({ title, children, id }: { title: string; children: React.ReactNode; id?: string }) {
  return (
    <section aria-labelledby={id} className="border-t border-border pt-5">
      <h2 id={id} className="mb-4 font-display text-lg font-bold">
        {title}
      </h2>
      {children}
    </section>
  );
}

/**
 * One part of the dossier on the numbered line: its disc in the gutter, a rule down to the next
 * disc (ink once the next part has started), the part's content beside it.
 */
function Step({ n, state, next, children }: { n: number; state: StepState; next?: StepState; children: React.ReactNode }) {
  return (
    <div className="relative grid grid-cols-[1.5rem_minmax(0,1fr)] gap-x-3 pb-12 md:grid-cols-[2.5rem_minmax(0,1fr)] md:gap-x-5">
      {next && (
        <span
          aria-hidden
          className={cn("absolute top-8 bottom-2 left-3 w-px md:top-12 md:left-5", next === "waiting" ? "bg-border" : "bg-foreground")}
        />
      )}
      <StepDisc n={n} state={state} size="sm" className="mt-1 md:hidden" />
      <StepDisc n={n} state={state} size="lg" className="hidden md:grid" />
      <div className="min-w-0">{children}</div>
    </div>
  );
}

/** A part's heading: the step's name, and its state while it is being worked on. */
function StepTitle({ id, title, state }: { id: string; title: string; state: StepState }) {
  return (
    <h2 id={id} className="mb-4 flex flex-wrap items-baseline gap-x-3 pt-0.5 font-display text-xl font-bold md:pt-1.5">
      {title}
      {state !== "done" && state !== "waiting" && <span className="font-sans text-sm font-normal text-muted-foreground">{t.flow.state[state]}</span>}
    </h2>
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
  const [cardOpen, setCardOpen] = useState(false);

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

  /** Verdict and status move together; a toast offers to put both back. */
  async function decide(verdict: Verdict | null) {
    if (!item || !claim) return;
    const before = { verdict: claim.verdict, status: claim.status };
    const status = statusAfter(verdict, claim.status);
    const ok = await patch({ status, data: { verdict } }, { status, data: { ...item.data, verdict } });
    if (!ok) return;
    const label = verdict ? t.detail.decision.done(VERDICT_META[verdict].label) : t.detail.decision.cleared;
    toast.success(label, {
      duration: 8000,
      action: {
        label: t.detail.decision.undo,
        onClick: async () => {
          const res = await api<Item>(base, {
            method: "PATCH",
            body: JSON.stringify({ status: before.status, data: { verdict: before.verdict } }),
          }).catch(() => null);
          if (res) {
            mutate(res, { revalidate: false });
            mutateHistory();
            toast(t.detail.decision.undone);
          }
        },
      },
    });
  }

  /** Downloading the card is what publishing means here: a verified claim becomes Publié. */
  function markShared() {
    if (claim?.status === "verified") patch({ status: "published" }, { status: "published" });
  }

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
  const steps = claimSteps(claim);
  const originLabel = claim.origin ? (t.origins[claim.origin as keyof typeof t.origins] ?? claim.origin) : null;
  const thread = [
    ...(comments ?? []).map((c) => ({ kind: "comment" as const, id: c.id, at: c.created_at, actor: c.author_id, body: c.body })),
    ...(history ?? [])
      .filter((a) => a.action !== "comment")
      .map((a) => ({ kind: "event" as const, id: a.id, at: a.created_at, actor: a.actor_id, body: describe(a, (uid) => names.get(uid) ?? t.detail.someone) })),
  ].sort((x, y) => y.at.localeCompare(x.at));

  return (
    <div className="mx-auto max-w-[90rem] px-4 pt-6 pb-12 lg:px-8 lg:pt-8">
      <BackLink ws={ws} />

      <div className="mt-6 grid gap-10 lg:grid-cols-[minmax(0,1fr)_20rem] lg:gap-12">
        {/* The dossier follows the numbered line: what is claimed, what the sources say, the conclusion. */}
        <div className="min-w-0">
          <Step n={1} state={steps.claim} next={steps.evidence}>
            <header>
              {editing ? (
                <form id="edit-claim" onSubmit={saveText} className="max-w-3xl space-y-4">
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
                <>
                  <h1 className="max-w-4xl font-display text-2xl leading-tight font-extrabold tracking-tight text-balance md:pt-0.5 lg:text-[2rem]">{item.title}</h1>
              <p className="mt-2 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-muted-foreground">
                <span className="font-display font-bold text-foreground tabular">{claim.ref}</span>
                {seenText && <span className="tabular">· {seenText}</span>}
                {originLabel && <span>· {originLabel}</span>}
                {seen && <span className="tabular">· {t.claims.board.circulating(formatDuration(now.getTime() - seen.getTime()))}</span>}
              </p>
                  {/* Context belongs with the claim it explains; when there is none, nothing takes its place. */}
                  {item.body && <p className="mt-3 max-w-[70ch] whitespace-pre-line text-pretty">{item.body}</p>}
                  <div className="mt-4 flex flex-wrap items-center gap-2">
                    <Label htmlFor="claim-status" className="sr-only">
                      {t.detail.status}
                    </Label>
                    <Select value={claim.status} disabled={!canEdit} onValueChange={(status) => patch({ status }, { status })}>
                      <SelectTrigger id="claim-status" aria-label={t.detail.status} className="h-10 min-w-40 bg-card">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {STATUSES.map((st) => (
                          <SelectItem key={st} value={st}>
                            <StatusLabel status={st} />
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {canEdit && (
                      <Button variant="outline" className="h-10 shrink-0" onClick={() => setEditing(true)}>
                        <Pencil aria-hidden />
                        {t.detail.edit}
                      </Button>
                    )}
                  </div>
                </>
              )}
            </header>
          </Step>

          <Step n={2} state={steps.evidence} next={steps.conclusion}>
            <section aria-labelledby="evidence">
              <StepTitle id="evidence" title={`${t.flow.steps.evidence}${claim.sources ? ` (${claim.sources})` : ""}`} state={steps.evidence} />
              <SourcesPanel ws={ws} itemId={id} />
              <div className="mt-8">
                <h3 className="mb-3 font-bold">{t.detail.analysisTitle}</h3>
                <AnalysisPanel ws={ws} item={item} sourceCount={claim.sources} />
              </div>
            </section>
          </Step>

          <Step n={3} state={steps.conclusion}>
            <section aria-labelledby="verdict">
              <StepTitle id="verdict" title={t.flow.steps.conclusion} state={steps.conclusion} />
              <VerdictDecision claim={claim} canEdit={canEdit} sourceCount={claim.sources} onDecide={decide} />
            </section>
          </Step>

          {claim.verdict && (
            <Section id="card" title={t.card.title}>
              {cardOpen ? (
                <div className="space-y-4">
                  <VerdictCard key={claim.verdict} ws={ws} item={item} verdict={claim.verdict} onShared={markShared} />
                  <Button variant="ghost" onClick={() => setCardOpen(false)}>
                    {t.detail.hideCard}
                  </Button>
                </div>
              ) : (
                <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
                  <p className="min-w-0 flex-1 text-muted-foreground">{t.detail.cardReady}</p>
                  <Button variant="outline" onClick={() => setCardOpen(true)}>
                    <ImageIcon aria-hidden />
                    {t.detail.makeCard}
                  </Button>
                </div>
              )}
            </Section>
          )}
        </div>

        <aside className="space-y-8">
          <RoutePanel item={item} />
          {canEdit && <PublicationPanel key={item.id} item={item} onSaved={(saved) => { mutate(saved, { revalidate: false }); mutateHistory(); }} />}
          <Section id="details" title={t.detail.details}>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2.5 text-sm">
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
              <dt className="text-muted-foreground">{t.detail.addedBy}</dt>
              <dd>{name(item.author_id)}</dd>
              {item.tags.length > 0 && (
                <>
                  <dt className="text-muted-foreground">{t.detail.tags}</dt>
                  <dd>{item.tags.join(" · ")}</dd>
                </>
              )}
            </dl>
          </Section>

          <Section id="thread" title={t.detail.thread}>
            <form onSubmit={postComment} className="space-y-2">
              <Label htmlFor="new-comment" className="sr-only">
                {t.detail.commentPlaceholder}
              </Label>
              <textarea
                id="new-comment"
                rows={2}
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) e.currentTarget.form?.requestSubmit();
                }}
                placeholder={t.detail.commentPlaceholder}
                className={textareaClass}
              />
              {comment.trim() && (
                <div className="flex justify-end">
                  <Button type="submit" size="sm" disabled={posting}>
                    {posting && <LoaderCircle className="animate-spin" aria-hidden />}
                    {t.detail.post}
                  </Button>
                </div>
              )}
            </form>
            {!history || !comments ? (
              <Skeleton className="mt-4 h-24 w-full" />
            ) : thread.length === 0 ? (
              <p className="mt-4 text-sm text-muted-foreground">{t.detail.noThread}</p>
            ) : (
              <ol className="mt-5 space-y-3.5 border-l border-border pl-4">
                {thread.map((e) => (
                  <li key={`${e.kind}-${e.id}`} className="relative text-sm">
                    <span
                      className={cn(
                        "absolute top-1.5 -left-[1.3125rem] size-2 rounded-full border border-border",
                        e.kind === "comment" ? "bg-foreground" : "bg-card",
                      )}
                      aria-hidden
                    />
                    <p className="flex flex-wrap items-baseline gap-x-2">
                      <span className="font-medium">{name(e.actor)}</span>
                      {e.kind === "event" && <span>{e.body}</span>}
                      <time dateTime={e.at} className="text-muted-foreground tabular">
                        {ago(e.at, now)}
                      </time>
                    </p>
                    {e.kind === "comment" && <p className="mt-0.5 whitespace-pre-line text-pretty">{e.body}</p>}
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
