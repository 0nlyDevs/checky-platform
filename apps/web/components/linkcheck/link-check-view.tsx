"use client";

import type { Verdict } from "@fanilo/shared";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { BadgeCheck, Check, CircleDashed, ExternalLink, LoaderCircle, ScanSearch, Sparkles, X } from "lucide-react";
import { VERDICT_META } from "@/components/claims/verdict";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError } from "@/lib/api";
import { t } from "@/lib/i18n/fr";
import { postStream } from "@/lib/sse";
import { cn } from "@/lib/utils";

const c = t.linkCheck;
type StepKey = keyof typeof c.steps;
type StepState = { status: "waiting" | "running" | "done" | "failed"; summary: string };
type Found = { n: number; kind: string; title: string; url: string; snippet: string };
type Evidence = { result: number; stance: "supports" | "contradicts" | "context"; quote: string };
type Result = {
  url: string | null;
  platform: string | null;
  kind?: "page" | "post" | "image" | "text";
  final_url?: string;
  title?: string;
  site?: string | null;
  author?: string | null;
  published_at?: string | null;
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
  read_error?: string;
};

const STEPS: StepKey[] = ["read", "claims", "search", "verdict"];
const fresh = () => Object.fromEntries(STEPS.map((k) => [k, { status: "waiting", summary: "" }])) as Record<StepKey, StepState>;
const ORIGIN: Record<string, string> = { facebook: "facebook", whatsapp: "whatsapp", tiktok: "tiktok" };
const host = (u: string) => {
  try {
    return new URL(u).hostname.replace(/^www\./, "");
  } catch {
    return u;
  }
};

/**
 * « Analyser un lien »: one pass from a pasted link (or text) to what it claims, its warning signs,
 * what fact-checkers and the web already say, and a suggested verdict. Nothing is written until
 * the journalist follows it in the desk, with the sources they tick.
 */
export function LinkCheckView() {
  const { ws } = useParams<{ ws: string }>();
  const router = useRouter();
  const params = useSearchParams();
  const [url, setUrl] = useState(params.get("lien") ?? "");
  const [text, setText] = useState("");
  const [showText, setShowText] = useState(false);
  const [running, setRunning] = useState(false);
  const [steps, setSteps] = useState(fresh);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [claim, setClaim] = useState(0);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [tracking, setTracking] = useState(false);
  const started = useRef(false);

  async function run() {
    if (running || (!url.trim() && !text.trim())) return;
    setRunning(true);
    setSteps(fresh());
    setResult(null);
    setError(null);
    try {
      await postStream(`/workspaces/${ws}/link-check`, { url: url.trim() || null, text: text.trim() || null }, (event, data) => {
        if (event === "step") {
          const d = data as { key: StepKey; status: StepState["status"]; summary: string };
          setSteps((all) => ({ ...all, [d.key]: { status: d.status, summary: d.summary } }));
        } else if (event === "result") {
          const r = data as Result;
          setResult(r);
          setClaim(0);
          // tick the fact-checks and what the suggestion rests on
          const cited = new Set((r.analysis?.evidence ?? []).map((e) => e.result));
          setPicked(new Set((r.results ?? []).filter((x) => x.kind === "fact-check" || cited.has(x.n)).map((x) => x.url)));
          if (r.needs_text) setShowText(true);
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

  // Opened by the copilot with ?lien=…: run at once.
  useEffect(() => {
    if (started.current || !params.get("lien")) return;
    started.current = true;
    void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function track() {
    if (!result) return;
    const title = result.claims?.[claim] ?? result.title ?? url;
    setTracking(true);
    try {
      const act = (body: Record<string, unknown>) => api<{ item_id: string; ref: string | null }>(`/workspaces/${ws}/copilot/act`, { method: "POST", body: JSON.stringify(body) });
      const made = await act({
        kind: "create_claim",
        title: title.slice(0, 300),
        body: [result.summary, result.url ?? ""].filter(Boolean).join("\n\n"),
        origin: (result.platform && ORIGIN[result.platform]) || (result.kind === "page" ? "press" : "other"),
      });
      const links = [result.url, ...picked].filter((u, i, all): u is string => !!u && all.indexOf(u) === i);
      // one by one: the API checks each link before queueing it
      for (const link of links) await act({ kind: "attach_link", item_id: made.item_id, url: link }).catch(() => null);
      router.push(`/w/${ws}/affirmations/${made.item_id}` as never);
    } catch {
      setError(c.trackFailed);
      setTracking(false);
    }
  }

  const toggle = (u: string) => setPicked((all) => {
    const next = new Set(all);
    if (next.has(u)) next.delete(u);
    else next.add(u);
    return next;
  });
  const touched = running || result || error;

  return (
    <div className="mx-auto max-w-4xl px-4 pt-6 pb-12 lg:px-8 lg:pt-8">
      <header className="pb-6">
        <h1 className="page-title">{c.title}</h1>
        <p className="mt-1 max-w-prose text-muted-foreground">{c.lead}</p>
      </header>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void run();
        }}
        className="space-y-3"
      >
        <Label htmlFor="link-url" className="sr-only">
          {c.url}
        </Label>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input
            id="link-url"
            type="url"
            inputMode="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder={c.urlPlaceholder}
            className="h-11 flex-1 bg-card text-base"
          />
          <Button type="submit" className="h-11 px-5" disabled={running || (!url.trim() && !text.trim())}>
            {running ? <LoaderCircle className="size-4 animate-spin" aria-hidden /> : <ScanSearch className="size-4" aria-hidden />}
            {running ? c.running : c.submit}
          </Button>
        </div>
        {showText ? (
          <div>
            <Label htmlFor="link-text" className="text-sm text-muted-foreground">
              {c.text}
            </Label>
            <textarea
              id="link-text"
              rows={4}
              maxLength={6000}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={c.textPlaceholder}
              className="mt-1 w-full resize-y rounded-lg border border-input bg-card px-3 py-2 text-base placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
            />
          </div>
        ) : (
          <button type="button" onClick={() => setShowText(true)} className="text-sm text-muted-foreground underline underline-offset-4 hover:text-foreground">
            {c.textToggle}
          </button>
        )}
      </form>

      {touched && (
        <ol className="mt-6 grid gap-x-6 gap-y-2 border-t border-border pt-5 text-sm sm:grid-cols-2" aria-live="polite">
          {STEPS.map((k) => (
            <li key={k} className="flex items-start gap-2">
              <StepIcon status={steps[k].status} />
              <span className={cn(steps[k].status === "waiting" && "text-muted-foreground")}>
                {c.steps[k]}
                {steps[k].summary && <span className="block text-muted-foreground">{steps[k].status === "done" && k === "verdict" ? VERDICT_META[steps[k].summary as Verdict]?.label ?? steps[k].summary : steps[k].summary}</span>}
              </span>
            </li>
          ))}
        </ol>
      )}

      {error && (
        <p role="alert" className="mt-5 rounded-md bg-verdict-false-soft px-3 py-2 text-sm text-verdict-false-ink">
          {error}
        </p>
      )}

      {result?.needs_text && (
        <p role="status" className="mt-5 rounded-md bg-verdict-misleading-soft px-3 py-2 text-sm text-verdict-misleading-ink">
          {c.needsText}
        </p>
      )}

      {result && !result.needs_text && (
        <div className="mt-6 space-y-8">
          {result.tracked && (
            <p className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-border bg-card px-3 py-2 text-sm">
              <span>{c.tracked(result.tracked.ref ?? "")}</span>
              <Link href={`/w/${ws}/affirmations/${result.tracked.item_id}` as never} className="font-medium underline underline-offset-4">
                {c.open} →
              </Link>
            </p>
          )}

          <Content r={result} />
          <Suggestion r={result} />
          <Claims r={result} claim={claim} setClaim={setClaim} />
          <Signals r={result} />
          {(result.image || result.reverse_search) && <ImageFacts r={result} />}
          <Elsewhere r={result} picked={picked} toggle={toggle} />

          <div className="sticky bottom-[calc(76px+env(safe-area-inset-bottom))] z-10 -mx-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border bg-background/95 px-4 py-3 backdrop-blur lg:bottom-0 lg:mx-0 lg:px-0">
            <Button onClick={() => void track()} disabled={tracking} className="h-11 px-5">
              {tracking && <LoaderCircle className="size-4 animate-spin" aria-hidden />}
              {tracking ? c.tracking : c.track}
            </Button>
            <span className="text-sm text-muted-foreground">{c.trackHint(picked.size)}</span>
          </div>
        </div>
      )}
    </div>
  );
}

function StepIcon({ status }: { status: StepState["status"] }) {
  if (status === "running") return <LoaderCircle className="mt-0.5 size-4 shrink-0 animate-spin" aria-hidden />;
  if (status === "done") return <Check className="mt-0.5 size-4 shrink-0" aria-hidden />;
  if (status === "failed") return <X className="mt-0.5 size-4 shrink-0 text-verdict-false-ink" aria-hidden />;
  return <CircleDashed className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />;
}

function Section({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-lg font-semibold">{title}</h2>
      {note && <p className="mt-0.5 text-sm text-muted-foreground">{note}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

function Content({ r }: { r: Result }) {
  const where = r.site || (r.url ? host(r.url) : c.pasted);
  const date = r.published_at ? new Date(r.published_at) : null;
  return (
    <Section title={c.content}>
      <div className="rounded-md border border-border bg-card p-4">
        <p className="flex flex-wrap items-baseline gap-x-2 text-sm text-muted-foreground">
          <span className="font-medium text-foreground">{where}</span>
          {r.author && <span>{c.by(r.author)}</span>}
          {date && !Number.isNaN(date.getTime()) && <time className="font-display tabular" dateTime={r.published_at!}>{date.toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" })}</time>}
        </p>
        {r.title && <p className="mt-1.5 font-medium text-pretty">{r.title}</p>}
        {r.summary && <p className="mt-1.5 max-w-[70ch] text-pretty">{r.summary}</p>}
        {r.excerpt && r.excerpt !== r.title && <p className="mt-2 line-clamp-4 max-w-[70ch] text-sm text-pretty text-muted-foreground">{r.excerpt}</p>}
        {r.url && (
          <a href={r.url} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1 text-sm font-medium underline underline-offset-4">
            {c.openOriginal} <ExternalLink className="size-3.5" aria-hidden />
          </a>
        )}
      </div>
    </Section>
  );
}

/** The AI's suggestion: dashed outline on the verdict's soft ground, icon and label, never colour alone. */
function Suggestion({ r }: { r: Result }) {
  const a = r.analysis;
  if (!a) return r.claims?.length ? <p className="text-sm text-muted-foreground">{c.noVerdict}</p> : null;
  const m = VERDICT_META[a.verdict];
  const Icon = m.icon;
  const byN = new Map((r.results ?? []).map((x) => [x.n, x]));
  return (
    <Section title={c.suggestion}>
      <div className={cn("rounded-md border border-dashed p-4", m.soft, m.ink, "border-current")}>
        <p className="flex items-center gap-2 text-lg font-semibold">
          <Icon className="size-5 shrink-0" aria-hidden />
          {m.label}
          <span className="text-sm font-normal">· {c.suggestedBy}</span>
        </p>
        {a.reason && <p className="mt-2 max-w-[70ch] text-pretty text-foreground">{a.reason}</p>}
        {a.missing && (
          <p className="mt-2 max-w-[70ch] text-sm text-pretty text-foreground">
            <span className="font-medium">{c.missing} :</span> {a.missing}
          </p>
        )}
      </div>
      {!!a.evidence.length && (
        <>
          <h3 className="mt-4 text-sm font-medium">{c.evidence}</h3>
          <ul className="mt-2 space-y-2">
            {a.evidence.map((e, i) => {
              const src = byN.get(e.result);
              return (
                <li key={i} className="rounded-md border border-border bg-card p-3 text-sm">
                  <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="rounded-sm border border-border px-1.5 py-px text-xs font-medium">{c.stance[e.stance]}</span>
                    {src ? (
                      <a href={src.url} target="_blank" rel="noreferrer" className="inline-flex min-w-0 items-center gap-1 font-medium hover:underline">
                        <span className="truncate">{src.title}</span>
                        <ExternalLink className="size-3 shrink-0 text-muted-foreground" aria-hidden />
                      </a>
                    ) : (
                      <span>{c.result(e.result)}</span>
                    )}
                  </p>
                  <blockquote className="mt-1.5 border-l-2 border-border pl-3 text-pretty">« {e.quote} »</blockquote>
                </li>
              );
            })}
          </ul>
        </>
      )}
      <p className="mt-3 text-sm text-muted-foreground">{c.humanConfirms}</p>
    </Section>
  );
}

function Claims({ r, claim, setClaim }: { r: Result; claim: number; setClaim: (n: number) => void }) {
  if (!r.claims?.length) return null;
  return (
    <Section title={c.claims}>
      <fieldset>
        <legend className="sr-only">{c.claimPick}</legend>
        <ul className="divide-y divide-border rounded-md border border-border bg-card">
          {r.claims.map((text, i) => (
            <li key={i}>
              <label className="flex cursor-pointer items-start gap-3 px-4 py-3">
                <input type="radio" name="claim" checked={claim === i} onChange={() => setClaim(i)} className="mt-1 size-4 accent-[var(--primary)]" />
                <span className="text-pretty">{text}</span>
              </label>
            </li>
          ))}
        </ul>
      </fieldset>
    </Section>
  );
}

function Signals({ r }: { r: Result }) {
  if (!r.claims?.length && !r.signals?.length) return null;
  return (
    <Section title={c.signals} note={c.signalsNote}>
      {r.signals?.length ? (
        <ul className="space-y-2">
          {r.signals.map((s, i) => (
            <li key={i} className="rounded-md border border-border bg-card p-3 text-sm">
              <p className="font-medium">{c.signal[s.type] ?? s.type}</p>
              <blockquote className="mt-1 border-l-2 border-border pl-3 text-pretty">« {s.quote} »</blockquote>
              {s.why && <p className="mt-1 text-pretty text-muted-foreground">{s.why}</p>}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">{c.noSignals}</p>
      )}
    </Section>
  );
}

function ImageFacts({ r }: { r: Result }) {
  const img = r.image;
  const camera = [img?.exif?.Make, img?.exif?.Model].filter(Boolean).join(" ");
  return (
    <Section title={c.image}>
      <div className="space-y-2 text-sm">
        {img &&
          (img.ai_markers?.length ? (
            <p className="flex items-start gap-1.5 font-medium text-verdict-misleading-ink">
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
              <a key={x.name} href={x.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-medium underline underline-offset-4">
                {x.name} <ExternalLink className="size-3" aria-hidden />
              </a>
            ))}
          </p>
        )}
      </div>
    </Section>
  );
}

function Elsewhere({ r, picked, toggle }: { r: Result; picked: Set<string>; toggle: (u: string) => void }) {
  if (!r.claims?.length && !r.results?.length) return null;
  const rows = r.results ?? [];
  return (
    <Section title={c.elsewhere} note={rows.length ? c.elsewhereNote : undefined}>
      {rows.length ? (
        <ul className="divide-y divide-border rounded-md border border-border bg-card">
          {rows.map((x) => (
            <li key={x.url} className="flex items-start gap-3 px-4 py-3">
              <input
                type="checkbox"
                checked={picked.has(x.url)}
                onChange={() => toggle(x.url)}
                aria-label={c.attach(x.title)}
                className="mt-1 size-4 shrink-0 accent-[var(--primary)]"
              />
              <div className="min-w-0 flex-1 text-sm">
                <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span className="font-display font-semibold tabular">[{x.n}]</span>
                  <span className="rounded-sm border border-border px-1.5 py-px text-xs font-medium">{c.kind[x.kind] ?? x.kind}</span>
                  <span className="text-muted-foreground">{host(x.url)}</span>
                </p>
                <a href={x.url} target="_blank" rel="noreferrer" className="mt-1 inline-flex max-w-full items-center gap-1 font-medium hover:underline">
                  <span className="truncate">{x.title}</span>
                  <ExternalLink className="size-3 shrink-0 text-muted-foreground" aria-hidden />
                </a>
                {x.snippet && <p className="mt-0.5 line-clamp-2 text-pretty text-muted-foreground">{x.snippet}</p>}
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">{c.noResults}</p>
      )}
    </Section>
  );
}
