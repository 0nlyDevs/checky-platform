"use client";

import { VerifiedBadge } from "@/components/verification/status";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { StepLine } from "@/components/flow/step-line";
import { Evidence, ShareActions, type SignedVerdict, Trajet, VerdictBlock } from "@/components/site/public/public-verdict";
import { useDay, useT } from "@/lib/i18n";
import { IconArrowLeft, IconArrowRight } from "@/lib/icons";
import { publicApi } from "@/lib/public-api";
import { tidy } from "@/lib/typo";

/** One published verdict, at its own shareable address: the answer first, why, the evidence with
 *  its dates, where the correction went, then share. */
export function VerdictPage() {
  const { id } = useParams<{ id: string }>();
  const t = useT();
  const p = t.site.pub.file;
  const day = useDay();
  const [v, setV] = useState<SignedVerdict | null | "missing">(null);

  useEffect(() => {
    publicApi<SignedVerdict>(`/verdicts/${id}`).then(setV).catch(() => setV("missing"));
  }, [id]);

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

  const origin = v.origin ? ((t.origins as Record<string, string>)[v.origin] ?? null) : null;
  return (
    <Shell>
      <h1 className="mt-6 max-w-[30ch] font-display text-[1.7rem] leading-[1.1] font-extrabold tracking-tight text-pretty md:mt-8 md:text-[2.6rem]">«&nbsp;{tidy(v.title)}&nbsp;»</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        {t.publicLayer.check.signed.by(v.newsroom.name, day(v.signed_at ?? v.published_at))}
        {v.ref && <span className="tabular"> · {v.ref}</span>}
      </p>
      <VerifiedBadge className="mt-1" />

      <div className="mt-6 grid gap-10 md:mt-8 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="min-w-0">
          <VerdictBlock v={v} />
          <div className="mt-4">
            <ShareActions v={v} primary />
          </div>

          {(v.confidence || !!v.evidence?.length) && (
            <section className="mt-10">
              <Evidence v={v} />
            </section>
          )}

          {v.post && (
            <section className="mt-10">
              <h2 className="font-display text-lg font-bold">{p.post}</h2>
              <p className="mt-2 max-w-[70ch] text-lg leading-relaxed text-pretty">{v.post}</p>
            </section>
          )}

          {/* Older verdicts have only source titles: listed as before. */}
          {!v.evidence?.length && (
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
          )}

          <Trajet id={v.id} className="mt-10" />
        </div>

        <aside className="lg:border-l lg:border-border lg:pl-8">
          <h2 className="sr-only">{t.flow.label}</h2>
          <StepLine
            states={{ claim: "done", evidence: "done", conclusion: "done" }}
            notes={{
              claim: v.first_seen_at ? p.seenOn(day(v.first_seen_at), origin) : undefined,
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
              {p.wrongAction} <IconArrowRight className="size-4" aria-hidden />
            </Link>
          </div>
        </aside>
      </div>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const p = useT().site.pub.file;
  return (
    <div className="mx-auto max-w-[88rem] px-4 pt-8 pb-20 lg:px-10">
      <Link href="/verifies" className="inline-flex items-center gap-1.5 text-sm font-bold hover:underline">
        <IconArrowLeft className="size-4" aria-hidden /> {p.back}
      </Link>
      {children}
    </div>
  );
}
