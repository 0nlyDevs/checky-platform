"use client";

import type { ItemPage, Verdict } from "@fanilo/shared";
import Link from "next/link";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";
import { ArrowRight, BadgeCheck, CalendarClock, ExternalLink, LoaderCircle, Mic, RotateCcw, Sparkles, Square } from "lucide-react";
import { AgentTrace, ResearchDetails, type AgentEvent, type ResearchExtras } from "@/components/verify/research-details";
import { research } from "@/lib/i18n/fr/research";
import { AskView } from "@/components/ask/ask-view";
import { toClaim, VERDICT_META, VerdictChip } from "@/components/claims/verdict";
import { claimSteps, type Step, StepLine, type StepState } from "@/components/flow/step-line";
import { Button } from "@/components/ui/button";
import { API_URL, api, ApiError, fetcher } from "@/lib/api";
import { t } from "@/lib/i18n/fr";
import { postStream } from "@/lib/sse";
import { cn } from "@/lib/utils";

const v = t.verify;
const c = t.linkCheck;
type StepKey = "read" | "claims" | "search" | "verdict";
type Run = { status: "waiting" | "running" | "done" | "failed"; summary: string };
type Found = { n: number; kind: string; title: string; url: string; snippet: string; date?: string | null; read_status?: string; passages?: string[] };
type Evidence = { result: number; stance: "supports" | "contradicts" | "context"; quote: string };
type Result = ResearchExtras & {
  url: string | null;
  platform: string | null;
  kind?: "page" | "post" | "image" | "text";
  title?: string;
  site?: string | null;
  author?: string | null;
  published_at?: string | null;
  days_old?: number | null; // worked out by the API
  excerpt?: string;
  summary?: string;
  claims?: string[];
  signals?: { type: string; quote: string; why: string }[];
  results?: Found[];
  analysis?: { verdict: Verdict; reason: string; evidence: Evidence[]; missing: string };
  image?: { ai_markers?: string[]; content_credentials?: boolean; exif?: Record<string, string> };
  reverse_search?: { name: string; url: string }[];
  tracked?: { item_id: string; ref: string | null; title: string } | null;
  needs_text?: boolean;
};
type LogLine = { id: number; at: Date; text: string; state: Run["status"] };

const KEYS: StepKey[] = ["read", "claims", "search", "verdict"];
const STALE_DAYS = 30; // the API's dates.STALE_DAYS
const ORIGIN: Record<string, string> = { facebook: "facebook", whatsapp: "whatsapp", tiktok: "tiktok" };
const fresh = () => Object.fromEntries(KEYS.map((k) => [k, { status: "waiting", summary: "" }])) as Record<StepKey, Run>;
const clock = new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
const host = (u: string) => {
  try {
    return new URL(u).hostname.replace(/^www\./, "");
  } catch {
    return u;
  }
};

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

/** Record a short voice message and get its text back (the public transcription, French by default). */
function useDictation(onText: (text: string) => void) {
  const [state, setState] = useState<"idle" | "recording" | "transcribing">("idle");
  const [error, setError] = useState<string | null>(null);
  const rec = useRef<MediaRecorder | null>(null);
  // Known only in the browser: decided after mount so the server and the first render agree.
  const [can, setCan] = useState(false);
  useEffect(() => {
    requestAnimationFrame(() => setCan("MediaRecorder" in window && !!navigator.mediaDevices?.getUserMedia));
  }, []);

  async function toggle() {
    if (state === "recording") return rec.current?.stop();
    if (state !== "idle") return;
    setError(null);
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch {
      return setError(v.micDenied);
    }
    const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg", "audio/mp4"].find((m) => MediaRecorder.isTypeSupported?.(m)) ?? "";
    const mr = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    const chunks: Blob[] = [];
    mr.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    mr.onstop = async () => {
      stream.getTracks().forEach((tr) => tr.stop());
      setState("transcribing");
      try {
        const blob = new Blob(chunks, { type: (mr.mimeType || "audio/webm").split(";")[0] });
        const res = await fetch(`${API_URL}/api/v1/public/transcribe?lang=fr`, { method: "POST", headers: { "Content-Type": blob.type }, body: blob });
        if (!res.ok) throw new Error(String(res.status));
        const { text } = (await res.json()) as { text: string };
        if (text.trim()) onText(text.trim());
      } catch {
        setError(v.dictationFailed);
      } finally {
        setState("idle");
      }
    };
    rec.current = mr;
    mr.start(250);
    setState("recording");
  }
  return { state, error, can, toggle };
}

/**
 * Vérifier: paste (or dictate) what came in and watch Checky work along the numbered line: it reads
 * the message and lights the phrases that should worry, brings what fact-checkers and the web say,
 * then suggests a conclusion. Nothing is written until the journalist follows it in the desk.
 * The second tab asks every source of the newsroom (and the agent for a deeper search).
 */
export function VerifyView() {
  const { ws } = useParams<{ ws: string }>();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const mode = params.get("mode") === "sources" ? "sources" : "message";
  const [input, setInput] = useState(params.get("lien") ?? "");
  const [sent, setSent] = useState<{ url: string | null; text: string | null } | null>(null);
  const [running, setRunning] = useState(false);
  const [aiEnabled, setAiEnabled] = useState(true);
  const [agents, setAgents] = useState<AgentEvent[]>([]);
  const [steps, setSteps] = useState(fresh);
  const [log, setLog] = useState<LogLine[]>([]);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [claim, setClaim] = useState(0);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [tracking, setTracking] = useState(false);
  const started = useRef(false);
  const seq = useRef(0);
  const dictation = useDictation((said) => setInput((prev) => (prev.trim() ? `${prev.trim()} ${said}` : said)));

  const say = (text: string, state: Run["status"]) => setLog((all) => [...all, { id: ++seq.current, at: new Date(), text, state }]);

  async function run() {
    const body = split(input);
    if (running) return;
    // The action stays lit; an empty field just gets the focus back.
    if (!body.url && !body.text) return document.getElementById("verify-input")?.focus();
    setSent(body);
    setRunning(true);
    setSteps(fresh());
    setAgents([]);
    setLog([]);
    setResult(null);
    setError(null);
    try {
      await postStream(`/workspaces/${ws}/crew`, { ...body, ai_enabled: aiEnabled }, (event, data) => {
        if (event === "agent") {
          const agent = data as AgentEvent;
          setAgents(previous => [...previous.filter(a => a.agent !== agent.agent), agent]);
        } else if (event === "step") {
          const d = data as { key: StepKey; status: Run["status"]; summary: string };
          setSteps((all) => ({ ...all, [d.key]: { status: d.status, summary: d.summary } }));
          if (d.status === "running") say(v.log[d.key], "running");
          else if (d.status === "failed") say(`${v.log.failed} : ${d.summary || c.steps[d.key]}`, "failed");
          else if (d.key === "verdict") say(`${v.conclusion} : ${VERDICT_META[d.summary as Verdict]?.label ?? d.summary}`, "done");
          else if (d.summary) say(d.summary, "done");
        } else if (event === "result") {
          const r = data as Result;
          setResult(r);
          setClaim(0);
          const cited = new Set((r.analysis?.evidence ?? []).map((e) => e.result));
          setPicked(new Set((r.results ?? []).filter((x) => x.kind === "fact-check" || cited.has(x.n)).map((x) => x.url)));
        } else if (event === "error") {
          setError((data as { code?: string }).code === "ai_unavailable" ? c.busy : c.failed);
        }
      });
    } catch (err) {
      setError(err instanceof ApiError && err.status === 429 ? c.tooMany : c.failed);
    } finally {
      setRunning(false);
    }
  }

  // Opened with ?lien=… (by the copilot or an old « Analyser » link): run at once.
  useEffect(() => {
    if (started.current || !params.get("lien")) return;
    started.current = true;
    void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
      await api(`/workspaces/${ws}/items/${made.item_id}`, { method: "PATCH", body: JSON.stringify({ data: { research: result, verdict_suggested: result.analysis?.verdict } }) });
      const links = [result.url, ...picked].filter((u, i, all): u is string => !!u && all.indexOf(u) === i);
      // one by one: the API checks each link before queueing it
      for (const link of links) await act({ kind: "attach_link", item_id: made.item_id, url: link }).catch(() => null);
      router.push(`/w/${ws}/affirmations/${made.item_id}` as never);
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
    setAgents([]);
    setLog([]);
    setInput("");
  }

  const toggle = (u: string) =>
    setPicked((all) => {
      const next = new Set(all);
      if (next.has(u)) next.delete(u);
      else next.add(u);
      return next;
    });

  const setMode = (m: "message" | "sources") => router.replace((m === "sources" ? `${pathname}?mode=sources` : pathname) as never, { scroll: false });
  const touched = Boolean(sent);

  return (
    <div className="@container mx-auto max-w-[88rem] px-4 pt-6 pb-16 lg:px-10 lg:pt-10">
      <div className="grid gap-10 @5xl:grid-cols-[minmax(0,1fr)_19rem] @5xl:gap-12">
        <div className="min-w-0">
          <div role="tablist" aria-label={v.modes.label} className="mb-6 inline-flex rounded-md border border-border bg-card p-1">
            {(["message", "sources"] as const).map((m) => (
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

          {mode === "sources" ? (
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
                        {dictation.state === "recording" ? <Square aria-hidden /> : dictation.state === "transcribing" ? <LoaderCircle className="animate-spin" aria-hidden /> : <Mic aria-hidden />}
                        {dictation.state === "recording" ? v.stopDictate : dictation.state === "transcribing" ? v.transcribing : v.dictate}
                      </Button>
                    )}
                    {dictation.error && <span className="text-sm text-verdict-false-ink">{dictation.error}</span>}
                    <Button type="submit" variant={result ? "outline" : "action"} size="xl" className="ml-auto" disabled={running}>
                      {running ? <LoaderCircle className="animate-spin" aria-hidden /> : null}
                      {running ? v.running : v.submit}
                      {!running && <ArrowRight aria-hidden />}
                    </Button>
                  </div>
                </div>
              </form>

              <label className="mt-4 flex items-center gap-2 text-sm"><input type="checkbox" checked={aiEnabled} disabled={running} onChange={e => setAiEnabled(e.target.checked)} className="size-4" />{research.ai}</label>
              {!aiEnabled && <p className="mt-1 text-sm text-muted-foreground">{research.noAi}</p>}
              <AgentTrace agents={agents} />
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
                  log={log}
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

function Board({
  ws,
  sent,
  steps,
  log,
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
  log: LogLine[];
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
  const count = result?.results?.length ?? Number(steps.search.summary.match(/\d+/)?.[0] ?? 0);
  const notes: Partial<Record<Step, React.ReactNode>> = {
    claim: steps.claims.summary || steps.read.summary || undefined,
    evidence: steps.search.summary || undefined,
    conclusion:
      steps.verdict.status === "done"
        ? `${VERDICT_META[steps.verdict.summary as Verdict]?.label ?? steps.verdict.summary} · ${t.flow.state.suggested}`
        : result && !running && !result.analysis
          ? v.noConclusion
          : undefined,
  };
  const message = sent?.text ?? result?.excerpt ?? "";
  const date = result?.published_at ? new Date(`${result.published_at.slice(0, 10)}T00:00:00Z`) : null;

  return (
    <div className="mt-8 max-w-5xl space-y-8" aria-live="polite">
      <div className="grid gap-6 md:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <section className="rounded-md border border-border bg-card p-5">
          <h2 className="font-display text-sm font-bold">{sent?.text ? v.message : v.link}</h2>
          {result?.site || sent?.url ? (
            <p className="mt-1 flex flex-wrap items-baseline gap-x-2 text-sm text-muted-foreground">
              <span className="font-bold text-foreground">{result?.site ?? host(sent?.url ?? "")}</span>
              {result?.author && <span>{c.by(result.author)}</span>}
              {date && !Number.isNaN(date.getTime()) && (
                <time className="tabular" dateTime={result!.published_at!}>
                  {date.toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" })}
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
              <CalendarClock className="mt-0.5 size-4 shrink-0" aria-hidden />
              {c.old(result.days_old)}
            </p>
          )}
          {!!result?.signals?.length && (
            <div className="mt-5 border-t border-border pt-4">
              <h3 className="text-sm font-bold">{v.signals}</h3>
              <ul className="mt-2 space-y-2">
                {result.signals.map((s, i) => (
                  <li key={i} className="arrive text-sm" style={{ "--i": i } as React.CSSProperties}>
                    <span className="font-bold">{c.signal[s.type] ?? s.type}</span> · <span className="text-muted-foreground">« {s.quote} »</span>
                    {s.why && <span className="block text-pretty text-muted-foreground">{s.why}</span>}
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-muted-foreground">{c.signalsNote}</p>
            </div>
          )}
          {sent?.url && (
            <a href={sent.url} target="_blank" rel="noreferrer" className="mt-4 inline-flex items-center gap-1 text-sm font-bold underline underline-offset-4">
              {c.openOriginal} <ExternalLink className="size-3.5" aria-hidden />
            </a>
          )}
        </section>

        <div className="space-y-5">
          <StepLine states={states} notes={notes} />
          <section className="rounded-md bg-live p-4 text-live-foreground">
            <h2 className="flex items-center justify-between gap-3 font-display text-sm font-bold">
              {v.live}
              <span className="flex items-center gap-1.5 text-xs font-bold">
                <span className={cn("size-2 rounded-full", running ? "animate-pulse bg-action" : "bg-live-muted")} aria-hidden />
                {running ? v.liveNow : v.liveDone}
              </span>
            </h2>
            <ol className="mt-3 space-y-1.5 text-sm">
              {log.map((l) => (
                <li key={l.id} className="arrive flex items-baseline gap-3">
                  <time className="shrink-0 text-xs text-live-muted tabular">{clock.format(l.at)}</time>
                  <span className={cn("min-w-0 text-pretty", l.state === "failed" && "text-verdict-false-ink dark:text-verdict-false")}>{l.text}</span>
                </li>
              ))}
            </ol>
            {count > 0 && (
              <p className="arrive mt-3 inline-flex rounded-full border border-live-border px-2.5 py-0.5 font-display text-sm font-bold tabular">{v.sourcesCount(count)}</p>
            )}
          </section>
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
          <Link href={`/w/${ws}/affirmations/${result.tracked.item_id}` as never} className="font-bold underline underline-offset-4">
            {c.open} <ArrowRight className="inline size-4" aria-hidden />
          </Link>
        </p>
      )}

      {result && !result.needs_text && (
        <>
          <Conclusion r={result} />
          <ResearchDetails data={result} ws={ws} />
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
          {(result.image || result.reverse_search) && <ImageFacts r={result} />}
          <Wall r={result} picked={picked} toggle={toggle} />

          <div className="sticky bottom-[calc(76px+env(safe-area-inset-bottom))] z-10 -mx-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border bg-background px-4 py-3 lg:bottom-0 lg:mx-0 lg:px-0">
            <Button variant="action" size="xl" onClick={onTrack} disabled={tracking}>
              {tracking && <LoaderCircle className="animate-spin" aria-hidden />}
              {tracking ? c.tracking : c.track}
            </Button>
            <span className="text-sm text-muted-foreground">{c.trackHint(picked.size)}</span>
            <Button variant="ghost" className="ml-auto h-10" onClick={onReset}>
              <RotateCcw aria-hidden />
              {v.again}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

/** The suggestion lands once, as a block: dashed outline on the verdict's soft ground, word first. */
function Conclusion({ r }: { r: Result }) {
  const a = r.analysis;
  if (!a) return r.claims?.length ? <p className="text-muted-foreground">{c.noVerdict}</p> : null;
  const m = VERDICT_META[a.verdict];
  const Icon = m.icon;
  const byN = new Map((r.results ?? []).map((x) => [x.n, x]));
  return (
    <section className="verdict-land">
      <h2 className="sr-only">{v.conclusion}</h2>
      <div className={cn("rounded-md border-2 border-dashed p-5 md:p-6", m.soft, m.ink, "border-current")}>
        <p className="flex items-center gap-3 font-display text-4xl font-extrabold tracking-tight md:text-5xl">
          <Icon className="size-9 shrink-0 md:size-11" strokeWidth={2.4} aria-hidden />
          {m.label}
        </p>
        <p className="mt-1 text-sm font-bold">{v.suggestedBy}</p>
        {a.reason && <p className="mt-4 max-w-[70ch] text-lg text-pretty text-foreground">{a.reason}</p>}
        {a.missing && (
          <p className="mt-3 max-w-[70ch] text-pretty text-foreground">
            <span className="font-bold">{c.missing} :</span> {a.missing}
          </p>
        )}
      </div>
      {!!a.evidence.length && (
        <div className="mt-4">
          <h3 className="text-sm font-bold">{v.restsOn}</h3>
          <ul className="mt-2 grid gap-2 md:grid-cols-2">
            {a.evidence.map((e, i) => {
              const src = byN.get(e.result);
              return (
                <li key={i} className="arrive rounded-md border border-border bg-card p-3 text-sm" style={{ "--i": i } as React.CSSProperties}>
                  <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="rounded-sm bg-muted px-1.5 py-px text-xs font-bold">{c.stance[e.stance]}</span>
                    {src ? (
                      <a href={src.url} target="_blank" rel="noreferrer" className="inline-flex min-w-0 items-center gap-1 font-bold hover:underline">
                        <span className="truncate">{src.title}</span>
                        <ExternalLink className="size-3 shrink-0 text-muted-foreground" aria-hidden />
                      </a>
                    ) : (
                      <span>{c.result(e.result)}</span>
                    )}
                  </p>
                  <blockquote className="mt-1.5 text-pretty text-muted-foreground">« {e.quote} »</blockquote>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </section>
  );
}

/** What fact-checkers, the web and Wikipedia say: each result arrives, then stays still to be read. */
function Wall({ r, picked, toggle }: { r: Result; picked: Set<string>; toggle: (u: string) => void }) {
  const rows = r.results ?? [];
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
                      <span className={cn("rounded-sm px-1.5 py-px text-xs font-bold", x.kind === "fact-check" ? "bg-foreground text-background" : "bg-muted")}>{c.kind[x.kind] ?? x.kind}</span>
                      <span className="text-muted-foreground">{host(x.url)}</span>
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

function ImageFacts({ r }: { r: Result }) {
  const img = r.image;
  const camera = [img?.exif?.Make, img?.exif?.Model].filter(Boolean).join(" ");
  return (
    <section className="rounded-md border border-border bg-card p-5">
      <h2 className="font-display text-lg font-bold">{c.image}</h2>
      <div className="mt-2 space-y-2 text-sm">
        {img &&
          (img.ai_markers?.length ? (
            <p className="flex items-start gap-1.5 font-bold text-verdict-misleading-ink">
              <Sparkles className="mt-0.5 size-4 shrink-0" aria-hidden />
              {c.imageMarkers(img.ai_markers.join(", "))}
            </p>
          ) : (
            <p className="text-muted-foreground">{c.imageNoMarkers}</p>
          ))}
        {img?.content_credentials && (
          <p className="flex items-start gap-1.5">
            <BadgeCheck className="mt-0.5 size-4 shrink-0" aria-hidden />
            {c.imageCredentials}
          </p>
        )}
        {camera && <p>{c.imageCamera(camera)}</p>}
        {!!r.reverse_search?.length && (
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="text-muted-foreground">{c.reverse} :</span>
            {r.reverse_search.map((x) => (
              <a key={x.name} href={x.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-bold underline underline-offset-4">
                {x.name} <ExternalLink className="size-3" aria-hidden />
              </a>
            ))}
          </p>
        )}
      </div>
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
          <Link href={`/w/${ws}/affirmations` as never} className="font-sans text-sm font-normal underline underline-offset-4">
            {v.allDossiers}
          </Link>
        </h2>
        {data && !open.length && <p className="mt-2 text-sm text-muted-foreground">{v.noOpen}</p>}
        <ul className="mt-3 space-y-2">
          {open.map((x) => (
            <li key={x.item.id}>
              <Link href={`/w/${ws}/affirmations/${x.item.id}` as never} className="block rounded-md border border-border bg-card p-3 transition-colors hover:border-foreground">
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
                <Link href={`/w/${ws}/affirmations/${x.item.id}` as never} className="block py-3 hover:underline">
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
