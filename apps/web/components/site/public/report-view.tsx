"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { IconArrowRight, IconCheck, IconCircleNotch } from "@/lib/icons";
import { StepLine } from "@/components/flow/step-line";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { type Newsroom, myTips, publicApi, rememberTip } from "@/lib/public-api";
import { cn } from "@/lib/utils";

type Sent = { token: string; ref: string; newsroom?: { slug: string; name: string } | null; routed: string };
const ORIGINS = ["whatsapp", "facebook", "tiktok", "radio", "press", "other"] as const;
const field =
  "mt-1.5 w-full rounded-md border border-input bg-card px-3 text-base outline-none placeholder:text-muted-foreground focus-visible:border-foreground focus-visible:ring-2 focus-visible:ring-foreground/15";

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
    <div className="mx-auto grid max-w-[88rem] gap-12 px-4 pt-10 pb-20 lg:grid-cols-[minmax(0,1fr)_minmax(0,34rem)] lg:px-10 lg:pt-14">
      <div>
        <h1 id="report-title" className="page-title">
          {r.title}
        </h1>
        <p className="mt-4 max-w-[52ch] text-lg leading-relaxed text-pretty text-muted-foreground">{r.lead}</p>
        <StepLine className="mt-10 max-w-md" states={{ claim: done ? "done" : "active", evidence: "waiting", conclusion: "waiting" }} explain />
        {mine.length > 0 && (
          <section className="mt-12">
            <h2 className="font-display text-lg font-bold">{r.mine}</h2>
            <ul className="mt-2 border-t border-foreground">
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
        <div className="verdict-land self-start rounded-md border-2 border-foreground bg-card p-6 md:p-8" role="status">
          <p className="flex items-center gap-3 font-display text-3xl font-extrabold">
            <span className="grid size-10 place-items-center rounded-full bg-foreground text-background">
              <IconCheck className="size-5" aria-hidden />
            </span>
            {r.doneTitle}
          </p>
          <p className="mt-4 text-lg leading-relaxed text-pretty">{r.done(done.ref)}</p>
          {done.newsroom && <p className="mt-2 text-pretty">{(r.routed[done.routed] ?? r.routed.chosen)(done.newsroom.name)}</p>}
          <Button asChild variant="action" size="xl" className="mt-6">
            <Link href={`/suivi/${done.token}`}>
              {r.follow} <IconArrowRight aria-hidden />
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
        <form onSubmit={send} className="self-start rounded-md border border-border bg-card p-5 md:p-7" aria-labelledby="report-title">
          {rooms && !rooms.length ? (
            <p className="text-lg">{r.noNewsroom}</p>
          ) : (
            <div className="space-y-5">
              <div>
                <label htmlFor="tip-text" className="font-bold">
                  {r.text}
                </label>
                <textarea id="tip-text" className={cn(field, "resize-y py-2.5 leading-relaxed")} rows={5} value={text} onChange={(e) => setText(e.target.value)} required minLength={5} maxLength={4000} />
              </div>
              <div>
                <label htmlFor="tip-url" className="font-bold">
                  {r.url}
                </label>
                <input id="tip-url" type="url" className={cn(field, "h-11")} value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" aria-describedby="tip-url-hint" />
                <p id="tip-url-hint" className="mt-1 text-sm text-muted-foreground">
                  {r.urlHint}
                </p>
              </div>
              <fieldset>
                <legend className="font-bold">{r.origin}</legend>
                <div className="mt-2 flex flex-wrap gap-2">
                  {ORIGINS.map((o) => (
                    <label
                      key={o}
                      className={cn(
                        "inline-flex h-10 cursor-pointer items-center rounded-md border px-3.5 has-focus-visible:ring-2 has-focus-visible:ring-ring",
                        origin === o ? "border-foreground bg-foreground font-bold text-background" : "border-input bg-card hover:bg-accent",
                      )}
                    >
                      <input type="radio" name="origin" className="sr-only" checked={origin === o} onChange={() => setOrigin(o)} />
                      {t.origins[o]}
                    </label>
                  ))}
                </div>
              </fieldset>
              {!room && (
                <div>
                  <label htmlFor="tip-place" className="font-bold">
                    {r.place}
                  </label>
                  <input id="tip-place" className={cn(field, "h-11")} value={place} onChange={(e) => setPlace(e.target.value)} maxLength={120} aria-describedby="tip-place-hint" />
                  <p id="tip-place-hint" className="mt-1 text-sm text-muted-foreground">
                    {r.placeHint}
                  </p>
                </div>
              )}
              <div>
                <label htmlFor="tip-room" className="font-bold">
                  {r.newsroom}
                </label>
                <select id="tip-room" className={cn(field, "h-11")} value={room} onChange={(e) => setRoom(e.target.value)}>
                  <option value="">{r.auto}</option>
                  {rooms?.map((n) => (
                    <option key={n.slug} value={n.slug}>
                      {n.name}
                    </option>
                  ))}
                </select>
              </div>
              {typeof state === "object" && "error" in state && (
                <p className="font-bold text-destructive" role="alert">
                  {state.error}
                </p>
              )}
              <Button type="submit" variant="action" size="xl" className="w-full sm:w-auto" disabled={state === "sending"}>
                {state === "sending" ? <IconCircleNotch className="animate-spin" aria-hidden /> : null}
                {state === "sending" ? r.sending : r.submit}
                {state !== "sending" && <IconArrowRight aria-hidden />}
              </Button>
            </div>
          )}
        </form>
      )}
    </div>
  );
}
