"use client";

import type { Item } from "@fanilo/shared";
import { useState } from "react";
import { Info, LoaderCircle, Minus, Plus, Sparkles, type LucideIcon } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useWorkspaceSocket } from "@/hooks/use-workspace-socket";
import { api } from "@/lib/api";
import { t } from "@/lib/i18n/fr";

type Evidence = { source_id: string; source_title: string; n: number; stance: string; quote: string; explanation: string };
type Analysis = {
  claims: { text: string; who: string; what: string; when: string; figure: string }[];
  evidence: Evidence[];
  reason: string;
  missing: string;
  dropped_quotes: number;
  sources_used: number;
  provider: string;
  model: string;
  at: string;
};

// Stance is not a verdict: ink icons only, never verdict colours.
const STANCE_ICON: Record<string, LucideIcon> = { supports: Plus, contradicts: Minus, context: Info };

const whenFmt = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

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
          {jobId ? <LoaderCircle className="animate-spin" aria-hidden /> : <Sparkles aria-hidden />}
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
            {analysis.evidence.length === 0 ? (
              <p className="mt-1.5 text-muted-foreground">{t.analysis.noEvidence}</p>
            ) : (
              <ul className="mt-2 space-y-3">
                {analysis.evidence.map((e, i) => {
                  const Icon = STANCE_ICON[e.stance] ?? Info;
                  return (
                    <li key={i} className="rounded-md border border-border bg-card p-3.5">
                      <p className="flex items-center gap-1.5 text-sm font-medium">
                        <Icon className="size-4" aria-hidden />
                        {t.analysis.stance[e.stance] ?? e.stance}
                        <span className="font-normal text-muted-foreground">
                          · [{e.n}] {e.source_title}
                        </span>
                      </p>
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
            <p className="tabular">{t.analysis.meta(analysis.sources_used, analysis.model, whenFmt.format(new Date(analysis.at)))}</p>
          </div>
        </div>
      )}
    </div>
  );
}
