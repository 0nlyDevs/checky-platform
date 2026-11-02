"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, Check, Link2, Share2, Square, Volume2 } from "lucide-react";
import { VERDICT_META } from "@/components/claims/verdict";
import { StepLine } from "@/components/flow/step-line";
import { day } from "@/components/site/public/verdicts";
import { Button } from "@/components/ui/button";
import { t } from "@/lib/i18n/fr";
import { type PublicVerdict, publicApi } from "@/lib/public-api";
import { speak, stopSpeaking } from "@/lib/speak";
import { tidy } from "@/lib/typo";
import { cn } from "@/lib/utils";

const p = t.site.pub.file;

/** The confirmed verdict as a visitor needs it: the answer first, why, where it was checked, then share. */
export function VerdictCard({ v }: { v: PublicVerdict }) {
  const m = VERDICT_META[v.verdict];
  const Icon = m.icon;
  return (
    <section className={cn("verdict-land rounded-md border-2 border-current p-5 md:p-7", m.soft, m.ink)} aria-label={p.verdict}>
      <p className="flex items-center gap-3 font-display text-5xl font-extrabold tracking-tight md:text-6xl">
        <Icon className="size-10 shrink-0 md:size-12" strokeWidth={2.4} aria-hidden />
        {m.label}
      </p>
      <p className="mt-2 text-sm font-bold">{p.confirmed}</p>
      {v.reason && <p className="mt-4 max-w-[62ch] text-xl leading-relaxed text-pretty text-foreground">{v.reason}</p>}
    </section>
  );
}

/** One published verdict, at its own shareable address. */
export function VerdictPage() {
  const { id } = useParams<{ id: string }>();
  const [v, setV] = useState<PublicVerdict | null | "missing">(null);
  const [copied, setCopied] = useState(false);
  const [reading, setReading] = useState(false);

  useEffect(() => {
    publicApi<PublicVerdict>(`/verdicts/${id}`).then(setV).catch(() => setV("missing"));
  }, [id]);
  useEffect(() => () => stopSpeaking(), []);

  if (v === "missing")
    return (
      <Shell>
        <p className="mt-8 text-xl">{p.notFound}</p>
      </Shell>
    );
  if (!v)
    return (
      <Shell>
        <div className="mt-8 h-12 w-2/3 animate-pulse rounded-md bg-muted" />
        <div className="mt-6 h-48 animate-pulse rounded-md bg-muted" />
      </Shell>
    );

  const label = t.verdict[v.verdict];
  const listen = () => {
    if (reading) {
      stopSpeaking();
      setReading(false);
      return;
    }
    setReading(true);
    void speak(`${v.title}. ${label}. ${v.post ?? v.reason ?? ""}`, "fr", () => setReading(false));
  };
  const href = typeof window === "undefined" ? "" : location.href;

  return (
    <Shell>
      <h1 className="mt-6 max-w-[30ch] font-display text-[1.7rem] leading-[1.1] font-extrabold tracking-tight text-pretty md:mt-8 md:text-[2.6rem]">«&nbsp;{tidy(v.title)}&nbsp;»</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        {p.by(v.newsroom.name)}
        {v.ref && <span className="tabular"> · {v.ref}</span>}
      </p>

      <div className="mt-6 grid gap-10 md:mt-8 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="min-w-0">
          <VerdictCard v={v} />
          <div className="mt-4 flex flex-wrap gap-2">
            <Button asChild variant="action" size="xl">
              <a href={`https://wa.me/?text=${encodeURIComponent(p.whatsappText(v.title, label, href))}`} target="_blank" rel="noreferrer">
                <Share2 aria-hidden /> {p.whatsapp}
              </a>
            </Button>
            <Button variant="outline" size="xl" onClick={listen} aria-pressed={reading}>
              {reading ? <Square aria-hidden /> : <Volume2 aria-hidden />}
              {reading ? p.stopListening : p.listen}
            </Button>
            <Button
              variant="outline"
              size="xl"
              onClick={() => navigator.clipboard?.writeText(location.href).then(() => setCopied(true))}
            >
              {copied ? <Check aria-hidden /> : <Link2 aria-hidden />}
              {copied ? p.copied : p.share}
            </Button>
          </div>

          {v.post && (
            <section className="mt-10">
              <h2 className="font-display text-lg font-bold">{p.post}</h2>
              <p className="mt-2 max-w-[70ch] text-lg leading-relaxed text-pretty">{v.post}</p>
            </section>
          )}

          <section className="mt-10">
            <h2 className="font-display text-lg font-bold">{p.sources}</h2>
            {v.sources.length ? (
              <ol className="mt-2 border-t border-foreground">
                {v.sources.map((s, i) => (
                  <li key={s} className="arrive flex gap-4 border-b border-border py-3" style={{ "--i": i } as React.CSSProperties}>
                    <span className="font-display font-bold text-muted-foreground tabular">{String(i + 1).padStart(2, "0")}</span>
                    <span className="min-w-0 text-pretty">{s}</span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="mt-2 text-muted-foreground">{p.noSources}</p>
            )}
          </section>
        </div>

        <aside className="lg:border-l lg:border-border lg:pl-8">
          <h2 className="sr-only">{t.flow.label}</h2>
          <StepLine
            states={{ claim: "done", evidence: "done", conclusion: "done" }}
            notes={{
              claim: v.first_seen_at ? p.seenOn(day(v.first_seen_at), v.origin ? (t.origins[v.origin as keyof typeof t.origins] ?? null) : null) : undefined,
              evidence: v.sources.length ? p.sourcesSeen(v.sources.length) : p.noSources,
              conclusion: p.publishedBy(day(v.published_at), v.newsroom.name),
            }}
          />
          <div className="mt-8 rounded-md border border-border bg-card p-4">
            <p className="text-pretty">{p.wrong}</p>
            <Link
              href={`/signaler?texte=${encodeURIComponent(v.title)}`}
              className="mt-2 inline-flex items-center gap-1.5 font-bold underline underline-offset-4"
            >
              {p.wrongAction} <ArrowRight className="size-4" aria-hidden />
            </Link>
          </div>
        </aside>
      </div>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-[88rem] px-4 pt-8 pb-20 lg:px-10">
      <Link href="/verifies" className="inline-flex items-center gap-1.5 text-sm font-bold hover:underline">
        <ArrowLeft className="size-4" aria-hidden /> {p.back}
      </Link>
      {children}
    </div>
  );
}
