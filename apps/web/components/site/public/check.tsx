"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, LoaderCircle } from "lucide-react";
import { VerdictRow } from "@/components/site/public/verdicts";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { t } from "@/lib/i18n/fr";
import { type PublicVerdict, publicApi } from "@/lib/public-api";
import { cn } from "@/lib/utils";

const c = t.site.pub.check;

/**
 * "Is it already checked?": the visitor pastes what they received; the public assistant answers from
 * the published verdicts only and cites them, and the matching files are listed. Nothing found → the
 * message can be reported to a newsroom in one tap.
 */
export function CheckForm({ id = "check", className }: { id?: string; className?: string }) {
  const [text, setText] = useState("");
  const [hits, setHits] = useState<PublicVerdict[] | null>(null);
  const [answer, setAnswer] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function check(e: React.FormEvent) {
    e.preventDefault();
    // The action stays lit; an empty field just gets the focus back.
    if (text.trim().length < 3) return document.getElementById(`${id}-text`)?.focus();
    setBusy(true);
    setNote(null);
    try {
      const res = await publicApi<{ answer: string | null; verdicts: PublicVerdict[]; checked: boolean }>("/ask", {
        method: "POST",
        body: JSON.stringify({ question: text.slice(0, 600) }),
      });
      setHits(res.verdicts);
      setAnswer(res.answer);
      if (res.checked && !res.answer) setNote(c.busy);
    } catch (err) {
      setHits(null);
      setAnswer(null);
      setNote(err instanceof ApiError && err.status === 429 ? c.tooMany : c.none);
    } finally {
      setBusy(false);
    }
  }

  // [n] in the answer opens the matching file.
  const cite = (body: string) =>
    body.split(/(\[\d+\]|【\d+[^】]*】|\*\*[^*]+\*\*)/).map((part, i) => {
      if (/^\*\*[^*]+\*\*$/.test(part)) return <strong key={i}>{part.slice(2, -2)}</strong>;
      const n = Number(part.match(/\d+/)?.[0]);
      const v = /^(\[|【)/.test(part) && hits?.[n - 1];
      return v ? (
        <Link key={i} href={`/verifies/${v.id}`} className="font-bold text-action underline underline-offset-2">
          [{n}]
        </Link>
      ) : (
        part
      );
    });

  return (
    <div className={className}>
      <form onSubmit={check} aria-labelledby={`${id}-title`}>
        <label htmlFor={`${id}-text`} className="sr-only">
          {c.label}
        </label>
        <div className="rounded-md border border-input bg-card focus-within:border-foreground focus-within:ring-2 focus-within:ring-foreground/15">
          <textarea
            id={`${id}-text`}
            rows={3}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) e.currentTarget.form?.requestSubmit();
            }}
            placeholder={c.placeholder}
            maxLength={4000}
            className="block w-full resize-none bg-transparent px-4 pt-4 pb-2 text-lg leading-relaxed outline-none placeholder:text-muted-foreground"
          />
          <div className="flex items-center justify-end border-t border-border px-3 py-2.5">
            <Button type="submit" variant="action" size="xl" disabled={busy}>
              {busy && <LoaderCircle className="animate-spin" aria-hidden />}
              {busy ? c.searching : c.submit}
              {!busy && <ArrowRight aria-hidden />}
            </Button>
          </div>
        </div>
      </form>

      <div aria-live="polite">
        {note && !hits && <p className="mt-6 text-lg">{note}</p>}
        {hits && (
          <div className="mt-8 space-y-6">
            {answer && (
              <div className="verdict-land rounded-md bg-live p-5 text-live-foreground md:p-6">
                <p className="text-sm font-bold text-live-muted">{c.answer}</p>
                <p className="mt-2 max-w-[70ch] text-lg leading-relaxed text-pretty">{cite(answer)}</p>
              </div>
            )}
            {note && <p className="text-lg">{note}</p>}
            <div>
              <h2 className={cn("font-display text-xl font-bold", !hits.length && "text-pretty")}>{hits.length ? c.found(hits.length) : c.notChecked}</h2>
              {!!hits.length && (
                <ul className="mt-2 border-t border-foreground">
                  {hits.map((v, i) => (
                    <VerdictRow key={v.id} v={v} index={i} />
                  ))}
                </ul>
              )}
            </div>
            <Link
              href={`/signaler?texte=${encodeURIComponent(text.slice(0, 600))}`}
              className="inline-flex h-11 items-center gap-2 rounded-md border border-foreground px-4 font-bold hover:bg-accent"
            >
              {c.noneAction} <ArrowRight className="size-4" aria-hidden />
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
