import type { Metadata } from "next";
import Link from "next/link";
import { IconArrowRight, IconCheck } from "@/lib/icons";
import { STEPS } from "@/components/flow/step-line";
import { CheckForm } from "@/components/site/public/check";
import { Specimen } from "@/components/site/public/specimen";
import { VerdictList } from "@/components/site/public/verdicts";
import { Button } from "@/components/ui/button";
import { brand } from "@/lib/brand";
import { t } from "@/lib/i18n/fr";

export const metadata: Metadata = {
  title: { absolute: `${brand.name} · ${t.site.metaTitle}` },
  description: t.site.metaDescription,
};

const s = t.site;
const h = s.home;
const [doubt, ...rest] = h.title.split("? ");

/** The public home: check a message first; then how a rumour is verified, recent verdicts, and newsrooms. */
export default function HomePage() {
  return (
    <>
      <section className="mx-auto grid max-w-[88rem] gap-x-16 gap-y-12 px-4 pt-10 pb-16 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] lg:px-10 lg:pt-12 lg:pb-24" aria-labelledby="home-title">
        <div>
          <h1 id="home-title" className="font-display text-[clamp(2.5rem,1.4rem+3.6vw,4.6rem)] leading-[0.95] font-extrabold tracking-[-0.03em]">
            <span className="block">{doubt.trim()}&nbsp;?</span>
            <mark className="signal-mark" style={{ "--i": 1 } as React.CSSProperties}>
              {rest.join("? ")}
            </mark>
          </h1>
          <p className="mt-5 max-w-[50ch] text-lg leading-relaxed text-pretty text-muted-foreground md:text-xl">{h.lead}</p>
          <CheckForm id="home" className="mt-8" />
          <p className="mt-4 text-sm font-bold" lang="mg">
            {h.saying}
          </p>
          <section className="mt-8" aria-labelledby="recent-title">
            <div className="flex items-baseline justify-between gap-4">
              <h2 id="recent-title" className="font-display text-lg font-bold">
                {h.recent}
              </h2>
              <Link href="/verifies" className="inline-flex items-center gap-1.5 text-sm font-bold underline underline-offset-4">
                {h.all} <IconArrowRight className="size-4" aria-hidden />
              </Link>
            </div>
            <div className="mt-2">
              <VerdictList limit={3} compact />
            </div>
          </section>
        </div>
        <div className="lg:pt-4">
          <Specimen />
        </div>
      </section>

      <section className="border-y border-border bg-card" aria-labelledby="how-title">
        <div className="mx-auto max-w-[88rem] px-4 py-14 lg:px-10 lg:py-20">
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)] lg:gap-16">
            <div>
              <h2 id="how-title" className="font-display text-3xl font-extrabold tracking-tight md:text-4xl">
                {h.how}
              </h2>
              <p className="mt-3 max-w-[46ch] text-lg text-pretty text-muted-foreground">{h.howLead}</p>
            </div>
            <ol className="grid gap-px overflow-hidden rounded-md border border-border bg-border md:grid-cols-3">
              {STEPS.map((step, i) => (
                <li key={step} className="flex gap-4 bg-card p-5 md:block">
                  <span className="font-display text-4xl leading-none font-extrabold tabular md:text-5xl">{String(i + 1).padStart(2, "0")}</span>
                  <div>
                    <p className="font-display text-xl font-bold md:mt-4">{t.flow.steps[step]}</p>
                    <p className="mt-1.5 text-pretty text-muted-foreground">{t.flow.notes[step]}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </section>

      <section className="bg-live text-live-foreground" aria-labelledby="newsrooms-title">
        <div className="mx-auto grid max-w-[88rem] gap-10 px-4 py-14 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)] lg:px-10 lg:py-20">
          <div>
            <h2 id="newsrooms-title" className="font-display text-[clamp(2rem,1.4rem+2.4vw,3.4rem)] leading-[1] font-extrabold tracking-[-0.02em]">
              {h.newsroomsTitle}
            </h2>
            <p className="mt-5 max-w-[56ch] text-lg leading-relaxed text-pretty text-live-muted">{h.newsroomsText}</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button asChild variant="action" size="xl">
                <Link href="/inscription">
                  {h.newsroomsCta} <IconArrowRight aria-hidden />
                </Link>
              </Button>
              <Link href="/connexion" className="inline-flex h-12 items-center rounded-md border border-live-border px-5 font-bold hover:bg-white/5">
                {s.nav.signIn}
              </Link>
            </div>
          </div>
          <ul className="space-y-px self-center">
            {h.newsroomsPoints.map((point) => (
              <li key={point} className="flex items-start gap-4 border-t border-live-border py-5 text-lg">
                <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full border border-live-border text-live-foreground">
                  <IconCheck className="size-4" aria-hidden />
                </span>
                {point}
              </li>
            ))}
          </ul>
        </div>
      </section>
    </>
  );
}
