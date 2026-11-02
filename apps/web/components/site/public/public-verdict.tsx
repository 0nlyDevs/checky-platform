"use client";

import { useEffect, useState } from "react";
import { VERDICT_META } from "@/components/claims/verdict";
import { Button } from "@/components/ui/button";
import { fr } from "@/lib/i18n/fr";
import { useDay, useLang, useT } from "@/lib/i18n";
import { IconBroadcast, IconCheck, IconLink, IconShareNetwork, IconSpeakerHigh, IconStop } from "@/lib/icons";
import { type PublicVerdict, publicApi } from "@/lib/public-api";
import { speak, stopSpeaking } from "@/lib/speak";
import { cn } from "@/lib/utils";

type Verdict = PublicVerdict["verdict"];

/** What `/public/verify` and `/public/verdicts/{id}` add to a published verdict: how solid the
 *  evidence is, in words only, and each source with its date. */
export type SignedVerdict = PublicVerdict & {
  confidence?: "eleve" | "moyen" | "faible" | null;
  evidence?: { title: string; date: string | null }[];
  signed_at?: string | null;
};

/** The verdict word with its icon, in the visitor's language (never colour alone). */
export function VerdictWord({ verdict, className }: { verdict: Verdict; className?: string }) {
  const t = useT();
  const m = VERDICT_META[verdict];
  const Icon = m.icon;
  return (
    <span className={cn("inline-flex flex-none items-center gap-1.5 rounded-sm px-2 py-0.5 text-sm font-bold whitespace-nowrap", m.soft, m.ink, className)}>
      <Icon className="size-3.5" aria-hidden />
      {t.verdict[verdict]}
    </span>
  );
}

/** The confirmed verdict as a solid block: the word, who confirmed it, why. */
export function VerdictBlock({ v, children, className }: { v: PublicVerdict; children?: React.ReactNode; className?: string }) {
  const t = useT();
  const m = VERDICT_META[v.verdict];
  const Icon = m.icon;
  return (
    <section className={cn("verdict-land rounded-md border-2 border-current p-5 md:p-7", m.soft, m.ink, className)} aria-label={t.site.pub.file.verdict}>
      <p className="flex items-center gap-3 font-display text-5xl font-extrabold tracking-tight md:text-6xl">
        <Icon className="size-10 shrink-0 md:size-12" aria-hidden />
        {t.verdict[v.verdict]}
      </p>
      <p className="mt-2 text-sm font-bold">{t.site.pub.file.confirmed}</p>
      {v.reason && <p className="mt-4 max-w-[62ch] text-xl leading-relaxed text-pretty text-foreground">{v.reason}</p>}
      {children}
    </section>
  );
}

/** « Solidité des preuves : élevée » and the sources with their dates. Words only: no percentage. */
export function Evidence({ v }: { v: SignedVerdict }) {
  const c = useT().publicLayer.check.signed;
  const day = useDay();
  const level = v.confidence ? c.levels[v.confidence] : null;
  return (
    <div className="space-y-4">
      {level && (
        <div>
          <p className="font-bold">{c.confidence(level)}</p>
          <p className="mt-0.5 text-sm text-pretty text-muted-foreground">{c.confidenceHint}</p>
        </div>
      )}
      {!!v.evidence?.length && (
        <div>
          <h3 className="font-display font-bold">{c.evidence}</h3>
          <ol className="mt-1.5 border-t border-border">
            {v.evidence.map((e, i) => (
              <li key={`${e.title}-${i}`} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5 border-b border-border py-2">
                <span className="min-w-0 text-pretty">{e.title}</span>
                <span className="shrink-0 text-sm text-muted-foreground tabular">{e.date ? day(e.date) : c.undated}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

/** WhatsApp, listen, copy the link. `primary` lights WhatsApp as the screen's one action. */
export function ShareActions({ v, primary = false }: { v: PublicVerdict; primary?: boolean }) {
  const t = useT();
  const lang = useLang();
  const p = t.site.pub.file;
  const [copied, setCopied] = useState(false);
  const [reading, setReading] = useState(false);
  useEffect(() => () => stopSpeaking(), []);

  const href = typeof window === "undefined" ? `/verifies/${v.id}` : `${location.origin}/verifies/${v.id}`;
  const listen = () => {
    if (reading) {
      stopSpeaking();
      setReading(false);
      return;
    }
    setReading(true);
    // The newsroom wrote in French: English pages read it in French, Malagasy pages in Malagasy.
    const voice = lang === "mg" ? "mg" : "fr";
    const word = voice === "mg" ? t.verdict[v.verdict] : fr.verdict[v.verdict];
    void speak(`${v.title}. ${word}. ${v.post ?? v.reason ?? ""}`, voice, () => setReading(false));
  };

  return (
    <div className="flex flex-wrap gap-2">
      <Button asChild variant={primary ? "action" : "outline"} size="xl">
        <a href={`https://wa.me/?text=${encodeURIComponent(p.whatsappText(v.title, t.verdict[v.verdict], href))}`} target="_blank" rel="noreferrer">
          <IconShareNetwork aria-hidden /> {p.whatsapp}
        </a>
      </Button>
      <Button variant="outline" size="xl" onClick={listen} aria-pressed={reading}>
        {reading ? <IconStop aria-hidden /> : <IconSpeakerHigh aria-hidden />}
        {reading ? p.stopListening : p.listen}
      </Button>
      <Button variant="outline" size="xl" onClick={() => navigator.clipboard?.writeText(href).then(() => setCopied(true))}>
        {copied ? <IconCheck aria-hidden /> : <IconLink aria-hidden />}
        {copied ? p.copied : p.share}
      </Button>
    </div>
  );
}

type Stop = { channel: string; place: string; region: string | null; status: string; at: string };
type Road = { truth: Stop[]; rumour_routes: number; truth_routes: number; covered: number; summary: string };

/**
 * « Où la correction est passée »: the places the newsroom sent the verdict back (radio, SMS,
 * posters…), from `/public/verdicts/{id}/trajet`. Nothing is shown when the road is empty or the
 * route is not there.
 */
export function Trajet({ id, className }: { id: string; className?: string }) {
  const t = useT();
  const l = t.publicLayer.verdict;
  const day = useDay();
  const [road, setRoad] = useState<Road | null>(null);

  useEffect(() => {
    let live = true;
    publicApi<Road>(`/verdicts/${id}/trajet`)
      .then((r) => live && Array.isArray(r?.truth) && setRoad(r))
      .catch(() => live && setRoad(null));
    return () => {
      live = false;
    };
  }, [id]);

  if (!road?.truth.length) return null;
  return (
    <section className={className} aria-labelledby={`trajet-${id}`}>
      <h2 id={`trajet-${id}`} className="font-display text-lg font-bold">
        {l.trajet}
      </h2>
      <p className="mt-0.5 text-sm text-pretty text-muted-foreground">{l.trajetLead}</p>
      <ol className="mt-2 border-t border-foreground">
        {road.truth.map((s, i) => (
          <li key={`${s.channel}-${s.place}-${i}`} className="arrive flex items-start gap-3 border-b border-border py-2.5" style={{ "--i": i } as React.CSSProperties}>
            <IconBroadcast className="mt-0.5 size-4 shrink-0" aria-hidden />
            <span className="min-w-0 flex-1">
              <span className="block font-bold text-pretty">
                {l.channels[s.channel] ?? fr.publicLayer.verdict.channels[s.channel] ?? s.channel} · {s.place}
              </span>
              <span className="block text-sm text-muted-foreground">
                {s.region && `${s.region} · `}
                {l.states[s.status] ?? s.status} · {day(s.at)}
              </span>
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
