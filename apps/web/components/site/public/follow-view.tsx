"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowRight } from "lucide-react";
import { type Step, type StepState, StepLine } from "@/components/flow/step-line";
import { VerdictCard } from "@/components/site/public/verdict-page";
import { t } from "@/lib/i18n/fr";
import { type TipStatus, publicApi } from "@/lib/public-api";

const f = t.site.pub.follow;

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
    <div className="mx-auto max-w-[88rem] px-4 pt-10 pb-20 lg:px-10 lg:pt-14">
      <h1 className="page-title">{f.title}</h1>
      {tip === "missing" && <p className="mt-8 text-xl">{f.notFound}</p>}
      {!tip && <div className="mt-8 h-40 max-w-xl animate-pulse rounded-md bg-muted" />}
      {tip && tip !== "missing" && (
        <div className="mt-8 grid gap-12 lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
          <div>
            <div className="rounded-md border border-border bg-card p-5">
              <p className="flex justify-between gap-4 text-sm text-muted-foreground">
                <span>{tip.newsroom.name}</span>
                <span className="font-display font-bold text-foreground tabular">{tip.ref}</span>
              </p>
              <p className="mt-2 font-display text-xl leading-snug font-bold text-pretty">« {tip.title} »</p>
              <p className="mt-2 text-sm text-muted-foreground">
                {f.received(new Date(tip.received_at).toLocaleString("fr-FR", { dateStyle: "long", timeStyle: "short" }))}
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
                <VerdictCard v={tip.verdict} />
                <Link href={`/verifies/${tip.verdict.id}`} className="mt-4 inline-flex items-center gap-1.5 font-bold underline underline-offset-4">
                  {t.site.pub.file.open} <ArrowRight className="size-4" aria-hidden />
                </Link>
              </>
            ) : (
              <p className="max-w-[48ch] text-xl leading-relaxed text-pretty">{f.waiting}</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
