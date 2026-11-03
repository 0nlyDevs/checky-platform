"use client";

import type { ItemPage, Verdict } from "@checky/shared";
import Link from "next/link";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";
import { IconAddressBook, IconArrowCounterClockwise, IconArrowRight, IconArrowSquareOut, IconCalendarDots, IconCircleNotch, IconMicrophone, IconQrCode, IconStop, IconTray } from "@/lib/icons";
import { AskView } from "@/components/ask/ask-view";
import { toClaim, VERDICT_META, VerdictChip } from "@/components/claims/verdict";
import { CrewLog } from "@/components/crew/crew-log";
import { Facts } from "@/components/crew/facts";
import { Lecture } from "@/components/crew/lecture";
import { PublicStrip, Reliability, RiskNote, ToneCard } from "@/components/crew/signals";
import { type AgentEvent, type CrewResult, frDate, hostOf, type Numbered } from "@/components/crew/types";
import { claimSteps, type Step, StepLine, type StepState } from "@/components/flow/step-line";
import { Button } from "@/components/ui/button";
import { useDictation } from "@/components/verify/dictation";
import { OnAir } from "@/components/verify/on-air";
import { useStickyColumns } from "@/hooks/use-sticky-columns";
import { api, ApiError, fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/live";
import { isOffline, useOnline } from "@/lib/offline";
import { addToOutbox, removeFromOutbox, updateOutbox, type OutboxEntry, useOutbox } from "@/lib/outbox";
import { postStream } from "@/lib/sse";
import { sendPhoto } from "@/components/scanner/read-image";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

const v = t.verify;
const c = t.linkCheck;
const k = t.crew;
const o = t.offline.outbox;
type StepKey = "read" | "claims" | "search" | "verdict";
type Run = { status: "waiting" | "running" | "done" | "failed"; summary: string };
type Result = CrewResult;

const KEYS: StepKey[] = ["read", "claims", "search", "verdict"];
const STALE_DAYS = 30; // the API's dates.STALE_DAYS
const ORIGIN: Record<string, string> = { facebook: "facebook", whatsapp: "whatsapp", tiktok: "tiktok" };
const fresh = () => Object.fromEntries(KEYS.map((key) => [key, { status: "waiting", summary: "" }])) as Record<StepKey, Run>;
const host = hostOf;
// Kept with the dossier: the facts and their snippets, not the pages' read text.
const light = (list?: Numbered[]) =>
  list?.map((x) => {
    const copy = { ...x };
    delete copy.passages;
    return copy;
  });

/** What a followed dossier keeps in `item.data`: the research, the reading with its confidence, the risk. */
export function dossierData(result: Result) {
  const { analysis, ...research } = result;
  delete research.tracked;
  return {
    research: { ...research, results: light(research.results), numbered: light(research.numbered), recheck: research.recheck && { ...research.recheck, results: light(research.recheck.results) } },
    ...(analysis ? { analysis, verdict_suggested: analysis.verdict } : {}),
    ...(result.risk ? { risk: result.risk } : {}),
  };
}

/** What was pasted becomes a link to read and/or the text itself. */
function split(input: string): { url: string | null; text: string | null } {
  const value = input.trim();
  const found = value.match(/https?:\/\/\S+/)?.[0] ?? null;
  if (found && found === value) return { url: found, text: null };
  return { url: found, text: value || null };
}

/** The four API steps folded onto the three of the line. */
function lineStates(s: Record<StepKey, Run>): Record<Step, StepState> {
  const from = (r: Run, doneAs: StepState = "done"): StepState =>
    r.status === "failed" ? "failed" : r.status === "done" ? doneAs : r.status === "running" ? "active" : "waiting";
  const claim =
    s.read.status === "failed" || s.claims.status === "failed"
      ? "failed"
      : s.claims.status === "done"
        ? "done"
        : s.read.status !== "waiting"
          ? "active"
          : "waiting";
  return { claim, evidence: from(s.search), conclusion: from(s.verdict, "suggested") };
}

/** The message with the phrases Checky flagged lit in citron, one after another. */
function Lit({ text, quotes }: { text: string; quotes: string[] }) {
  const hits: [number, number][] = [];
  const lower = text.toLowerCase();
  for (const q of quotes) {
    const at = lower.indexOf(q.toLowerCase());
    if (at >= 0 && !hits.some(([s, e]) => at < e && at + q.length > s)) hits.push([at, at + q.length]);
  }
  hits.sort((a, b) => a[0] - b[0]);
  const out: React.ReactNode[] = [];
  let pos = 0;
  hits.forEach(([s, e], i) => {
    if (s > pos) out.push(text.slice(pos, s));
    out.push(
      <mark key={s} className="signal-mark" style={{ "--i": i } as React.CSSProperties}>
        {text.slice(s, e)}
      </mark>,
    );
    pos = e;
  });
  out.push(text.slice(pos));
  return <>{out}</>;
}

/**
 * Vérifier: paste (or dictate) what came in and watch Checky work along the numbered line: it reads
 * the message and lights the phrases that should worry, brings what fact-checkers and the web say,
 * then suggests a conclusion. Nothing is written until the journalist follows it in the desk.
 * The second tab asks every source of the newsroom (and the agent for a deeper search).
 */
export function VerifyView() {
  const columns = useStickyColumns<HTMLDivElement>();
  const { ws } = useParams<{ ws: string }>();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const asked = params.get("mode");
  const mode = asked === "sources" ? "sources" : asked === "antenne" ? "onAir" : "message";
  const [input, setInput] = useState(params.get("lien") ?? "");
  const [sent, setSent] = useState<{ url: string | null; text: string | null } | null>(null);
  const [running, setRunning] = useState(false);
  // « Sans IA » for this run; the newsroom's own setting (Paramètres) always wins.
  const { data: newsroom } = useSWR<{ settings?: { ai_enabled?: boolean } }>(`/workspaces/${ws}`, fetcher);
  const newsroomAi = newsroom?.settings?.ai_enabled !== false;
  const [noAi, setNoAi] = useState(false);
  const aiEnabled = newsroomAi && !noAi;
  const [agents, setAgents] = useState<Record<string, AgentEvent>>({});
  const [runs, setRuns] = useState<Record<string, number>>({});
  const [steps, setSteps] = useState(fresh);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [claim, setClaim] = useState(0);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [tracking, setTracking] = useState(false);
  const [queued, setQueued] = useState<string | null>(null);
  const started = useRef(false);
  const dictation = useDictation((said) => setInput((prev) => (prev.trim() ? `${prev.trim()} ${said}` : said)));

  async function run(given?: { url: string | null; text: string | null; source_id?: string }) {
    const body: { url: string | null; text: string | null; source_id?: string } = given ?? split(input);
    if (running) return false;
    // The action stays lit; an empty field just gets the focus back.
    if (!body.url && !body.text && !body.source_id) {
      document.getElementById("verify-input")?.focus();
      return false;
    }
    // No network: kept in « À envoyer », run when the network returns.
    if (isOffline()) {
      await addToOutbox({ ws, text: input.trim() }).catch(() => null);
      setInput("");
      setQueued(o.queued);
      return false;
    }
    setQueued(null);
    setSent(body);
    setRunning(true);
    setSteps(fresh());
    setAgents({});
    setRuns({});
    setResult(null);
    setError(null);
    let success = false;
    try {
      await postStream(`/workspaces/${ws}/crew`, { ...body, ai_enabled: aiEnabled }, (event, data) => {
        if (event === "agent") {
          const agent = data as AgentEvent;
          setAgents((all) => ({ ...all, [agent.agent]: agent }));
          if (agent.status === "running") setRuns((all) => ({ ...all, [agent.agent]: (all[agent.agent] ?? 0) + 1 }));
        } else if (event === "step") {
          const d = data as { key: StepKey; status: Run["status"]; summary: string };
          setSteps((all) => ({ ...all, [d.key]: { status: d.status, summary: d.summary } }));
        } else if (event === "result") {
          success = true;
          const r = data as Result;
          setResult(r);
          setClaim(0);
          const cited = new Set((r.analysis?.evidence ?? []).map((e) => e.n ?? e.result));
          setPicked(new Set((r.results ?? []).filter((x) => x.url && (x.kind === "fact-check" || cited.has(x.n))).map((x) => x.url)));
        } else if (event === "error") {
          success = false;
          setError((data as { code?: string }).code === "ai_unavailable" ? c.busy : c.failed);
        }
      });
    } catch (err) {
      setError(err instanceof ApiError && err.status === 429 ? c.tooMany : c.failed);
    } finally {
      setRunning(false);
    }
    return success;
  }

  // Opened with ?lien=… (by the copilot, the scanner or an old « Analyser » link) or ?source=… (a
  // photo the scanner sent): run at once.
  useEffect(() => {
    if (started.current) return;
    const source = params.get("source");
    if (!params.get("lien") && !source) return;
    started.current = true;
    void Promise.resolve().then(() => run(source ? { url: null, text: null, source_id: source } : undefined));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // « À envoyer »: when the network returns, the oldest waiting check runs by itself.
  const online = useOnline();
  const outbox = useOutbox(ws);
  async function send(entry: OutboxEntry) {
    if (running || isOffline()) return;
    if (entry.text) {
      setInput(entry.text);
      if (await run(split(entry.text))) await removeFromOutbox(entry.id);
      return;
    }
    if (entry.photo || entry.sourceId) {
      setQueued(t.offline.scanner.sending);
      try {
        const source = entry.sourceId ?? await sendPhoto(ws, entry.photo!, entry.name);
        if (!entry.sourceId) await updateOutbox({ ...entry, photo: undefined, sourceId: source });
        setQueued(null);
        if (await run({ url: null, text: null, source_id: source })) await removeFromOutbox(entry.id);
      } catch {
        setQueued(t.offline.scanner.failed);
      }
    }
  }
  const next = outbox[0];
  useEffect(() => {
    if (!online || !next || running) return;
    const timer = setTimeout(() => {
      toast(o.running);
      void send(next);
    }, 800);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [online, next?.id]);

  async function track() {
    if (!result) return;
    const title = result.claims?.[claim] ?? result.title ?? sent?.text ?? result.url ?? "";
    setTracking(true);
    try {
      const act = (body: Record<string, unknown>) => api<{ item_id: string; ref: string | null }>(`/workspaces/${ws}/copilot/act`, { method: "POST", body: JSON.stringify(body) });
      const made = await act({
        kind: "create_claim",
        title: title.slice(0, 300),
        body: [result.summary, sent?.text && sent.text !== title ? sent.text : "", result.url ?? ""].filter(Boolean).join("\n\n").slice(0, 4000),
        origin: (result.platform && ORIGIN[result.platform]) || (result.kind === "page" ? "press" : "other"),
      });
      await api(`/workspaces/${ws}/items/${made.item_id}`, { method: "PATCH", body: JSON.stringify({ data: dossierData(result) }) });
      const links = [result.url, ...picked].filter((u, i, all): u is string => !!u && all.indexOf(u) === i);
      // one by one: the API checks each link before queueing it
      for (const link of links) await act({ kind: "attach_link", item_id: made.item_id, url: link }).catch(() => null);
      router.push(`/w/${ws}/claims/${made.item_id}` as never);
    } catch {
      setError(c.trackFailed);
      setTracking(false);
    }
  }

  function reset() {
    setSent(null);
    setResult(null);
    setError(null);
    setSteps(fresh());
    setAgents({});
    setRuns({});
    setInput("");
  }

  const toggle = (u: string) =>
    setPicked((all) => {
      const next = new Set(all);
      if (next.has(u)) next.delete(u);
      else next.add(u);
      return next;
    });

  const setMode = (m: "message" | "onAir" | "sources") =>
    router.replace((m === "sources" ? `${pathname}?mode=sources` : m === "onAir" ? `${pathname}?mode=antenne` : pathname) as never, { scroll: false });
  const touched = Boolean(sent);

  return (
    <div className="@container mx-auto max-w-[88rem] px-4 pt-6 pb-16 lg:px-10 lg:pt-10">
      <div ref={columns} className="grid gap-10 @5xl:grid-cols-[minmax(0,1fr)_19rem] @5xl:gap-12">
        <div className="min-w-0">
          <div role="tablist" aria-label={v.modes.label} className="mb-6 inline-flex rounded-md border border-border bg-card p-1">
            {(["message", "onAir", "sources"] as const).map((m) => (
              <button
                key={m}
                role="tab"
                type="button"
                aria-selected={mode === m}
                onClick={() => setMode(m)}
                className={cn(
                  "rounded-[3px] px-3.5 py-1.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  mode === m ? "bg-foreground font-bold text-background" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {v.modes[m]}
              </button>
            ))}
          </div>

          {mode === "onAir" ? (
            <OnAir ws={ws} />
          ) : mode === "sources" ? (
            <>
              <h1 className="page-title">{t.ask.title}</h1>
              <div className="mt-4 max-w-4xl">
                <AskView embedded />
              </div>
            </>
          ) : (
            <>
              <h1 className="page-title max-w-3xl">{v.title}</h1>
              <p className="mt-3 max-w-[62ch] text-lg text-pretty text-muted-foreground">{v.lead}</p>

              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void run();
                }}
                className="mt-7 max-w-4xl"
              >
                <label htmlFor="verify-input" className="sr-only">
                  {v.field}
                </label>
                <div className="rounded-md border border-input bg-card focus-within:border-foreground focus-within:ring-2 focus-within:ring-foreground/15">
                  <textarea
                    id="verify-input"
                    rows={touched ? 2 : 4}
                    maxLength={6000}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) e.currentTarget.form?.requestSubmit();
                    }}
                    placeholder={v.placeholder}
                    className="block w-full resize-none bg-transparent px-4 pt-4 pb-2 text-lg leading-relaxed outline-none placeholder:text-muted-foreground"
                  />
                  <div className="flex flex-wrap items-center gap-2 border-t border-border px-3 py-2.5">
                    {dictation.can && (
                      <Button type="button" variant="ghost" onClick={dictation.toggle} disabled={dictation.state === "transcribing"} className={cn("h-10", dictation.state === "recording" && "bg-verdict-false-soft text-verdict-false-ink")}>
                        {dictation.state === "recording" ? <IconStop aria-hidden /> : dictation.state === "transcribing" ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconMicrophone aria-hidden />}
                        {dictation.state === "recording" ? v.stopDictate : dictation.state === "transcribing" ? v.transcribing : v.dictate}
                      </Button>
                    )}
                    {dictation.error && <span className="text-sm text-verdict-false-ink">{dictation.error}</span>}
                    <Button type="submit" variant={result ? "outline" : "action"} size="xl" className="ml-auto" disabled={running}>
                      {running ? <IconCircleNotch className="animate-spin" aria-hidden /> : null}
                      {running ? v.running : v.submit}
                      {!running && <IconArrowRight aria-hidden />}
                    </Button>
                  </div>
                </div>
              </form>

              {queued && (
                <p role="status" className="mt-3 max-w-4xl font-bold text-pretty">
                  {queued}
                </p>
              )}
              {outbox.length > 0 && <Outbox entries={outbox} online={online} onRun={(e) => void send(e)} />}
              <div className="mt-3 max-w-4xl">
                <Link href={`/w/${ws}/scanner`} className="mb-2 inline-flex items-center gap-1.5 text-sm font-bold underline underline-offset-4">
                  <IconQrCode className="size-4" aria-hidden /> {t.offline.scanner.fromDesk}
                </Link>
              </div>
              <div className="mt-1 max-w-4xl">
                <label className="inline-flex cursor-pointer items-center gap-2 text-sm font-bold">
                  <input type="checkbox" checked={!aiEnabled} disabled={running || !newsroomAi} onChange={(e) => setNoAi(e.target.checked)} className="size-4 accent-[var(--foreground)]" />
                  {k.noAi.label}
                </label>
                {!aiEnabled && <p className="mt-0.5 text-sm text-muted-foreground">{newsroomAi ? k.noAi.hint : k.noAi.newsroomOff}</p>}
              </div>
              {!touched ? (
                <section className="mt-12 max-w-4xl">
                  <h2 className="font-display text-xl font-bold">{v.how}</h2>
                  <StepLine className="mt-5" states={{ claim: "waiting", evidence: "waiting", conclusion: "waiting" }} explain />
                </section>
              ) : (
                <Board
                  ws={ws}
                  sent={sent}
                  steps={steps}
                  agents={agents}
                  runs={runs}
                  running={running}
                  result={result}
                  error={error}
                  claim={claim}
                  setClaim={setClaim}
                  picked={picked}
                  toggle={toggle}
                  tracking={tracking}
                  onTrack={() => void track()}
                  onReset={reset}
                />
              )}
            </>
          )}
        </div>

        <DeskColumn ws={ws} />
      </div>
    </div>
  );
}

/** « À envoyer »: what was asked with no network, oldest first; each runs when the network returns. */
function Outbox({ entries, online, onRun }: { entries: OutboxEntry[]; online: boolean; onRun: (e: OutboxEntry) => void }) {
  return (
    <section aria-labelledby="outbox-title" className="mt-4 max-w-4xl rounded-md border border-dashed border-foreground bg-card p-4">
      <h2 id="outbox-title" className="flex items-center gap-2 font-bold">
        <IconTray className="size-5" aria-hidden /> {o.title} · {o.count(entries.length)}
      </h2>
      <ul className="mt-2 divide-y divide-border">
        {entries.map((e) => (
          <li key={e.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
            <span className="min-w-0 flex-1 truncate">{e.text ?? `${o.photo} · ${e.name ?? ""}`}</span>
            <span className="text-sm text-muted-foreground tabular">{new Date(e.at).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}</span>
            {online ? (
              <Button type="button" size="sm" variant="outline" onClick={() => onRun(e)}>
                {o.run}
              </Button>
            ) : (
              <span className="text-sm">{o.waiting}</span>
            )}
            <Button type="button" size="sm" variant="ghost" onClick={() => void removeFromOutbox(e.id)}>
              {o.remove}
            </Button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Board({
  ws,
  sent,
  steps,
  agents,
  runs,
  running,
  result,
  error,
  claim,
  setClaim,
  picked,
  toggle,
  tracking,
  onTrack,
  onReset,
}: {
  ws: string;
  sent: { url: string | null; text: string | null } | null;
  steps: Record<StepKey, Run>;
  agents: Record<string, AgentEvent>;
  runs: Record<string, number>;
  running: boolean;
  result: Result | null;
  error: string | null;
  claim: number;
  setClaim: (n: number) => void;
  picked: Set<string>;
  toggle: (u: string) => void;
  tracking: boolean;
  onTrack: () => void;
  onReset: () => void;
}) {
  const states = lineStates(steps);
  const quotes = (result?.signals ?? []).map((s) => s.quote);
  const notes: Partial<Record<Step, React.ReactNode>> = {
    claim: steps.claims.summary || steps.read.summary || undefined,
    evidence: steps.search.summary || undefined,
    conclusion:
      steps.verdict.status === "done"
        ? (VERDICT_META[steps.verdict.summary as Verdict]?.label ?? steps.verdict.summary)
        : steps.verdict.status === "waiting" && k.noLecture[steps.verdict.summary]
          ? k.noLecture[steps.verdict.summary]
          : undefined,
  };
  const message = sent?.text ?? result?.excerpt ?? "";
  const date = frDate(result?.published_at);

  return (
    <div className="mt-8 max-w-5xl space-y-8" aria-live="polite">
      <div className="grid items-start gap-6 md:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <section className="rounded-md border border-border bg-card p-5">
          <h2 className="font-display text-sm font-bold">{sent?.text ? v.message : v.link}</h2>
          {result?.site || sent?.url ? (
            <p className="mt-1 flex flex-wrap items-baseline gap-x-2 text-sm text-muted-foreground">
              <span className="font-bold text-foreground">{result?.site ?? host(sent?.url ?? "")}</span>
              {result?.author && <span>{c.by(result.author)}</span>}
              {date && (
                <time className="tabular" dateTime={result!.published_at!}>
                  {date}
                </time>
              )}
            </p>
          ) : null}
          {result?.title && !sent?.text && <p className="mt-3 font-bold text-pretty">{result.title}</p>}
          {message && (
            <p className="mt-3 text-lg leading-relaxed whitespace-pre-line text-pretty">
              <Lit text={message.slice(0, 900)} quotes={quotes} />
            </p>
          )}
          {result?.days_old != null && result.days_old > STALE_DAYS && (
            <p role="note" className="mt-4 flex gap-2 rounded-md bg-muted p-3 text-sm font-bold text-pretty">
              <IconCalendarDots className="mt-0.5 size-4 shrink-0" aria-hidden />
              {c.old(result.days_old)}
            </p>
          )}
          <RiskNote risk={result?.risk} />
          {sent?.url && (
            <a href={sent.url} target="_blank" rel="noreferrer" className="mt-4 inline-flex items-center gap-1 text-sm font-bold underline underline-offset-4">
              {c.openOriginal} <IconArrowSquareOut className="size-3.5" aria-hidden />
            </a>
          )}
        </section>

        <div className="space-y-5">
          <StepLine states={states} notes={notes} />
          <CrewLog agents={agents} runs={runs} running={running} />
        </div>
      </div>

      {error && (
        <p role="alert" className="rounded-md bg-verdict-false-soft px-4 py-3 text-verdict-false-ink">
          {error}
        </p>
      )}
      {result?.needs_text && (
        <p role="status" className="rounded-md bg-verdict-misleading-soft px-4 py-3 text-verdict-misleading-ink">
          {c.needsText}
        </p>
      )}
      {result?.tracked && (
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-border bg-card px-4 py-3">
          <span>{c.tracked(result.tracked.ref ?? "")}</span>
          <Link href={`/w/${ws}/claims/${result.tracked.item_id}` as never} className="font-bold underline underline-offset-4">
            {c.open} <IconArrowRight className="inline size-4" aria-hidden />
          </Link>
        </p>
      )}

      {/* What has not arrived yet holds its place, flat and at its final size, so nothing moves when it lands. */}
      {!result && !error && (running || Object.values(steps).some((x) => x.status !== "waiting")) && <PendingBlocks />}

      {result && !result.needs_text && (
        <>
          <Facts r={result} ws={ws} />
          <Wall r={result} picked={picked} toggle={toggle} />
          <Lecture r={result} />
          {(result.credibility || result.tone || !!result.framing?.length) && (
            <div className="grid items-start gap-4 md:grid-cols-2">
              {result.credibility && <Reliability c={result.credibility} />}
              <ToneCard tone={result.tone} framing={result.framing} />
            </div>
          )}
          {(result.claims?.length ?? 0) > 1 && (
            <section>
              <h2 className="font-display text-lg font-bold">{c.claims}</h2>
              <fieldset className="mt-3">
                <legend className="sr-only">{c.claimPick}</legend>
                <ul className="divide-y divide-border rounded-md border border-border bg-card">
                  {result.claims!.map((text, i) => (
                    <li key={i}>
                      <label className="flex cursor-pointer items-start gap-3 px-4 py-3">
                        <input type="radio" name="claim" checked={claim === i} onChange={() => setClaim(i)} className="mt-1 size-4 accent-[var(--foreground)]" />
                        <span className="text-pretty">{text}</span>
                      </label>
                    </li>
                  ))}
                </ul>
              </fieldset>
            </section>
          )}
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <IconAddressBook className="size-4 shrink-0" aria-hidden />
            <span className="font-bold">{k.contact}</span>
            <span className="text-muted-foreground">{k.contactHelp}</span>
            <Link href={`/w/${ws}/directory` as never} className="font-bold underline underline-offset-4">
              {k.openDirectory}
            </Link>
          </p>
          <PublicStrip r={result} />

          <div className="sticky bottom-0 z-10 -mx-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border bg-background px-4 py-3 max-[641px]:bottom-[calc(66px+env(safe-area-inset-bottom))] max-[901px]:pr-[88px] min-[641px]:max-[901px]:pl-[88px] lg:mx-0 lg:px-0">
            <Button variant="action" size="xl" onClick={onTrack} disabled={tracking}>
              {tracking && <IconCircleNotch className="animate-spin" aria-hidden />}
              {tracking ? c.tracking : c.track}
            </Button>
            <span className="text-sm text-muted-foreground">{c.trackHint(picked.size)}</span>
            <Button variant="ghost" className="ml-auto h-10" onClick={onReset}>
              <IconArrowCounterClockwise aria-hidden />
              {v.again}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

/** Flat placeholders (no shimmer) for the blocks a live check has not delivered yet, in their final order. */
function PendingBlocks() {
  return (
    <div aria-hidden className="space-y-8">
      <div data-pending="facts" className="h-[5.625rem] rounded-md bg-raised" />
      <div data-pending="wall">
        <div className="h-7 w-52 rounded-md bg-raised" />
        <div className="mt-0.5 h-5 w-80 max-w-full rounded-md bg-raised" />
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-[10.25rem] rounded-md bg-raised" />
          ))}
        </div>
      </div>
      <div data-pending="lecture" className="h-[14rem] rounded-md bg-raised" />
    </div>
  );
}

/** What fact-checkers, the web and Wikipedia say: each result arrives, then stays still to be read. */
function Wall({ r, picked, toggle }: { r: Result; picked: Set<string>; toggle: (u: string) => void }) {
  const rows = (r.results ?? []).filter((x) => x.url);
  if (!r.claims?.length && !rows.length) return null;
  return (
    <section>
      <h2 className="font-display text-lg font-bold">{v.wall}</h2>
      {rows.length ? (
        <>
          <p className="mt-0.5 text-sm text-muted-foreground">{c.elsewhereNote}</p>
          <ul className="mt-3 grid gap-3 md:grid-cols-2">
            {rows.map((x, i) => (
              <li key={x.url} className="arrive" style={{ "--i": i } as React.CSSProperties}>
                <label className={cn("flex h-full cursor-pointer gap-3 rounded-md border bg-card p-4 transition-colors", picked.has(x.url) ? "border-foreground" : "border-border hover:border-input")}>
                  <input type="checkbox" checked={picked.has(x.url)} onChange={() => toggle(x.url)} aria-label={c.attach(x.title)} className="mt-1 size-4 shrink-0 accent-[var(--foreground)]" />
                  <span className="min-w-0 flex-1 text-sm">
                    <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span className="font-display text-xs font-bold tabular">[{x.n}]</span>
                      <span className={cn("rounded-sm px-1.5 py-px text-xs font-bold", x.kind === "fact-check" ? "bg-foreground text-background" : "bg-muted")}>{x.kind === "recheck" ? k.recheck : (c.kind[x.kind] ?? x.kind)}</span>
                      <span className="text-muted-foreground">{host(x.url)}</span>
                      <span className="text-muted-foreground">· {frDate(x.date) ?? k.undated}</span>
                    </span>
                    <a href={x.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} className="mt-1.5 block font-bold text-pretty hover:underline">
                      {x.title}
                    </a>
                    {x.snippet && <span className="mt-1 line-clamp-3 block text-pretty text-muted-foreground">{x.snippet}</span>}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="mt-2 text-muted-foreground">{c.noResults}</p>
      )}
    </section>
  );
}

/** Beside the check: the dossiers still open (oldest first) and what the desk settled lately. */
function DeskColumn({ ws }: { ws: string }) {
  const { data } = useSWR<ItemPage>(`/workspaces/${ws}/items?limit=200`, fetcher);
  const claims = useMemo(() => (data?.items ?? []).map(toClaim), [data]);
  const open = claims
    .filter((x) => x.status === "to_check" || x.status === "in_progress")
    .sort((a, b) => (a.firstSeen?.getTime() ?? 0) - (b.firstSeen?.getTime() ?? 0))
    .slice(0, 4);
  const recent = claims
    .filter((x) => x.verdict)
    .sort((a, b) => b.item.updated_at.localeCompare(a.item.updated_at))
    .slice(0, 3);
  return (
    <aside className="space-y-8 @6xl:pt-14">
      <section>
        <h2 className="flex items-baseline justify-between gap-3 font-display text-lg font-bold">
          {v.open}
          <Link href={`/w/${ws}/claims` as never} className="font-sans text-sm font-normal underline underline-offset-4">
            {v.allDossiers}
          </Link>
        </h2>
        {data && !open.length && <p className="mt-2 text-sm text-muted-foreground">{v.noOpen}</p>}
        <ul className="mt-3 space-y-2">
          {open.map((x) => (
            <li key={x.item.id}>
              <Link href={`/w/${ws}/claims/${x.item.id}` as never} className="block rounded-md border border-border bg-card p-3 transition-colors hover:border-foreground">
                <span className="font-display text-xs font-bold text-muted-foreground tabular">{x.ref}</span>
                <span className="mt-0.5 line-clamp-2 block font-bold text-pretty">{x.item.title}</span>
                <StepLine variant="mini" states={claimSteps(x)} className="mt-2.5" />
              </Link>
            </li>
          ))}
        </ul>
      </section>
      {!!recent.length && (
        <section>
          <h2 className="font-display text-lg font-bold">{v.recent}</h2>
          <ul className="mt-3 divide-y divide-border border-y border-border">
            {recent.map((x) => (
              <li key={x.item.id}>
                <Link href={`/w/${ws}/claims/${x.item.id}` as never} className="block py-3 hover:underline">
                  <span className="line-clamp-2 text-pretty">{x.item.title}</span>
                  <VerdictChip verdict={x.verdict!} className="mt-1.5" />
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </aside>
  );
}
