"use client";

import { VerifiedBadge } from "@/components/verification/status";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Evidence, ShareActions, type SignedVerdict, VerdictBlock } from "@/components/site/public/public-verdict";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { useDay, useLang, useMoment, useT } from "@/lib/i18n";
import { IconArrowRight, IconArrowSquareOut, IconCircleNotch, IconInfo, IconPaperPlaneTilt, IconSealCheck } from "@/lib/icons";
import { isOffline } from "@/lib/offline";
import { publicApi, rememberTip, visitorCountry } from "@/lib/public-api";
import { tidy } from "@/lib/typo";

type Review = { publisher: string; url: string; rating: string | null; date: string | null; title: string };
type Diff = { op: "equal" | "insert" | "delete" | "replace"; a?: string; b?: string };
type Signal = { kind: string; quote: string };
type Fact = { kind: string; text: string; source: string | null; date: string | null; url: string | null; diff: Diff[]; level?: string | null; signals?: Signal[] };
type Verify = {
  status: "signed" | "external" | "facts" | "none";
  signed: SignedVerdict | null;
  external: Review[];
  known: Fact[];
  followed_since: string | null;
  followed_by: string | null;
  search_status: "done" | "unavailable" | "skipped";
};

const LONE_URL = /^https?:\/\/\S+$/i;

/**
 * « Est-ce déjà vérifié ? »: the visitor pastes what they received (or a link) and Checky looks in
 * three layers, in order: a verdict a newsroom signed, a fact-checker's published review, then what
 * is already known (the original text, an official figure, the first appearance, the tone). No
 * machine verdict and no percentage ever reach this page: only a newsroom's signed verdict, a
 * fact-checker's own words, or facts with their source and date.
 */
export function CheckForm({ id = "check", className, initialText = "" }: { id?: string; className?: string; initialText?: string }) {
  const t = useT();
  const c = t.publicLayer.check;
  const [text, setText] = useState(initialText);
  const [asked, setAsked] = useState("");
  const [result, setResult] = useState<Verify | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [waiting, setWaiting] = useState(false);
  const form = useRef<HTMLFormElement>(null);

  // Arriving with a text (the landing's field opens /verdicts?q=…): check it once, straight away.
  const asked0 = useRef(false);
  useEffect(() => {
    if (asked0.current || initialText.trim().length < 3) return;
    asked0.current = true;
    form.current?.requestSubmit();
  }, [initialText]);

  // Asked with no network: it runs by itself when the network returns.
  useEffect(() => {
    if (!waiting) return;
    const go = () => {
      setWaiting(false);
      form.current?.requestSubmit();
    };
    window.addEventListener("online", go);
    return () => window.removeEventListener("online", go);
  }, [waiting]);

  async function check(e: React.FormEvent) {
    e.preventDefault();
    const value = text.trim();
    // The action stays lit; an empty field just gets the focus back.
    if (value.length < 3) return document.getElementById(`${id}-text`)?.focus();
    if (isOffline()) {
      setWaiting(true);
      setResult(null);
      return setNote(t.offline.outbox.queued);
    }
    setBusy(true);
    setNote(null);
    setResult(null);
    try {
      const body = LONE_URL.test(value) ? { url: value } : { text: value.slice(0, 6000) };
      setResult(await publicApi<Verify>("/verify", { method: "POST", body: JSON.stringify({ ...body, country: visitorCountry() }) }));
      setAsked(value);
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 0;
      setNote(status === 429 ? c.tooMany : status === 503 || status === 504 ? c.busy : c.failed);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={className}>
      <form ref={form} onSubmit={check} aria-labelledby={`${id}-title`}>
        <label htmlFor={`${id}-text`} className="sr-only">
          {c.label}
        </label>
        <div className="pub-prompt">
          <textarea
            id={`${id}-text`}
            rows={3}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) e.currentTarget.form?.requestSubmit();
            }}
            placeholder={c.placeholder}
            maxLength={6000}
            className="block w-full resize-none bg-transparent px-6 pt-5 pb-2 text-lg leading-relaxed outline-none placeholder:text-muted-foreground"
          />
          <div className="flex items-center justify-end px-3 pb-3">
            <Button type="submit" variant="action" size="xl" disabled={busy} className="group rounded-full px-6">
              {busy && <IconCircleNotch className="animate-spin" aria-hidden />}
              {busy ? c.searching : c.submit}
              {!busy && <IconArrowRight className="transition-transform duration-300 group-hover:translate-x-1" aria-hidden />}
            </Button>
          </div>
        </div>
      </form>

      <div aria-live="polite" aria-busy={busy}>
        {busy && (
          // The three places Checky looks, in the order it looks; no fake progress.
          <ol className="mt-6 flex flex-wrap gap-x-5 gap-y-1 text-sm text-muted-foreground">
            {c.layers.map((layer, i) => (
              <li key={layer} className="flex items-center gap-1.5">
                <span className="font-display font-bold tabular text-foreground">{String(i + 1).padStart(2, "0")}</span>
                {layer}
              </li>
            ))}
          </ol>
        )}
        {note && (
          <p className="mt-6 text-lg" role="alert">
            {note}
          </p>
        )}
        {result && (
          <div className="mt-8">
            {result.status === "signed" && result.signed ? (
              <Signed v={result.signed} />
            ) : result.status === "external" && result.external.length ? (
              <External reviews={result.external} />
            ) : (
              <Known result={result} asked={asked} />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/** Case 1: a newsroom signed it. The solid block, who and when, the evidence with dates, share. */
function Signed({ v }: { v: SignedVerdict }) {
  const t = useT();
  const c = t.publicLayer.check.signed;
  const day = useDay();
  return (
    <div className="space-y-5">
      <div>
        <h2 className="font-display text-xl font-bold">{c.title}</h2>
        <p className="mt-1 text-pretty">«&nbsp;{tidy(v.title)}&nbsp;»</p>
      </div>
      <VerdictBlock v={v}>
        <p className="mt-4 font-bold text-foreground">
          {c.by(v.newsroom.name, day(v.signed_at ?? v.published_at))}
          {v.ref && <span className="font-normal tabular"> · {v.ref}</span>}
        </p>
        <VerifiedBadge className="mt-1" />
      </VerdictBlock>
      <Evidence v={v} />
      <ShareActions v={v} />
      <Link href={`/verdicts/${v.id}`} className="inline-flex items-center gap-1.5 font-bold underline underline-offset-4">
        {c.open} <IconArrowRight className="size-4" aria-hidden />
      </Link>
    </div>
  );
}

/** Case 2: a fact-checker already published a review. Relayed as theirs, in their own words. */
function External({ reviews }: { reviews: Review[] }) {
  const c = useT().publicLayer.check.external;
  const day = useDay();
  return (
    <div className="space-y-4">
      <h2 className="font-display text-xl font-bold">{c.title}</h2>
      <ul className="space-y-3">
        {reviews.map((r) => (
          <li key={r.url} className="arrive rounded-[20px] border border-input bg-card p-5 md:p-6">
            <p className="flex items-center gap-2 font-bold">
              <IconSealCheck className="size-5 shrink-0" aria-hidden />
              {c.by(r.publisher, r.date ? day(r.date) : null)}
            </p>
            <p className="mt-2 text-lg text-pretty">{r.title}</p>
            {r.rating && <p className="mt-2 font-display text-lg font-bold">{c.rating(r.rating)}</p>}
            <a href={r.url} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1.5 font-bold underline underline-offset-4">
              {c.read} <IconArrowSquareOut className="size-4" aria-hidden />
            </a>
          </li>
        ))}
      </ul>
      <p className="text-sm text-pretty text-muted-foreground">{c.relayed}</p>
      <p className="font-bold text-pretty">{c.noNeed}</p>
    </div>
  );
}

/** Cases 3 and 4: what is known, with source and date; no verdict yet; tell me; report it. */
function Known({ result, asked }: { result: Verify; asked: string }) {
  const t = useT();
  const c = t.publicLayer.check;
  const f = c.facts;
  const moment = useMoment();
  // The tone's signs get their own box, first: what the visitor can see for themselves.
  const tone = (result.known ?? []).find((x) => x.kind === "tone" && x.signals?.length);
  const known = (result.known ?? []).filter((x) => x !== tone);
  return (
    <div className="space-y-6">
      {tone && <Alert fact={tone} />}
      {known.length ? (
        <section>
          <h2 className="font-display text-xl font-bold">{f.title}</h2>
          <ol className="mt-2 border-t border-foreground">
            {known.map((fact, i) => (
              <FactRow key={`${fact.kind}-${i}`} fact={fact} index={i} />
            ))}
          </ol>
        </section>
      ) : (
        <section>
          <h2 className="font-display text-xl font-bold">{f.none}</h2>
          <p className="mt-1 max-w-[60ch] text-pretty text-muted-foreground">{f.noneLead}</p>
        </section>
      )}
      {result.search_status === "unavailable" && (
        <p className="flex items-start gap-2 text-sm text-pretty text-muted-foreground">
          <IconInfo className="mt-0.5 size-4 shrink-0" aria-hidden />
          {f.searchDown}
        </p>
      )}
      <div className="rounded-[20px] border-2 border-dashed border-foreground p-5">
        <p className="font-display text-lg font-bold">{f.noVerdict}</p>
        {result.followed_since && <p className="mt-1 text-pretty">{f.following(moment(result.followed_since), result.followed_by)}</p>}
      </div>
      <AskNewsroom text={asked} />
      <Notify text={asked} />
    </div>
  );
}

/** « Ce qui doit vous alerter »: each sign the tone lexicon found, named in the visitor's language,
 * with the words of the message it rests on. Found in code, no model; it says nothing of truth. */
function Alert({ fact }: { fact: Fact }) {
  const a = useT().publicLayer.check.facts.alert;
  return (
    <section aria-labelledby="alert-title" className="rounded-[20px] border border-input bg-card p-5 md:p-6">
      <h2 id="alert-title" className="font-display text-xl font-bold">
        {a.title}
      </h2>
      {fact.level && <p className="mt-1 font-bold">{a.level[fact.level] ?? fact.level}</p>}
      <ul className="mt-3 space-y-2">
        {(fact.signals ?? []).map((sg, i) => (
          <li key={`${sg.kind}-${i}`} className="flex flex-wrap items-baseline gap-x-2">
            <span className="text-sm font-bold">{a.kinds[sg.kind] ?? sg.kind}</span>
            <span className="quote text-lg">«&nbsp;{sg.quote}&nbsp;»</span>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-sm text-pretty text-muted-foreground">{a.lead}</p>
    </section>
  );
}

function FactRow({ fact, index }: { fact: Fact; index: number }) {
  const f = useT().publicLayer.check.facts;
  const day = useDay();
  const changed = (fact.diff ?? []).filter((d) => d.op !== "equal");
  return (
    <li className="arrive border-b border-border py-3" style={{ "--i": index } as React.CSSProperties}>
      <p className="text-sm font-bold">{f.kinds[fact.kind] ?? fact.kind}</p>
      <p className="mt-0.5 text-pretty">{fact.text}</p>
      {!!changed.length && (
        <div className="mt-2 text-sm">
          <p className="font-bold">{f.diff}</p>
          <dl className="mt-1 grid gap-x-3 gap-y-1 sm:grid-cols-[auto_minmax(0,1fr)]">
            {changed.slice(0, 4).map((d, i) => (
              <div key={i} className="contents">
                {d.a && (
                  <>
                    <dt className="text-muted-foreground">{f.removed}</dt>
                    <dd className="text-pretty line-through decoration-2">{d.a}</dd>
                  </>
                )}
                {d.b && (
                  <>
                    <dt className="text-muted-foreground">{f.added}</dt>
                    <dd className="font-bold text-pretty">{d.b}</dd>
                  </>
                )}
              </div>
            ))}
          </dl>
        </div>
      )}
      {(fact.source || fact.date) && (
        <p className="mt-1 text-sm text-muted-foreground">
          {fact.source}
          {fact.source && fact.date && " · "}
          {fact.date && <span className="tabular">{day(fact.date)}</span>}
          {fact.url && (
            <>
              {" · "}
              <a href={fact.url} target="_blank" rel="noreferrer" className="font-bold text-foreground underline underline-offset-4">
                {f.open}
              </a>
            </>
          )}
        </p>
      )}
    </li>
  );
}

/** « Me prévenir »: a phone number (or e-mail) to receive the verdict once a newsroom signs it. */
/** « Demander à une rédaction »: the message becomes a tip, routed to the newsroom where it
 * circulates (else the nearest), with a follow-up link; no account, no number. */
function AskNewsroom({ text }: { text: string }) {
  const t = useT();
  const a = t.publicLayer.check.ask;
  const [state, setState] = useState<"idle" | "sending" | "failed" | { token: string; ref: string; name: string }>("idle");

  async function ask() {
    setState("sending");
    try {
      const res = await publicApi<{ token: string; ref: string; newsroom?: { name: string } | null }>("/tips", {
        method: "POST",
        body: JSON.stringify({ text: text.slice(0, 4000), origin: "other", country: visitorCountry() }),
      });
      rememberTip({ token: res.token, ref: res.ref, title: text.slice(0, 120) });
      setState({ token: res.token, ref: res.ref, name: res.newsroom?.name ?? "" });
    } catch {
      setState("failed");
    }
  }

  return (
    <section aria-labelledby="ask-title" className="rounded-[20px] border border-input bg-card p-5">
      <h3 id="ask-title" className="font-display text-lg font-bold">
        {a.title}
      </h3>
      {typeof state === "object" ? (
        <div role="status" className="mt-1">
          <p className="text-pretty">{a.done(state.name, state.ref)}</p>
          <Link href={`/track/${state.token}`} className="mt-3 inline-flex h-11 items-center gap-2 rounded-full bg-primary px-5 font-bold text-primary-foreground hover:bg-primary-hover hover:text-primary-foreground">
            {a.follow} <IconArrowRight className="size-4" aria-hidden />
          </Link>
        </div>
      ) : (
        <>
          <p className="mt-1 text-pretty text-muted-foreground">{a.lead}</p>
          <Button type="button" variant="action" size="xl" className="mt-3 rounded-full px-6" onClick={ask} disabled={state === "sending"}>
            {state === "sending" ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconPaperPlaneTilt aria-hidden />}
            {state === "sending" ? a.sending : a.button}
          </Button>
          {state === "failed" && (
            <p className="mt-2 text-sm font-bold text-verdict-false-ink" role="alert">
              {a.failed}
            </p>
          )}
        </>
      )}
    </section>
  );
}

function Notify({ text }: { text: string }) {
  const t = useT();
  const n = t.publicLayer.check.notify;
  const lang = useLang();
  const [contact, setContact] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (contact.trim().length < 5) return setError(n.invalid);
    setBusy(true);
    setError(null);
    try {
      const res = await publicApi<{ masked: string; channel: "sms" | "email" }>("/notify", {
        method: "POST",
        body: JSON.stringify({ text: text.slice(0, 2000), contact: contact.trim(), lang }),
      });
      setDone(res.channel === "sms" ? n.sms(res.masked) : n.email);
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 0;
      setError(
        status === 422
          ? n.invalid
          : status === 409
            ? n.noNewsroom
            : status === 429
              ? t.publicLayer.check.tooMany
              : status === 503
                ? n.unavailable
                : n.failed,
      );
    } finally {
      setBusy(false);
    }
  }

  if (done)
    return (
      <p className="rounded-[20px] border border-foreground bg-card p-5 text-pretty" role="status">
        {done}
      </p>
    );
  return (
    <form onSubmit={send} className="rounded-[20px] border border-border bg-card p-5" aria-labelledby="notify-title">
      <h3 id="notify-title" className="font-display text-lg font-bold">
        {t.publicLayer.check.ask.sms}
      </h3>
      <p className="mt-1 text-pretty text-muted-foreground">{n.lead}</p>
      <div className="mt-3 flex flex-wrap items-end gap-2">
        <label className="block min-w-0 flex-1 basis-56">
          <span className="text-sm font-bold">{n.label}</span>
          <input
            type="text"
            inputMode="tel"
            autoComplete="tel"
            value={contact}
            onChange={(e) => setContact(e.target.value)}
            placeholder={n.placeholder}
            aria-invalid={!!error}
            aria-describedby="notify-privacy"
            className="mt-1 h-12 w-full rounded-full border border-input bg-background px-5 outline-none placeholder:text-muted-foreground focus-visible:border-foreground focus-visible:ring-2 focus-visible:ring-foreground/15"
          />
        </label>
        <Button type="submit" variant="outline" size="xl" disabled={busy} className="rounded-full px-6">
          {busy ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconPaperPlaneTilt aria-hidden />}
          {busy ? n.sending : n.submit}
        </Button>
      </div>
      {error && (
        <p className="mt-2 text-sm font-bold text-verdict-false-ink" role="alert">
          {error}
        </p>
      )}
      <p id="notify-privacy" className="mt-2 text-sm text-pretty text-muted-foreground">
        {n.privacy}
      </p>
    </form>
  );
}
