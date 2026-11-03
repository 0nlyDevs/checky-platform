"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { IconArrowRight } from "@/lib/icons";
import { type Step, type StepState, StepLine } from "@/components/flow/step-line";
import { Em, Lines } from "@/components/site/public/kit";
import { VerdictBlock } from "@/components/site/public/public-verdict";
import { useMoment, useT } from "@/lib/i18n";
import { type TipStatus, publicApi } from "@/lib/public-api";

/** Where a tip stands at the desk, on the same numbered line as everything else. */
function states(status: TipStatus["status"]): Record<Step, StepState> {
  if (status === "to_check") return { claim: "done", evidence: "waiting", conclusion: "waiting" };
  if (status === "in_progress") return { claim: "done", evidence: "active", conclusion: "waiting" };
  if (status === "verified") return { claim: "done", evidence: "done", conclusion: "active" };
  return { claim: "done", evidence: "done", conclusion: "done" };
}

/** The follow-up of a public tip: where it stands at the desk, and its verdict once published. */
export function FollowView() {
  const { token } = useParams<{ token: string }>();
  const t = useT();
  const f = t.site.pub.follow;
  const moment = useMoment();
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

  return (
    <div className="mx-auto max-w-[88rem] px-4 pt-10 pb-24 lg:px-10 lg:pt-16">
      <Lines className="pub-display" lines={t.look.follow.hero.map((line, i) => <Em key={i} text={line} />)} />
      {tip === "missing" && <p className="mt-10 text-xl">{f.notFound}</p>}
      {!tip && <div className="mt-10 h-44 max-w-xl rounded-[24px] bg-muted" />}
      {tip && tip !== "missing" && (
        <div className="rise mt-10 grid gap-12 lg:grid-cols-[minmax(0,28rem)_minmax(0,1fr)]" style={{ "--d": "0.25s" } as React.CSSProperties}>
          <div>
            <div className="rounded-[24px] border border-border bg-card p-6">
              <p className="flex justify-between gap-4 text-sm text-muted-foreground">
                <span>{tip.newsroom.name}</span>
                <span className="font-display font-bold text-foreground tabular">{tip.ref}</span>
              </p>
              <p className="mt-2 font-display text-xl leading-snug font-bold text-pretty">« {tip.title} »</p>
              <p className="mt-2 text-sm text-muted-foreground">
                {f.received(moment(tip.received_at))}
              </p>
            </div>
            <StepLine
              className="mt-8"
              states={states(tip.status)}
              notes={{
                claim: f.steps.to_check,
                evidence: f.steps.in_progress,
                conclusion: tip.status === "published" ? f.steps.published : f.steps.verified,
              }}
            />
          </div>
          <div aria-live="polite">
            {tip.verdict ? (
              <>
                <VerdictBlock v={tip.verdict} />
                <Link
                  href={`/verifies/${tip.verdict.id}`}
                  className="group mt-5 inline-flex h-12 items-center gap-2 rounded-full bg-primary px-6 font-bold text-primary-foreground outline-none hover:bg-primary-hover hover:text-primary-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                >
                  {t.site.pub.file.open} <IconArrowRight className="size-4 transition-transform duration-300 group-hover:translate-x-1" aria-hidden />
                </Link>
              </>
            ) : (
              <p className="max-w-[48ch] text-xl leading-relaxed text-pretty lg:pt-2">{f.waiting}</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
