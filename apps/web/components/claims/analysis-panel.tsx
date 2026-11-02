"use client";

import type { Item } from "@fanilo/shared";
import Link from "next/link";
import { useState } from "react";
import { IconCalendarDots, IconCircleNotch, IconInfo, IconMinus, IconPlus, IconSparkle, type Icon } from "@/lib/icons";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useWorkspaceSocket } from "@/hooks/use-workspace-socket";
import { api } from "@/lib/api";
import { t } from "@/lib/i18n/fr";
import { cn } from "@/lib/utils";

type Evidence = {
  source_id: string;
  source_title: string;
  n: number;
  stance: string;
  quote: string;
  explanation: string;
  // Older analyses have no `attached`: they only read attached sources.
  attached?: boolean;
  item_id?: string | null;
  // Worked out by the API: the source's date and how many days before the rumour it is.
  source_date?: string | null;
  date_basis?: "published" | "added" | null;
  days_before?: number | null;
};
type Analysis = {
  claims: { text: string; who: string; what: string; when: string; figure: string }[];
  evidence: Evidence[];
  reason: string;
  missing: string;
  dropped_quotes: number;
  sources_used: number;
  related_used?: number;
  date_check?: "downgraded" | "old_evidence" | null;
  provider: string;
  model: string;
  at: string;
};

// Stance is not a verdict: ink icons only, never verdict colours.
const STANCE_ICON: Record<string, Icon> = { supports: IconPlus, contradicts: IconMinus, context: IconInfo };

const whenFmt = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
// Source dates are calendar days (YYYY-MM-DD): read and shown in UTC so no time zone shifts them.
const dayFmt = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
const STALE_DAYS = 30; // the API's dates.STALE_DAYS

function dateLabel(e: Evidence) {
  const d = t.analysis.dates;
  if (!e.source_date || e.days_before == null) return d.unknown;
  const day = dayFmt.format(new Date(`${e.source_date}T00:00:00Z`));
  return (e.date_basis === "added" ? d.added : d.published)(day, d.gap(e.days_before));
}

/** F1 claim checker: run the AI over the claim's sources and show what it found, with verbatim quotes. */
export function AnalysisPanel({ ws, item, sourceCount }: { ws: string; item: Item; sourceCount: number }) {
  const [jobId, setJobId] = useState<string | null>(null);
  const analysis = (item.data as { analysis?: Analysis }).analysis;

  useWorkspaceSocket(ws, {
    "job.done": (j: { id: string }) => j.id === jobId && setJobId(null),
    "job.failed": (j: { id: string }) => {
      if (j.id !== jobId) return;
      setJobId(null);
      toast.error(t.analysis.failed);
    },
  });

  async function run() {
    try {
      const job = await api<{ id: string }>(`/workspaces/${ws}/items/${item.id}/analyze`, { method: "POST" });
      setJobId(job.id);
    } catch {
      toast.error(t.analysis.failed);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="outline" className="h-10" onClick={run} disabled={Boolean(jobId)}>
          {jobId ? <IconCircleNotch className="animate-spin" aria-hidden /> : <IconSparkle aria-hidden />}
          {analysis ? t.analysis.rerun : t.analysis.run}
        </Button>
        {jobId && (
          <span className="text-sm text-muted-foreground" role="status">
            {t.analysis.running}
          </span>
        )}
      </div>
      {sourceCount === 0 && !analysis && <p className="text-sm text-muted-foreground">{t.analysis.noSources}</p>}

      {analysis && (
        <div className="space-y-5">
          {analysis.claims.length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-muted-foreground">{t.analysis.facts}</h3>
              <ul className="mt-1.5 list-disc space-y-1 pl-5">
                {analysis.claims.map((c, i) => (
                  <li key={i} className="text-pretty">
                    {c.text}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div>
            <h3 className="text-sm font-medium text-muted-foreground">{t.analysis.evidence}</h3>
            {analysis.date_check && (
              <p role="note" className="mt-2 flex gap-2 rounded-md border border-border bg-muted p-3 text-sm text-pretty">
                <IconCalendarDots className="mt-0.5 size-4 shrink-0" aria-hidden />
                {analysis.date_check === "downgraded" ? t.analysis.downgraded : t.analysis.oldEvidence}
              </p>
            )}
            {analysis.evidence.length === 0 ? (
              <p className="mt-1.5 text-muted-foreground">{t.analysis.noEvidence}</p>
            ) : (
              <ul className="mt-2 space-y-3">
                {analysis.evidence.map((e, i) => {
                  const Icon = STANCE_ICON[e.stance] ?? IconInfo;
                  return (
                    <li key={i} className="rounded-md border border-border bg-card p-3.5">
                      <p className="flex items-center gap-1.5 text-sm font-medium">
                        <Icon className="size-4" aria-hidden />
                        {t.analysis.stance[e.stance] ?? e.stance}
                        <span className="font-normal text-muted-foreground">
                          · [{e.n}] {e.source_title}
                        </span>
                      </p>
                      {e.attached === false && (
                        <p className="mt-1 text-sm text-muted-foreground">
                          {t.analysis.otherFile}
                          {e.item_id && e.item_id !== item.id && (
                            <>
                              {" · "}
                              <Link href={`/w/${ws}/affirmations/${e.item_id}`} className="underline underline-offset-2 hover:text-foreground">
                                {t.analysis.openFile}
                              </Link>
                            </>
                          )}
                        </p>
                      )}
                      {e.date_basis !== undefined && (
                        <p
                          className={cn(
                            "mt-1 flex items-center gap-1.5 text-sm",
                            (e.days_before ?? 0) > STALE_DAYS ? "font-medium text-foreground" : "text-muted-foreground",
                          )}
                        >
                          <IconCalendarDots className="size-4 shrink-0" aria-hidden />
                          {dateLabel(e)}
                        </p>
                      )}
                      <blockquote className="mt-2 border-l-2 border-border pl-3 text-pretty italic">« {e.quote} »</blockquote>
                      {e.explanation && <p className="mt-2 text-sm text-pretty text-muted-foreground">{e.explanation}</p>}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {analysis.reason && (
            <div>
              <h3 className="text-sm font-medium text-muted-foreground">{t.analysis.reason}</h3>
              <p className="mt-1 max-w-[70ch] text-pretty">{analysis.reason}</p>
            </div>
          )}
          {analysis.missing && (
            <div>
              <h3 className="text-sm font-medium text-muted-foreground">{t.analysis.missing}</h3>
              <p className="mt-1 max-w-[70ch] text-pretty">{analysis.missing}</p>
            </div>
          )}
          <div className="space-y-0.5 text-sm text-muted-foreground">
            {analysis.dropped_quotes > 0 && <p>{t.analysis.dropped(analysis.dropped_quotes)}</p>}
            <p className="tabular" title={analysis.model}>
              {t.analysis.meta(analysis.sources_used, analysis.related_used ?? 0, whenFmt.format(new Date(analysis.at)))}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
