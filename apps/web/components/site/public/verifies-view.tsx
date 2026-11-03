"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useSyncExternalStore } from "react";
import { CheckForm } from "@/components/site/public/check";
import { Doodle, DoodleNote, Em, Lines } from "@/components/site/public/kit";
import { VerdictList } from "@/components/site/public/verdicts";
import { VERDICT_META } from "@/components/claims/verdict";
import { useT } from "@/lib/i18n";
import { reducedMotion } from "@/lib/prefs";
import { cn } from "@/lib/utils";

/** « Est-ce déjà vérifié ? »: the check first, under the landing's rising title, then every
 *  published verdict as cards, filterable. */
export function VerifiesView() {
  const t = useT();
  const l = t.look.verifies;
  const c = t.publicLayer.check;
  return (
    <div className="mx-auto max-w-[88rem] px-4 pt-10 pb-24 lg:px-10 lg:pt-16">
      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-x-16 gap-y-10 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <div className="relative">
          <Lines id="check-title" className="pub-display" lines={l.hero.map((line, i) => <Em key={i} text={line} />)} />
          <p className="pub-lead rise mt-7" style={{ "--d": "0.25s" } as React.CSSProperties}>
            {c.lead}
          </p>
          <div className="rise relative mt-8 max-w-3xl" style={{ "--d": "0.35s" } as React.CSSProperties}>
            <DoodleNote className="-top-11 right-28" style={{ "--d": "0.9s" } as React.CSSProperties}>
              {l.note}
            </DoodleNote>
            <Doodle className="-top-14 right-4 h-[84px] w-[96px] rotate-[18deg]" style={{ "--d": "1.1s" } as React.CSSProperties} />
            <Suspense fallback={<CheckForm />}>
              <CheckFromLink />
            </Suspense>
          </div>
        </div>
        <Reels />
      </div>

      <section className="mt-24" aria-labelledby="archive-title">
        <hr className="mb-12 border-0 border-t-2 border-foreground" />
        <VerdictList
          limit={9}
          title={
            <h2 id="archive-title" className="pub-h2">
              <Em text={l.archive} />
            </h2>
          }
        />
      </section>
    </div>
  );
}

/** The landing's field opens this page with `?q=`: the check starts with that text. */
function CheckFromLink() {
  const q = useSearchParams().get("q") ?? "";
  return <CheckForm key={q} initialText={q.slice(0, 6000)} />;
}

const REELS = [
  { key: "market", src: "/site/landing/videos/marche-a.mp4", verdict: "misleading" },
  { key: "outage", src: "/site/landing/videos/reel-rocade-nuit.mp4", verdict: "false" },
  { key: "sky", src: "/site/landing/videos/delestage-satellite.mp4", verdict: "unverifiable" },
] as const;

/** Three muted clips of what circulates, tilted like the landing's picks (fictional examples). Not
 *  drawn on a phone, in Mode éco or with reduced motion: they are decoration, the check is the page. */
function Reels() {
  const t = useT();
  const l = t.look.verifies;
  const still = useSyncExternalStore(
    () => () => {},
    () => reducedMotion(),
    () => true,
  );
  if (still) return <div className="hidden lg:block" aria-hidden />;
  return (
    <figure className="reels rise hidden lg:block" style={{ "--d": "0.3s" } as React.CSSProperties}>
      <div className="reels-stage" aria-hidden>
        {REELS.map((r) => {
          const m = VERDICT_META[r.verdict];
          const Mark = m.icon;
          return (
            <div key={r.key} className="reel">
              <video src={r.src} autoPlay muted loop playsInline preload="metadata" />
              <span className={cn("reel-badge", m.soft, m.ink)}>
                <Mark className="size-4" />
                {t.verdict[r.verdict]}
              </span>
              <span className="reel-cap">{l.reel[r.key]}</span>
            </div>
          );
        })}
      </div>
      <figcaption className="mt-4 flex justify-between gap-4 text-sm text-muted-foreground">
        <span>{l.reels}</span>
        <a href="/site/landing/videos/CREDITS.md" target="_blank" rel="noreferrer" className="underline-offset-4 hover:text-foreground hover:underline">
          {l.credits}
        </a>
      </figcaption>
    </figure>
  );
}
