"use client";

import { IconCircleNotch, IconInfo, IconMinus, IconPlus, IconSparkle, type Icon } from "@/lib/icons";
import { VERDICT_META } from "@/components/claims/verdict";
import { Button } from "@/components/ui/button";
import { t } from "@/lib/i18n/live";
import { cn } from "@/lib/utils";
import { fmtDay, type Reading } from "./types";

const r = t.dossier.reading;

// A stance is not a verdict: ink icons only.
const STANCE_ICON: Record<string, Icon> = { supports: IconPlus, contradicts: IconMinus, context: IconInfo };

/**
 * « Lecture de Checky »: what a model read in the sources, dashed from edge to edge because it is a
 * suggestion. The confidence comes from code; the public never sees this block or its percentage.
 */
export function ReadingPanel({
  reading,
  running,
  canRun,
  aiEnabled,
  onRun,
}: {
  reading: Reading | null;
  running: boolean;
  canRun: boolean;
  aiEnabled: boolean;
  onRun: () => void;
}) {
  const m = reading?.verdict ? VERDICT_META[reading.verdict] : null;
  const VIcon = m?.icon;
  const c = reading?.confidence;
  const missing = [...new Set([...(reading?.missing ?? []), ...(c?.missing ?? [])])];

  return (
    <section aria-labelledby="reading" className="rounded-md border-2 border-dashed border-foreground/70 bg-card p-4 md:p-5">
      <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="min-w-0">
          <h3 id="reading" className="flex items-center gap-2 font-display text-lg font-bold">
            <IconSparkle className="size-4" aria-hidden />
            {r.title}
          </h3>
          <p className="mt-0.5 max-w-[60ch] text-sm text-muted-foreground">{r.lead}</p>
        </div>
        <span className="rounded-sm border border-border px-2 py-0.5 text-xs text-muted-foreground">{r.desk}</span>
      </header>

      {!reading && !running && <p className="mt-4 text-muted-foreground">{r.none}</p>}

      {reading && (
        <div className="mt-4 space-y-5">
          <div className="flex flex-wrap items-stretch gap-3">
            {m && VIcon && (
              <div className={cn("rounded-sm border-2 border-dashed border-current px-4 py-3", m.ink)}>
                <p className="text-sm font-bold">{r.suggests}</p>
                <p className="mt-0.5 flex items-center gap-2 font-display text-2xl font-extrabold tracking-tight">
                  <VIcon className="size-6" aria-hidden />
                  {m.label}
                </p>
              </div>
            )}
            {c && (
              <div className="rounded-sm border border-dashed border-border px-4 py-3">
                <p className="text-sm text-muted-foreground">{r.confidence}</p>
                <p className="mt-0.5 font-display text-2xl font-extrabold tabular">
                  {c.score} %{c.level && <span className="font-sans text-base font-bold"> · {r.level[c.level] ?? c.level}</span>}
                </p>
              </div>
            )}
          </div>

          {reading.reason && <p className="max-w-[70ch] text-pretty">{reading.reason}</p>}

          {c && c.reasons.length > 0 && (
            <div>
              <h4 className="text-sm font-bold">{r.reasons}</h4>
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm">
                {c.reasons.map((x, i) => (
                  <li key={i}>{x}</li>
                ))}
              </ul>
            </div>
          )}

          {reading.evidence.length > 0 && (
            <div>
              <h4 className="text-sm font-bold">{r.evidence}</h4>
              <ul className="mt-2 space-y-3">
                {reading.evidence.map((e, i) => {
                  const SIcon = STANCE_ICON[e.stance] ?? IconInfo;
                  return (
                    <li key={i} className="border-l border-border pl-3">
                      <p className="flex flex-wrap items-center gap-x-2 text-sm">
                        <span className="inline-flex items-center gap-1 font-bold">
                          <SIcon className="size-3.5" aria-hidden />
                          {r.stance[e.stance] ?? e.stance}
                        </span>
                        <span className="text-muted-foreground">
                          {e.n !== null ? `[${e.n}] ` : ""}
                          {e.title}
                          {e.date && ` · ${fmtDay(e.date)}`}
                        </span>
                      </p>
                      <blockquote className="mt-1 text-pretty">« {e.quote} »</blockquote>
                      {e.explanation && <p className="mt-0.5 text-sm text-muted-foreground">{e.explanation}</p>}
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          {missing.length > 0 && (
            <div>
              <h4 className="text-sm font-bold">{r.missing}</h4>
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm">
                {missing.map((x) => (
                  <li key={x}>{x}</li>
                ))}
              </ul>
            </div>
          )}

          {c && c.components.length > 0 && (
            <details className="group text-sm">
              <summary className="cursor-pointer font-bold underline decoration-border underline-offset-4 hover:decoration-foreground">{r.how}</summary>
              <p className="mt-2 text-muted-foreground">{r.howLead}</p>
              <dl className="mt-2 grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1">
                {c.components.map((x) => (
                  <div key={x.key} className="contents">
                    <dt>{x.detail ?? x.key}</dt>
                    <dd className="text-right font-display font-bold tabular">
                      {Math.round(x.points)} / {Math.round(x.maximum)}
                    </dd>
                  </div>
                ))}
              </dl>
            </details>
          )}
        </div>
      )}

      {canRun && aiEnabled && (
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <Button variant="outline" onClick={onRun} disabled={running}>
            {running ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconSparkle aria-hidden />}
            {reading ? r.rerun : r.run}
          </Button>
          {running && (
            <span role="status" className="text-sm text-muted-foreground">
              {r.running}
            </span>
          )}
        </div>
      )}
    </section>
  );
}
