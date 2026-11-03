"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { IconArrowRight, IconCheck, IconCircleNotch } from "@/lib/icons";
import { StepLine } from "@/components/flow/step-line";
import { Doodle, DoodleNote, Em, Lines, ORIGIN_ICON, ThemedSelect } from "@/components/site/public/kit";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { type Newsroom, myTips, publicApi, rememberTip } from "@/lib/public-api";
import { cn } from "@/lib/utils";

type Sent = { token: string; ref: string; newsroom?: { slug: string; name: string } | null; routed: string };
const ORIGINS = ["whatsapp", "facebook", "tiktok", "radio", "press", "other"] as const;
const field =
  "mt-2 w-full border border-input bg-card px-5 text-base text-foreground outline-none transition-[border-color,box-shadow] placeholder:text-muted-foreground focus-visible:border-foreground focus-visible:ring-3 focus-visible:ring-foreground/12";

/** The public tip form: a message heard or received goes to a newsroom's "to check" list. */
export function ReportView() {
  const t = useT();
  const r = t.site.pub.report;
  const params = useSearchParams();
  const [rooms, setRooms] = useState<Newsroom[] | null>(null);
  // Empty: Checky routes the tip to the newsroom where the rumour circulates (else the nearest).
  const [room, setRoom] = useState("");
  const [place, setPlace] = useState("");
  const [text, setText] = useState(params.get("texte") ?? "");
  const [url, setUrl] = useState("");
  const [origin, setOrigin] = useState<(typeof ORIGINS)[number]>("whatsapp");
  const [state, setState] = useState<"idle" | "sending" | Sent | { error: string }>("idle");
  // Read once on the client; the server renders none (this view only runs in the browser after Suspense).
  const [mine, setMine] = useState<ReturnType<typeof myTips>>(() => (typeof window === "undefined" ? [] : myTips()));

  useEffect(() => {
    publicApi<Newsroom[]>("/newsrooms")
      .then((list) => setRooms(list))
      .catch(() => setRooms([]));
  }, []);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    setState("sending");
    try {
      const res = await publicApi<Sent>("/tips", {
        method: "POST",
        body: JSON.stringify({ newsroom: room || null, place: place.trim() || null, text, url: url.trim() || null, origin }),
      });
      rememberTip({ ...res, title: text.slice(0, 120) });
      setMine(myTips());
      setState(res);
    } catch (err) {
      setState({ error: err instanceof ApiError && err.status === 429 ? r.tooMany : r.failed });
    }
  }

  const done = typeof state === "object" && "token" in state ? state : null;

  return (
    <div className="mx-auto grid max-w-[88rem] gap-14 px-4 pt-10 pb-24 lg:grid-cols-[minmax(0,1fr)_minmax(0,36rem)] lg:px-10 lg:pt-16">
      <div>
        <Lines id="report-title" className="pub-display" lines={t.look.report.hero.map((line, i) => <Em key={i} text={line} />)} />
        <p className="pub-lead rise mt-7" style={{ "--d": "0.25s" } as React.CSSProperties}>
          {r.lead}
        </p>
        <div className="rise mt-10" style={{ "--d": "0.35s" } as React.CSSProperties}>
          <StepLine className="max-w-md" states={{ claim: done ? "done" : "active", evidence: "waiting", conclusion: "waiting" }} explain />
        </div>
        {mine.length > 0 && (
          <section className="mt-12">
            <h2 className="font-display text-lg font-bold">{r.mine}</h2>
            <ul className="mt-3 border-t border-foreground">
              {mine.map((m) => (
                <li key={m.token}>
                  <Link href={`/suivi/${m.token}`} className="group flex items-baseline gap-3 border-b border-border py-3">
                    <span className="font-display font-bold tabular">{m.ref}</span>
                    <span className="min-w-0 truncate group-hover:underline">{m.title}</span>
                    <IconArrowRight className="ml-auto size-4 shrink-0 self-center text-muted-foreground" aria-hidden />
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>

      {done ? (
        <div className="verdict-land self-start rounded-[24px] border-2 border-foreground bg-card p-6 md:p-8" role="status">
          <p className="flex items-center gap-3 font-display text-3xl font-extrabold">
            <span className="grid size-10 place-items-center rounded-full bg-foreground text-background">
              <IconCheck className="size-5" aria-hidden />
            </span>
            {r.doneTitle}
          </p>
          <p className="mt-4 text-lg leading-relaxed text-pretty">{r.done(done.ref)}</p>
          {done.newsroom && <p className="mt-2 text-pretty">{(r.routed[done.routed] ?? r.routed.chosen)(done.newsroom.name)}</p>}
          <Button asChild variant="action" size="xl" className="group mt-6 rounded-full px-6">
            <Link href={`/suivi/${done.token}`}>
              {r.follow} <IconArrowRight className="transition-transform duration-300 group-hover:translate-x-1" aria-hidden />
            </Link>
          </Button>
          <button
            type="button"
            className="mt-5 block font-bold underline underline-offset-4"
            onClick={() => {
              setText("");
              setUrl("");
              setState("idle");
            }}
          >
            {r.another}
          </button>
        </div>
      ) : (
        <form onSubmit={send} className="rise relative self-start rounded-[24px] border border-border bg-card p-6 md:p-8" style={{ "--d": "0.2s" } as React.CSSProperties} aria-labelledby="report-title">
          {rooms && !rooms.length ? (
            <p className="text-lg">{r.noNewsroom}</p>
          ) : (
            <div className="space-y-6">
              <div className="relative">
                <DoodleNote className="-top-8 right-16" style={{ "--d": "0.9s" } as React.CSSProperties}>
                  {t.look.report.note}
                </DoodleNote>
                <Doodle className="-top-6 right-1 h-[58px] w-[66px] rotate-[62deg]" style={{ "--d": "1.1s" } as React.CSSProperties} />
                <label htmlFor="tip-text" className="font-bold">
                  {r.text}
                </label>
                <textarea id="tip-text" className={cn(field, "resize-y rounded-[20px] py-3.5 leading-relaxed")} rows={5} value={text} onChange={(e) => setText(e.target.value)} required minLength={5} maxLength={4000} />
              </div>
              <div>
                <label htmlFor="tip-url" className="font-bold">
                  {r.url}
                </label>
                <input id="tip-url" type="url" className={cn(field, "h-12 rounded-full")} value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" aria-describedby="tip-url-hint" />
                <p id="tip-url-hint" className="mt-1 text-sm text-muted-foreground">
                  {r.urlHint}
                </p>
              </div>
              <fieldset>
                <legend className="font-bold">{r.origin}</legend>
                <div className="mt-3 flex flex-wrap gap-2.5">
                  {ORIGINS.map((o) => {
                    const Glyph = ORIGIN_ICON[o];
                    return (
                      <label key={o} className="pub-icon-btn pub-tip pub-choice cursor-pointer" data-tip={t.origins[o]}>
                        <input type="radio" name="origin" className="sr-only" checked={origin === o} onChange={() => setOrigin(o)} />
                        <Glyph aria-hidden />
                        <span className="sr-only">{t.origins[o]}</span>
                      </label>
                    );
                  })}
                </div>
              </fieldset>
              {!room && (
                <div>
                  <label htmlFor="tip-place" className="font-bold">
                    {r.place}
                  </label>
                  <input id="tip-place" className={cn(field, "h-12 rounded-full")} value={place} onChange={(e) => setPlace(e.target.value)} maxLength={120} aria-describedby="tip-place-hint" />
                  <p id="tip-place-hint" className="mt-1 text-sm text-muted-foreground">
                    {r.placeHint}
                  </p>
                </div>
              )}
              <div>
                <span id="tip-room-label" className="font-bold">
                  {r.newsroom}
                </span>
                <ThemedSelect
                  id="tip-room"
                  className="mt-2 w-full"
                  value={room}
                  onValueChange={setRoom}
                  label={r.newsroom}
                  options={[{ value: "", label: r.auto }, ...(rooms ?? []).map((n) => ({ value: n.slug, label: n.name }))]}
                />
              </div>
              {typeof state === "object" && "error" in state && (
                <p className="font-bold text-destructive" role="alert">
                  {state.error}
                </p>
              )}
              <Button type="submit" variant="action" size="xl" className="group w-full rounded-full px-6 sm:w-auto" disabled={state === "sending"}>
                {state === "sending" ? <IconCircleNotch className="animate-spin" aria-hidden /> : null}
                {state === "sending" ? r.sending : r.submit}
                {state !== "sending" && <IconArrowRight className="transition-transform duration-300 group-hover:translate-x-1" aria-hidden />}
              </Button>
            </div>
          )}
        </form>
      )}
    </div>
  );
}
