"use client";

import { CheckForm } from "@/components/site/public/check";
import { VerdictList } from "@/components/site/public/verdicts";
import { useT } from "@/lib/i18n";

/** « Les verdicts »: the layered check first, then every published verdict, filterable. */
export function VerifiesView() {
  const t = useT();
  const c = t.publicLayer.check;
  const p = t.site.pub;
  return (
    <div className="mx-auto max-w-[88rem] px-4 pt-10 pb-20 lg:px-10 lg:pt-14">
      <div className="grid gap-x-16 gap-y-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,38rem)]">
        <div>
          <h1 id="check-title" className="page-title">
            {c.title}
          </h1>
          <p className="mt-4 max-w-[52ch] text-lg leading-relaxed text-pretty text-muted-foreground">{c.lead}</p>
        </div>
        <CheckForm />
      </div>
      <section className="mt-16" aria-labelledby="archive-title">
        <h2 id="archive-title" className="font-display text-2xl font-extrabold tracking-tight">
          {p.archive.title}
        </h2>
        <div className="mt-4">
          <VerdictList limit={12} filter />
        </div>
      </section>
    </div>
  );
}
