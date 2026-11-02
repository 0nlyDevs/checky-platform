"use client";

import { dayRange, formatDuration, formatTime } from "@/components/claims/day-grid";
import { type ClaimView, VERDICT_META } from "@/components/claims/verdict";
import { t } from "@/lib/i18n/fr";
import { cn } from "@/lib/utils";

const HOUR = 3_600_000;

/** One claim's lane from the day grid: its airtime, drawn to the same scale. */
export function AirtimeStrip({ claim, now }: { claim: ClaimView; now: Date }) {
  if (!claim.firstSeen) return null;
  const { start, end } = dayRange(now);
  const span = end - start;
  const pct = (ms: number) => ((Math.min(Math.max(ms, start), end) - start) / span) * 100;
  const seen = claim.firstSeen.getTime();
  const left = pct(seen);
  const nowPct = pct(now.getTime());
  const v = claim.verdict ?? claim.suggested;
  const meta = v ? VERDICT_META[v] : null;
  const ticks: number[] = [];
  for (let h = start; h <= end; h += 3 * HOUR) ticks.push(h);

  return (
    <div className="mt-6" aria-hidden>
      <div className="flex items-baseline justify-between gap-4 text-sm text-muted-foreground">
        <span>
          {t.detail.circulating}{" "}
          <span className="font-display text-lg font-semibold tracking-wide text-foreground tabular">
            {formatDuration(now.getTime() - seen)}
          </span>
        </span>
        <span className="font-display font-medium tracking-wide uppercase tabular">
          {t.claims.now} {formatTime(now)}
        </span>
      </div>
      <div className="relative mt-2 h-9 rounded-md border border-border bg-card">
        <div className="absolute inset-y-0 right-0 rounded-r-md bg-muted/60" style={{ left: `${nowPct}%` }} />
        {ticks.map((h) => (
          <div key={h} className="absolute inset-y-0 w-px bg-rule" style={{ left: `${pct(h)}%` }}>
            <span className="absolute -bottom-5 -translate-x-1/2 font-display text-xs text-muted-foreground tabular">
              {String(new Date(h).getHours()).padStart(2, "0")}h
            </span>
          </div>
        ))}
        <div
          className={cn(
            "absolute inset-y-1.5 origin-left animate-[grid-extend_640ms_var(--ease-out-expo)_backwards] rounded-[3px]",
            !v && "border border-foreground/60 bg-card",
            v && !claim.verdict && cn("border border-dashed border-current", meta!.soft, meta!.ink),
            claim.verdict && meta!.fill,
            seen < start && "rounded-l-none",
          )}
          style={{ left: `${left}%`, width: `${Math.max(nowPct - left, 0.6)}%` }}
        />
        <div className="absolute -inset-y-1 w-0.5 bg-signal" style={{ left: `${nowPct}%` }} />
      </div>
    </div>
  );
}
