"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import { t } from "@/lib/i18n/fr";
import { type Newsroom, myTips, publicApi, rememberTip } from "@/lib/public-api";

const r = t.site.pub.report;
const ORIGINS = ["whatsapp", "facebook", "tiktok", "radio", "press", "other"] as const;

/** The public tip form: a message heard or received goes to a newsroom's "to check" list. */
export function ReportView() {
  const params = useSearchParams();
  const [rooms, setRooms] = useState<Newsroom[] | null>(null);
  const [room, setRoom] = useState("");
  const [text, setText] = useState(params.get("texte") ?? "");
  const [url, setUrl] = useState("");
  const [origin, setOrigin] = useState<(typeof ORIGINS)[number]>("whatsapp");
  const [state, setState] = useState<"idle" | "sending" | { token: string; ref: string } | { error: string }>("idle");
  // Read once on the client; the server renders none (this view only runs in the browser after Suspense).
  const [mine, setMine] = useState<ReturnType<typeof myTips>>(() => (typeof window === "undefined" ? [] : myTips()));

  useEffect(() => {
    publicApi<Newsroom[]>("/newsrooms")
      .then((list) => {
        setRooms(list);
        if (list[0]) setRoom(list[0].slug);
      })
      .catch(() => setRooms([]));
  }, []);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    setState("sending");
    try {
      const res = await publicApi<{ token: string; ref: string }>("/tips", {
        method: "POST",
        body: JSON.stringify({ newsroom: room, text, url: url.trim() || null, origin }),
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
    <section className="frame-x pt-[clamp(32px,6vw,72px)] pb-[clamp(72px,9vw,130px)]" aria-labelledby="report-title">
      <div className="grid gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,32rem)]">
        <div>
          <h1 id="report-title" className="disp text-[clamp(52px,8vw,128px)] leading-[0.88]">
            {r.title}
          </h1>
          <p className="mt-6 max-w-[44ch] text-xl leading-relaxed">{r.lead}</p>
          {mine.length > 0 && (
            <div className="mt-10">
              <h2 className="typed text-[15px] text-ink-soft">{r.mine}</h2>
              <ul className="mt-2 space-y-2">
                {mine.map((m) => (
                  <li key={m.token}>
                    <Link href={`/suivi/${m.token}`} className="ulink text-lg">
                      <span className="tabular font-semibold">{m.ref}</span> · {m.title}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {done ? (
          <div className="dossier-card" role="status">
            <p className="t">{r.doneTitle}</p>
            <p className="text-lg leading-relaxed">{r.done(done.ref)}</p>
            <Link href={`/suivi/${done.token}`} className="tab-btn">
              {r.follow} <span className="arr" aria-hidden>→</span>
            </Link>
            <button type="button" className="ulink mt-6 block text-base" onClick={() => { setText(""); setUrl(""); setState("idle"); }}>
              {r.another}
            </button>
            <span className="stamp" data-on="true" aria-hidden data-label={r.stamp} />
          </div>
        ) : (
          <form onSubmit={send} className="dossier-card" aria-labelledby="report-title">
            {rooms && !rooms.length ? (
              <p className="text-lg">{r.noNewsroom}</p>
            ) : (
              <>
                <label htmlFor="tip-room" className="!mt-0">{r.newsroom}</label>
                <select id="tip-room" className="pub-input" value={room} onChange={(e) => setRoom(e.target.value)} required>
                  {rooms?.map((n) => (
                    <option key={n.slug} value={n.slug}>{n.name}</option>
                  ))}
                </select>
                <label htmlFor="tip-text">{r.text}</label>
                <textarea id="tip-text" className="pub-input" rows={5} value={text} onChange={(e) => setText(e.target.value)} required minLength={5} maxLength={4000} />
                <label htmlFor="tip-url">{r.url}</label>
                <input id="tip-url" type="url" className="pub-input" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" aria-describedby="tip-url-hint" />
                <p id="tip-url-hint" className="mt-1 text-[14px] text-ink-soft">{r.urlHint}</p>
                <fieldset>
                  <legend>{r.origin}</legend>
                  <div className="choice">
                    {ORIGINS.map((o) => (
                      <label key={o}>
                        <input type="radio" name="origin" checked={origin === o} onChange={() => setOrigin(o)} /> {t.origins[o]}
                      </label>
                    ))}
                  </div>
                </fieldset>
                {typeof state === "object" && "error" in state && (
                  <p className="mt-4 font-medium text-alarm-ink" role="alert">{state.error}</p>
                )}
                <button type="submit" className="tab-btn" disabled={state === "sending" || !room}>
                  {state === "sending" ? r.sending : r.submit} <span className="arr" aria-hidden>→</span>
                </button>
              </>
            )}
          </form>
        )}
      </div>
    </section>
  );
}
