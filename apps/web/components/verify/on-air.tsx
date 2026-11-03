"use client";

import type { Verdict } from "@checky/shared";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { VERDICT_META } from "@/components/claims/verdict";
import { Button } from "@/components/ui/button";
import { useDictation } from "@/components/verify/dictation";
import { api } from "@/lib/api";
import { useDay, useT } from "@/lib/i18n";
import { IconArrowCounterClockwise, IconArrowRight, IconArrowSquareOut, IconCheck, IconCircleNotch, IconCopy, IconMicrophone, IconStop } from "@/lib/icons";
import { cn } from "@/lib/utils";

type OnAirVerdict = {
  id: string;
  ref: string | null;
  title: string;
  verdict: Verdict;
  newsroom: string;
  own: boolean;
  published_at: string;
  signed_at: string | null;
  check_label: string | null;
  link: string;
  radio_line: string;
  radio_line_mg: string | null;
  mg_status: "relu" | "not_reread";
};
type OnAirOut = {
  status: "signed" | "followed" | "new";
  signed: OnAirVerdict[];
  own: {
    item_id: string;
    ref: string | null;
    title: string;
    status: string;
  } | null;
  followed_by: string | null;
  careful_line: string | null;
};
type Review = {
  publisher: string;
  url: string;
  rating: string | null;
  date: string | null;
  title: string;
};
type Reviews = { status: "done" | "unavailable"; reviews: Review[] };

/** A button that copies `text` and says so for two seconds. */
function CopyLine({ text, label, done }: { text: string; label: string; done: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      type="button"
      variant="action"
      size="xl"
      onClick={async () => {
        await navigator.clipboard?.writeText(text).catch(() => null);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }}
    >
      {copied ? <IconCheck aria-hidden /> : <IconCopy aria-hidden />}
      <span aria-live="polite">{copied ? done : label}</span>
    </Button>
  );
}

/**
 * « Avant l'antenne »: during a call-in show the radio journalist repeats the caller's claim (or
 * dictates it) and knows at once whether a newsroom signed a verdict on it, with the two sentences
 * to read on air. No signed verdict is never shown as « Faux »: only what is known, and a careful
 * line without a verdict word. The fact-checkers arrive a moment later, relayed as theirs.
 */
export function OnAir({ ws }: { ws: string }) {
  const T = useT();
  const o = T.verify.onAir;
  const router = useRouter();
  const [text, setText] = useState("");
  const [running, setRunning] = useState(false);
  const [asked, setAsked] = useState("");
  const [out, setOut] = useState<OnAirOut | null>(null);
  const [reviews, setReviews] = useState<Reviews | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tracking, setTracking] = useState(false);
  const dictation = useDictation((said) => setText((prev) => (prev.trim() ? `${prev.trim()} ${said}` : said)));

  async function run() {
    const said = text.trim();
    if (said.length < 3 || running) return document.getElementById("onair-input")?.focus();
    setRunning(true);
    setAsked(said);
    setOut(null);
    setReviews(null);
    setError(null);
    const body = JSON.stringify({ text: said });
    // the signed verdicts come from the database at once; the fact-checkers follow
    void api<Reviews>(`/workspaces/${ws}/avant-antenne/fact-checks`, {
      method: "POST",
      body,
    })
      .then(setReviews)
      .catch(() => setReviews({ status: "unavailable", reviews: [] }));
    try {
      setOut(
        await api<OnAirOut>(`/workspaces/${ws}/avant-antenne`, {
          method: "POST",
          body,
        }),
      );
    } catch {
      setError(o.failed);
    } finally {
      setRunning(false);
    }
  }

  async function track() {
    setTracking(true);
    try {
      const act = (b: Record<string, unknown>) =>
        api<{ item_id: string }>(`/workspaces/${ws}/copilot/act`, {
          method: "POST",
          body: JSON.stringify(b),
        });
      const made = await act({
        kind: "create_claim",
        title: asked.slice(0, 300),
        body: asked.slice(0, 4000),
        origin: "radio",
      });
      for (const r of reviews?.reviews ?? [])
        await act({
          kind: "attach_link",
          item_id: made.item_id,
          url: r.url,
        }).catch(() => null);
      router.push(`/w/${ws}/claims/${made.item_id}` as never);
    } catch {
      setError(o.trackFailed);
      setTracking(false);
    }
  }

  function reset() {
    setText("");
    setAsked("");
    setOut(null);
    setReviews(null);
    setError(null);
    document.getElementById("onair-input")?.focus();
  }

  const best = out?.signed[0];
  return (
    <>
      <h1 className="page-title max-w-3xl">{o.title}</h1>
      <p className="mt-3 max-w-[62ch] text-lg text-pretty text-muted-foreground">{o.lead}</p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void run();
        }}
        className="mt-7 max-w-4xl"
      >
        <label htmlFor="onair-input" className="font-display text-sm font-bold">
          {o.field}
        </label>
        <div className="mt-2 rounded-md border border-input bg-card focus-within:border-foreground focus-within:ring-2 focus-within:ring-foreground/15">
          <textarea
            id="onair-input"
            rows={2}
            maxLength={2000}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                e.currentTarget.form?.requestSubmit();
              }
            }}
            placeholder={o.placeholder}
            className="block w-full resize-none bg-transparent px-4 pt-4 pb-2 text-xl leading-relaxed outline-none placeholder:text-muted-foreground"
          />
          <div className="flex flex-wrap items-center gap-2 border-t border-border px-3 py-2.5">
            {dictation.can && (
              <>
                <Button
                  type="button"
                  variant="outline"
                  size="xl"
                  onClick={dictation.toggle}
                  disabled={dictation.state === "transcribing"}
                  className={cn(dictation.state === "recording" && "bg-verdict-false-soft text-verdict-false-ink")}
                >
                  {dictation.state === "recording" ? (
                    <IconStop aria-hidden />
                  ) : dictation.state === "transcribing" ? (
                    <IconCircleNotch className="animate-spin" aria-hidden />
                  ) : (
                    <IconMicrophone aria-hidden />
                  )}
                  {dictation.state === "recording" ? T.verify.stopDictate : dictation.state === "transcribing" ? T.verify.transcribing : o.dictate}
                </Button>
              </>
            )}
            {dictation.error && <span className="text-sm text-verdict-false-ink">{dictation.error}</span>}
            <Button type="submit" variant="action" size="xl" className="ml-auto" disabled={running}>
              {running && <IconCircleNotch className="animate-spin" aria-hidden />}
              {running ? o.running : o.submit}
              {!running && <IconArrowRight aria-hidden />}
            </Button>
          </div>
        </div>
      </form>

      <div className="mt-8 max-w-4xl space-y-8" aria-live="polite">
        {error && (
          <p role="alert" className="rounded-md bg-verdict-false-soft px-4 py-3 text-verdict-false-ink">
            {error}
          </p>
        )}
        {best && <Signed v={best} />}
        {out && !best && (
          <section className="rounded-md border border-border bg-card p-5 md:p-7">
            <h2 className="font-display text-3xl font-bold md:text-4xl">{o.notYet}</h2>
            <p className="mt-2 text-lg text-pretty">{o.notYetLead}</p>
            {out.own && (
              <p className="mt-3 flex flex-wrap items-center gap-x-3 font-bold">
                {o.ownFollows(out.own.ref ?? "")}
                <Link href={`/w/${ws}/claims/${out.own.item_id}` as never} className="underline underline-offset-4">
                  {o.openDossier} <IconArrowRight className="inline size-4" aria-hidden />
                </Link>
              </p>
            )}
            {out.followed_by && <p className="mt-3 font-bold">{o.otherFollows(out.followed_by)}</p>}
            {out.careful_line && (
              <div className="mt-6 border-t border-border pt-5">
                <h3 className="font-display text-sm font-bold">{o.careful}</h3>
                <p className="text-sm text-muted-foreground">{o.carefulHelp}</p>
                <p className="mt-3 text-2xl leading-snug font-bold text-pretty md:text-3xl">{o.carefulLine[out.status === "followed" ? "followed" : "new"]}</p>
                <div className="mt-4">
                  <CopyLine text={o.carefulLine[out.status === "followed" ? "followed" : "new"]} label={o.copyCareful} done={o.copied} />
                </div>
              </div>
            )}
          </section>
        )}
        {out && out.signed.length > 1 && (
          <section>
            <h2 className="font-display text-lg font-bold">{o.others}</h2>
            <ul className="mt-3 divide-y divide-border rounded-md border border-border bg-card">
              {out.signed.slice(1).map((x) => {
                const m = VERDICT_META[x.verdict];
                const Icon = m.icon;
                return (
                  <li key={x.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                    <span className={cn("inline-flex items-center gap-1.5 rounded-sm px-2 py-0.5 text-sm font-bold", m.fill, m.on)}>
                      <Icon className="size-3.5" aria-hidden />
                      {T.verdict[x.verdict]}
                    </span>
                    <span className="min-w-0 flex-1 text-pretty">{x.title}</span>
                    <span className="text-sm text-muted-foreground">{x.own ? o.yours : x.newsroom}</span>
                  </li>
                );
              })}
            </ul>
          </section>
        )}
        {(out || reviews) && <Checkers reviews={reviews} />}
        {out && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border pt-4">
            {!best && !out.own && (
              <Button variant="outline" size="xl" onClick={() => void track()} disabled={tracking}>
                {tracking && <IconCircleNotch className="animate-spin" aria-hidden />}
                {tracking ? o.tracking : o.track}
              </Button>
            )}
            <Button variant="ghost" className="ml-auto h-10" onClick={reset}>
              <IconArrowCounterClockwise aria-hidden />
              {o.again}
            </Button>
          </div>
        )}
      </div>
    </>
  );
}

/** The signed verdict in large type, and its radio line in French or (once reread) Malagasy. */
function Signed({ v }: { v: OnAirVerdict }) {
  const T = useT();
  const o = T.verify.onAir;
  const day = useDay();
  const m = VERDICT_META[v.verdict];
  const Icon = m.icon;
  const [lineLang, setLineLang] = useState<"fr" | "mg">("fr");
  const line = lineLang === "mg" ? v.radio_line_mg : v.radio_line;
  return (
    <section className="rounded-md border-2 border-foreground bg-card p-5 md:p-7">
      <h2 className="font-display text-sm font-bold">{o.already}</h2>
      <p className={cn("mt-2 inline-flex items-center gap-3 rounded-md px-4 py-2 text-4xl font-bold md:text-5xl", m.fill, m.on)}>
        <Icon className="size-9 md:size-11" aria-hidden />
        {T.verdict[v.verdict]}
      </p>
      <p className="mt-3 text-lg text-pretty">
        {o.by(v.own ? o.yours : v.newsroom, day(v.signed_at ?? v.published_at))}
        {v.check_label && <span className="ml-2 font-display font-bold tabular">· {v.check_label}</span>}
      </p>
      <p className="mt-1 text-pretty text-muted-foreground">{T.common.quote(v.title)}</p>
      <a href={v.link} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 text-sm font-bold underline underline-offset-4">
        {o.openVerdict} <IconArrowSquareOut className="size-3.5" aria-hidden />
      </a>

      <div className="mt-6 border-t border-border pt-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="font-display text-sm font-bold">{o.line}</h3>
            <p className="text-sm text-muted-foreground">{o.lineHelp}</p>
          </div>
          <div role="radiogroup" aria-label={o.lineLang} className="inline-flex rounded-md border border-border p-0.5">
            {(["fr", "mg"] as const).map((l) => (
              <button
                key={l}
                type="button"
                role="radio"
                aria-checked={lineLang === l}
                onClick={() => setLineLang(l)}
                className={cn(
                  "rounded-[3px] px-3 py-1.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  lineLang === l ? "bg-foreground font-bold text-background" : "text-muted-foreground",
                )}
              >
                {o.langs[l]}
              </button>
            ))}
          </div>
        </div>
        {line ? (
          <>
            <p lang={lineLang === "mg" ? "mg" : "fr"} className="mt-4 text-2xl leading-snug font-bold text-pretty md:text-3xl">
              {line}
            </p>
            <div className="mt-4">
              <CopyLine text={line} label={o.copy} done={o.copied} />
            </div>
          </>
        ) : (
          <p role="note" className="mt-4 rounded-md bg-muted p-4 text-pretty">
            {o.mgMissing}
          </p>
        )}
      </div>
    </section>
  );
}

/** The fact-checkers' reviews, relayed as theirs: their name, their date, their own words. */
function Checkers({ reviews }: { reviews: Reviews | null }) {
  const T = useT();
  const o = T.verify.onAir;
  const day = useDay();
  return (
    <section>
      <h2 className="font-display text-lg font-bold">{o.checkers}</h2>
      {!reviews ? (
        <p className="mt-2 flex items-center gap-2 text-muted-foreground">
          <IconCircleNotch className="size-4 animate-spin" aria-hidden />
          {o.checkersLoading}
        </p>
      ) : reviews.status === "unavailable" ? (
        <p className="mt-2 text-muted-foreground">{o.checkersDown}</p>
      ) : !reviews.reviews.length ? (
        <p className="mt-2 text-muted-foreground">{o.checkersNone}</p>
      ) : (
        <ul className="mt-3 space-y-3">
          {reviews.reviews.map((r) => (
            <li key={r.url} className="rounded-md border border-border bg-card p-4">
              <p className="font-bold">{o.checkedBy(r.publisher, r.date ? day(r.date) : "")}</p>
              {r.rating && (
                <p className="mt-1">
                  <span className="text-muted-foreground">{o.theirWords} </span>
                  <span className="font-bold">{T.common.quote(r.rating)}</span>
                </p>
              )}
              <a href={r.url} target="_blank" rel="noreferrer" className="mt-1.5 inline-flex items-center gap-1 text-pretty underline underline-offset-4">
                {r.title} <IconArrowSquareOut className="size-3.5 shrink-0" aria-hidden />
              </a>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
