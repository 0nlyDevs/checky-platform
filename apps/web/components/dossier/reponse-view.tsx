"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Em, Lines } from "@/components/site/public/kit";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { t } from "@/lib/i18n/live";
import { IconCheck, IconCircleNotch } from "@/lib/icons";
import { publicApi } from "@/lib/public-api";
import { fmtWhen } from "./types";

const r = t.dossier.reponse;
const STANCES = ["confirms", "denies", "unknown"] as const;
type Stance = (typeof STANCES)[number];

type Reponse = {
  question: string;
  claim: string;
  ref: string | null;
  newsroom: string;
  contact: string | null;
  institution: string | null;
  asked_at: string | null;
  answered_at: string | null;
  stance: string | null;
};

const field =
  "mt-2 w-full border border-input bg-card px-5 text-base text-foreground outline-none transition-[border-color,box-shadow] placeholder:text-muted-foreground focus-visible:border-foreground focus-visible:ring-3 focus-visible:ring-foreground/12";

/**
 * The page a contact opens from the newsroom's message: no account, the claim and the question,
 * three answers and a sentence. The answer joins the dossier as a dated source under their name.
 */
export function ReponseView() {
  const { token } = useParams<{ token: string }>();
  const [ask, setAsk] = useState<Reponse | null | "missing">(null);
  const [stance, setStance] = useState<Stance | null>(null);
  const [text, setText] = useState("");
  const [name, setName] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | { error: string }>("idle");

  useEffect(() => {
    let live = true;
    publicApi<Reponse>(`/reponse/${token}`)
      .then((v) => {
        if (!live) return;
        setAsk(v);
        setName([v.contact, v.institution].filter(Boolean).join(", "));
      })
      .catch(() => live && setAsk("missing"));
    return () => {
      live = false;
    };
  }, [token]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!stance) return;
    setState("sending");
    try {
      const out = await publicApi<Reponse>(`/reponse/${token}`, { method: "POST", body: JSON.stringify({ stance, text: text.trim(), name: name.trim() }) });
      setAsk(out);
      setState("sent");
    } catch (err) {
      const code = err instanceof ApiError ? err.code : "";
      setState({ error: err instanceof ApiError && err.status === 429 ? r.tooMany : code === "already_answered" ? r.already(null) : r.failed });
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-4 pt-10 pb-24 lg:pt-16">
      <Lines className="pub-display" lines={t.look.reponse.hero.map((line, i) => <Em key={i} text={line} />)} />
      {ask === "missing" && <p className="mt-10 text-xl">{r.notFound}</p>}
      {!ask && <div aria-label={r.loading} className="mt-10 h-44 rounded-[24px] bg-muted" />}
      {ask && ask !== "missing" && (
        <div className="rise mt-8 space-y-8" style={{ "--d": "0.25s" } as React.CSSProperties}>
          <p className="pub-lead">{r.lead(ask.newsroom)}</p>

          <div className="rounded-[24px] border border-border bg-card p-6">
            <p className="flex justify-between gap-4 text-sm text-muted-foreground">
              <span>{r.claim}</span>
              {ask.ref && <span className="font-display font-bold text-foreground tabular">{ask.ref}</span>}
            </p>
            <p className="mt-2 font-display text-xl leading-snug font-bold text-pretty">« {ask.claim} »</p>
            <p className="mt-4 text-sm text-muted-foreground">
              {r.question}
              {ask.contact && ` · ${r.to([ask.contact, ask.institution].filter(Boolean).join(", "))}`}
            </p>
            <p className="mt-1 whitespace-pre-line text-pretty">{ask.question}</p>
          </div>

          {state === "sent" ? (
            <div role="status" className="verdict-land rounded-[24px] border-2 border-foreground bg-card p-6">
              <p className="flex items-center gap-2 font-display text-xl font-bold">
                <IconCheck className="size-5" aria-hidden />
                {r.thanks}
              </p>
              <p className="mt-2 text-pretty">{r.thanksLead(ask.newsroom)}</p>
            </div>
          ) : ask.answered_at ? (
            <p role="status" className="rounded-[24px] border border-border bg-card p-6">
              {r.already(fmtWhen(ask.answered_at))}
            </p>
          ) : (
            <form onSubmit={send} className="space-y-6">
              <fieldset>
                <legend className="font-bold">{r.stance}</legend>
                <div className="mt-3 grid gap-2.5 sm:grid-cols-3">
                  {STANCES.map((s) => (
                    <label
                      key={s}
                      className="flex min-h-12 cursor-pointer items-center justify-center gap-2.5 rounded-full border border-input bg-card px-4 py-2 text-center font-medium text-foreground transition-colors hover:border-foreground has-checked:border-primary has-checked:bg-primary has-checked:font-bold has-checked:text-primary-foreground has-focus-visible:ring-2 has-focus-visible:ring-ring has-focus-visible:ring-offset-2 has-focus-visible:ring-offset-background"
                    >
                      <input type="radio" name="stance" value={s} checked={stance === s} onChange={() => setStance(s)} className="sr-only" required />
                      {r.stances[s]}
                    </label>
                  ))}
                </div>
              </fieldset>
              <label className="block">
                <span className="font-bold">{r.text}</span>
                <span className="mt-0.5 block text-sm text-muted-foreground">{r.textHint}</span>
                <textarea value={text} onChange={(e) => setText(e.target.value)} required minLength={2} maxLength={4000} rows={5} className={`${field} resize-y rounded-[20px] py-3.5`} />
              </label>
              <label className="block">
                <span className="font-bold">{r.name}</span>
                <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={200} className={`${field} h-12 rounded-full`} />
              </label>
              {typeof state === "object" && (
                <p role="alert" className="font-medium">
                  {state.error}
                </p>
              )}
              <Button type="submit" variant="action" size="xl" className="w-full rounded-full px-6 sm:w-auto" disabled={state === "sending" || !stance}>
                {state === "sending" && <IconCircleNotch className="animate-spin" aria-hidden />}
                {state === "sending" ? r.sending : r.send}
              </Button>
              <p className="text-sm text-muted-foreground">{r.privacy}</p>
            </form>
          )}
        </div>
      )}
    </div>
  );
}
