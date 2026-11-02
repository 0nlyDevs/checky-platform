"use client";

import type { Activity, Comment, Item, ItemPatch, Status, Verdict } from "@fanilo/shared";
import { STATUSES } from "@fanilo/shared";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { IconArrowLeft, IconCircleNotch, IconImage, IconPencilSimple, IconWarning } from "@/lib/icons";
import { toast } from "sonner";
import { undoable } from "@/lib/undo";
import { RoutePanel } from "@/components/claims/route-panel";
import { VerdictCard } from "@/components/claims/verdict-card";
import { CarnetPanel } from "@/components/dossier/carnet";
import { DiffusePanel, type RouteDraft } from "@/components/dossier/diffuse-panel";
import { FactsPanel } from "@/components/dossier/facts-panel";
import { ReadingPanel } from "@/components/dossier/reading-panel";
import { hasResearch, type NewsroomSettings, readByline, readReading, readResearch, readRisk } from "@/components/dossier/types";
import { WhoPanel } from "@/components/dossier/who-panel";
import { claimSteps, StepDisc, type StepState } from "@/components/flow/step-line";
import { formatDuration, formatTime } from "@/lib/time";
import { exact, relative } from "@/lib/when";
import { StatusLabel, toClaim, VERDICT_META } from "@/components/claims/verdict";
import { VerdictDecision } from "@/components/claims/verdict-decision";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useStickyColumn } from "@/hooks/use-sticky-column";
import { useWorkspace } from "@/hooks/use-workspace";
import { SourcesPanel } from "@/components/sources/sources-panel";
import { useWorkspaceSocket } from "@/hooks/use-workspace-socket";
import { api, ApiError, fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/fr";
import { cn } from "@/lib/utils";

const dayFmt = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short" });

const textareaClass =
  "w-full resize-none rounded-md border border-input bg-card px-3 py-2 text-base outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30";

/** One activity row in plain French: who did what. */
function describe(a: Activity, nameOf: (id: string) => string): string {
  if (a.action === "create") return t.detail.events.created;
  if (a.action === "comment") return t.detail.events.commented;
  if (a.action === "delete") return t.detail.events.deleted;
  if (a.action === "source") return t.detail.events.sourceAdded;
  const ev = t.dossier.events;
  const word = (v: unknown) => (typeof v === "string" && v in VERDICT_META ? VERDICT_META[v as Verdict].label : "—");
  if (a.action === "sign") {
    const diff = a.diff as { verdict?: string; status?: string; adopted?: boolean };
    if (diff.adopted) return ev.adopt(word(diff.verdict));
    return diff.status === "published" ? ev.signPublish(word(diff.verdict)) : ev.sign(word(diff.verdict));
  }
  if (a.action === "publish") return ev.publish;
  if (a.action === "question") return ev.question;
  if (a.action === "answer") return ev.answer;
  if (a.action === "route") return ev.route;
  if (a.action === "diffuse") return ev.diffuse;
  if (a.action === "broadcast") return ev.broadcast;
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

/** « Risque élevé »: the danger the reading spotted in the wording, in ink (it is not a verdict). */
function RiskBadge({ item }: { item: Item }) {
  const risk = readRisk(item);
  if (!risk || risk.level === "low") return null;
  const kinds = [...new Set(risk.reasons.map((r) => t.dossier.risk.kinds[r.kind]).filter(Boolean))];
  return (
    <p className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
      <span className={cn("inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 font-bold", risk.level === "high" ? "border-2 border-foreground" : "border-border")}>
        <IconWarning className="size-4" aria-hidden />
        {t.dossier.risk.level[risk.level]}
      </span>
      {kinds.length > 0 && <span>{kinds.join(" · ")}</span>}
      <span className="w-full text-muted-foreground sm:w-auto">
        <span className="hidden sm:inline">· </span>
        {t.dossier.risk.lead}
      </span>
    </p>
  );
}

export function ClaimDetail() {
  const { ws, id } = useParams<{ ws: string; id: string }>();
  const column = useStickyColumn<HTMLElement>();
  const router = useRouter();
  const base = `/workspaces/${ws}/items/${id}`;
  const { data: item, error, mutate } = useSWR<Item>(base, fetcher);
  const { data: comments, mutate: mutateComments } = useSWR<Comment[]>(`${base}/comments`, fetcher);
  const { data: history, mutate: mutateHistory } = useSWR<Activity[]>(
    `/workspaces/${ws}/activity?entity_id=${id}&limit=50`,
    fetcher,
  );
  const { data: newsroom } = useSWR<NewsroomSettings>(`/workspaces/${ws}`, fetcher);
  const { mutate: revalidate } = useSWRConfig();
  const { me, role, names, members } = useWorkspace(ws);
  const [now, setNow] = useState(() => new Date());
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [comment, setComment] = useState("");
  const [posting, setPosting] = useState(false);
  const [cardOpen, setCardOpen] = useState(false);
  const [readingJob, setReadingJob] = useState<string | null>(null);
  const [routes, setRoutes] = useState<RouteDraft[]>([]);

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(timer);
  }, []);

  // One socket for the whole dossier; panels refetch through SWR keys.
  useWorkspaceSocket(ws, {
    "item.updated": (updated: Item) => {
      if (updated.id !== id) return;
      mutate(updated, { revalidate: false });
      mutateHistory();
      revalidate(`${base}/trajet`);
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
    "question.created": () => revalidate(`${base}/who`),
    "source.created": () => {
      revalidate(`${base}/who`);
      mutateHistory();
    },
    "route.added": () => revalidate(`${base}/trajet`),
    "job.done": (j: { id: string }) => j.id === readingJob && setReadingJob(null),
    "job.failed": (j: { id: string }) => {
      if (j.id !== readingJob) return;
      setReadingJob(null);
      toast.error(t.dossier.reading.failed);
    },
    reconnected: () => {
      mutate();
      mutateComments();
      mutateHistory();
    },
  });

  const claim = useMemo(() => (item ? toClaim(item) : null), [item]);
  const research = useMemo(() => (item ? readResearch(item) : null), [item]);
  const reading = useMemo(() => (item ? readReading(item) : null), [item]);
  const canEdit = Boolean(item && me && (item.author_id === me.id || role === "editor" || role === "admin"));
  const isEditor = role === "editor" || role === "admin";
  const name = (userId: string) =>
    userId === me?.id ? t.detail.you : userId === "public" ? t.dossier.events.public : userId === "system" ? "Checky" : (names.get(userId) ?? t.detail.someone);

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

  function saved(next: Item) {
    mutate(next, { revalidate: false });
    mutateHistory();
    revalidate(`${base}/trajet`);
  }

  /** A change already saved is put back on the server, then on screen. */
  async function putBack(change: ItemPatch) {
    const res = await api<Item>(base, { method: "PATCH", body: JSON.stringify(change) });
    mutate(res, { revalidate: false });
    mutateHistory();
  }

  /** Moving a dossier from one status to another is reversible: the toast offers to move it back. */
  async function changeStatus(status: Status) {
    if (!claim) return;
    const before = claim.status;
    if (status === before) return;
    const ok = await patch({ status }, { status });
    if (ok) undoable(t.detail.statusMoved(t.status[status]), () => putBack({ status: before }), t.detail.statusRestored(t.status[before]));
  }

  async function runReading() {
    try {
      const job = await api<{ id: string }>(`${base}/analyze`, { method: "POST" });
      setReadingJob(job.id);
    } catch {
      toast.error(t.dossier.reading.failed);
    }
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

  if (!item || !claim || !research) {
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
  const signedBy = typeof item.data.signed_by === "string" ? item.data.signed_by : null;
  const canSign = Boolean(me && (item.author_id === me.id || claim.assigneeId === me.id || isEditor));
  const double = Boolean(newsroom?.settings?.double_signature);
  const aiEnabled = newsroom?.settings?.ai_enabled ?? true;
  const analysisReason = typeof (item.data.analysis as { reason?: unknown } | undefined)?.reason === "string" ? String((item.data.analysis as { reason: string }).reason) : "";
  const thread = [
    ...(comments ?? []).map((c) => ({ kind: "comment" as const, id: c.id, at: c.created_at, actor: c.author_id, body: c.body })),
    ...(history ?? [])
      .filter((a) => a.action !== "comment")
      .map((a) => ({ kind: "event" as const, id: a.id, at: a.created_at, actor: a.actor_id, body: describe(a, (uid) => names.get(uid) ?? t.detail.someone) })),
  ].sort((x, y) => y.at.localeCompare(x.at));

  return (
    <div className="mx-auto max-w-[90rem] px-4 pt-6 pb-12 lg:px-8 lg:pt-8">
      <BackLink ws={ws} />

      <div className="mt-6 grid gap-10 lg:grid-cols-[minmax(0,1fr)_22rem] lg:gap-12">
        {/* The dossier follows the numbered line: what is claimed, what is known, the signed conclusion. */}
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
                      {saving && <IconCircleNotch className="animate-spin" aria-hidden />}
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
                  <RiskBadge item={item} />
                  {/* Context belongs with the claim it explains; when there is none, nothing takes its place. */}
                  {item.body && <p className="mt-3 max-w-[70ch] whitespace-pre-line text-pretty">{item.body}</p>}
                  <div className="mt-4 flex flex-wrap items-center gap-2">
                    <Label htmlFor="claim-status" className="sr-only">
                      {t.detail.status}
                    </Label>
                    <Select value={claim.status} disabled={!canEdit} onValueChange={(status) => void changeStatus(status as Status)}>
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
                        <IconPencilSimple aria-hidden />
                        {t.detail.edit}
                      </Button>
                    )}
                  </div>
                </>
              )}
            </header>
          </Step>

          <Step n={2} state={steps.evidence} next={steps.conclusion}>
            <section aria-labelledby="evidence" className="space-y-8">
              <StepTitle id="evidence" title={`${t.flow.steps.evidence}${claim.sources ? ` (${claim.sources})` : ""}`} state={steps.evidence} />
              {hasResearch(research) && <FactsPanel ws={ws} item={item} research={research} canSign={canSign} onSigned={saved} />}
              <SourcesPanel ws={ws} itemId={id} />
              <ReadingPanel reading={reading} running={Boolean(readingJob)} canRun={canEdit || canSign} aiEnabled={aiEnabled} onRun={runReading} />
            </section>
          </Step>

          <Step n={3} state={steps.conclusion}>
            <section aria-labelledby="verdict">
              <StepTitle id="verdict" title={t.dossier.sign.title} state={steps.conclusion} />
              <VerdictDecision
                key={`${item.id}-${String(item.data.signed_at ?? "")}-${item.status}`}
                ws={ws}
                item={item}
                suggested={claim.suggested}
                reasonDraft={analysisReason}
                byline={readByline(item)}
                canSign={canSign}
                canRelease={double && isEditor && Boolean(signedBy) && signedBy !== me?.id}
                doubleSignature={double}
                isPublic={Boolean(newsroom?.is_public)}
                onSaved={saved}
              />
            </section>
          </Step>
        </div>

        <aside ref={column} className="space-y-8 min-[1101px]:sticky min-[1101px]:self-start">
          <WhoPanel ws={ws} itemId={id} />
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
                    {posting && <IconCircleNotch className="animate-spin" aria-hidden />}
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
                      <time dateTime={e.at} title={exact(e.at)} className="text-muted-foreground tabular">
                        {relative(e.at, now)}
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

      {/* After the conclusion: where the rumour went and where the truth must follow. */}
      <div className="mt-4 space-y-12 border-t border-foreground pt-8">
        <RoutePanel
          ws={ws}
          item={item}
          onDiffuseHere={(gap) => {
            setRoutes((list) => (list.some((r) => r.channel === gap.channel && r.place === gap.place) ? list : [...list, { channel: gap.channel, place: gap.place, location: gap.location }]));
            document.getElementById("diffuser")?.scrollIntoView({ behavior: "smooth", block: "start" });
          }}
        />
        <DiffusePanel ws={ws} item={item} routes={routes} onRoutes={setRoutes} />

        {claim.verdict && (
          <section aria-labelledby="card" className="space-y-3">
            <h2 id="card" className="font-display text-xl font-bold">
              {t.card.title}
            </h2>
            {cardOpen ? (
              <div className="space-y-4">
                <VerdictCard key={claim.verdict} ws={ws} item={item} verdict={claim.verdict} onShared={() => mutateHistory()} />
                <Button variant="ghost" onClick={() => setCardOpen(false)}>
                  {t.detail.hideCard}
                </Button>
              </div>
            ) : (
              <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
                <p className="min-w-0 flex-1 text-muted-foreground">{t.detail.cardReady}</p>
                <Button variant="outline" onClick={() => setCardOpen(true)}>
                  <IconImage aria-hidden />
                  {t.detail.makeCard}
                </Button>
              </div>
            )}
          </section>
        )}

        <CarnetPanel ws={ws} item={item} />
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
      <IconArrowLeft className="size-4" aria-hidden />
      {t.detail.back}
    </Link>
  );
}
