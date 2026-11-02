"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { VerdictFile } from "@/components/site/public/verdict-file";
import { t } from "@/lib/i18n/fr";
import { type TipStatus, publicApi } from "@/lib/public-api";

const f = t.site.pub.follow;
const STEPS = ["to_check", "in_progress", "verified", "published"] as const;

/** The follow-up of a public tip: where it stands at the desk, and its verdict once published. */
export function FollowView() {
  const { token } = useParams<{ token: string }>();
  const [tip, setTip] = useState<TipStatus | null | "missing">(null);

  useEffect(() => {
    let dead = false;
    const load = () =>
      publicApi<TipStatus>(`/tips/${token}`)
        .then((v) => !dead && setTip(v))
        .catch(() => !dead && setTip("missing"));
    load();
    const id = setInterval(load, 30_000);
    return () => {
      dead = true;
      clearInterval(id);
    };
  }, [token]);

  const at = tip && tip !== "missing" ? STEPS.indexOf(tip.status) : -1;

  return (
    <section className="frame-x pt-[clamp(32px,6vw,72px)] pb-[clamp(72px,9vw,130px)]" aria-labelledby="follow-title">
      <h1 id="follow-title" className="disp text-[clamp(48px,7vw,112px)] leading-[0.9]">
        {f.title}
      </h1>
      {tip === "missing" && <p className="mt-8 text-xl">{f.notFound}</p>}
      {tip && tip !== "missing" && (
        <div className="mt-10 grid gap-12 lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
          <div className="dossier-fiche" style={{ transform: "none" }}>
            <div className="t">
              <span>{tip.newsroom.name}</span>
              <span className="tabular">{tip.ref}</span>
            </div>
            <p className="text-lg leading-snug font-medium">«&nbsp;{tip.title}&nbsp;»</p>
            <p className="typed mt-2 text-[14px] text-ink-soft">
              {f.received(new Date(tip.received_at).toLocaleString("fr-FR", { dateStyle: "long", timeStyle: "short" }))}
            </p>
            <ol className="pub-steps mt-6">
              {STEPS.map((s, i) => (
                <li key={s} data-done={i <= at} aria-current={i === at ? "step" : undefined}>
                  {f.steps[s]}
                </li>
              ))}
            </ol>
          </div>
          <div aria-live="polite">{tip.verdict ? <VerdictFile v={tip.verdict} full /> : <p className="max-w-[44ch] text-xl leading-relaxed">{f.waiting}</p>}</div>
        </div>
      )}
    </section>
  );
}
