"use client";

import Link from "next/link";
import { IconCaretRight } from "@/lib/icons";
import { claimSteps, StepLine } from "@/components/flow/step-line";
import { Avatar, type ClaimView, StatusLabel, VerdictBadge } from "@/components/claims/verdict";
import { t } from "@/lib/i18n/fr";
import { formatDuration, formatTime } from "@/lib/time";

const dateFmt = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short" });

function seen(c: ClaimView, now: Date) {
  if (!c.firstSeen) return { at: t.claims.noFirstSeen, ago: null };
  const at = c.firstSeen.toDateString() === now.toDateString() ? formatTime(c.firstSeen) : `${dateFmt.format(c.firstSeen)}, ${formatTime(c.firstSeen)}`;
  return { at, ago: t.claims.ago(formatDuration(now.getTime() - c.firstSeen.getTime())) };
}

/** One dossier per line: when it was first seen, what it says, where it stands on the line, the verdict. */
export function DossierList({ ws, claims, now, names }: { ws: string; claims: ClaimView[]; now: Date; names: Map<string, string> }) {
  return (
    <ul className="border-t border-foreground">
      {claims.map((c, i) => {
        const when = seen(c, now);
        const who = c.assigneeId ? names.get(c.assigneeId) : null;
        const origin = c.origin ? (t.origins[c.origin as keyof typeof t.origins] ?? c.origin) : null;
        return (
          <li key={c.item.id} className="arrive relative border-b border-border" style={{ "--i": Math.min(i, 12) } as React.CSSProperties}>
            <div className="grid gap-x-6 gap-y-3 px-4 py-4 transition-colors hover:bg-card md:grid-cols-[6.5rem_minmax(0,1fr)_auto] md:items-center lg:px-3 @4xl:grid-cols-[6.5rem_minmax(0,1fr)_13rem_11rem_1.5rem]">
              <p className="flex items-baseline gap-3 md:block">
                <span className="block font-display font-bold tabular">{c.ref}</span>
                <time dateTime={c.firstSeen?.toISOString()} className="block text-sm text-muted-foreground tabular" title={when.at}>
                  {when.ago ?? when.at}
                </time>
              </p>
              <div className="min-w-0">
                <Link
                  href={`/w/${ws}/affirmations/${c.item.id}`}
                  className="block font-bold text-pretty outline-none after:absolute after:inset-0 hover:underline focus-visible:after:ring-2 focus-visible:after:ring-ring focus-visible:after:ring-inset md:text-[1.05rem]"
                >
                  {c.item.title}
                </Link>
                <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
                  <StatusLabel status={c.status} />
                  {origin && <span>{origin}</span>}
                  <span className="tabular">{t.claims.sources(c.sources)}</span>
                </p>
              </div>
              <StepLine variant="mini" states={claimSteps(c)} className="hidden @4xl:flex" />
              <div className="flex items-center gap-3 md:justify-end @4xl:justify-start">
                <VerdictBadge claim={c} />
                {who && <Avatar name={who} className="@4xl:hidden" />}
              </div>
              <span className="hidden items-center justify-end @4xl:flex">
                {who ? <Avatar name={who} /> : <IconCaretRight className="size-4 text-muted-foreground" aria-hidden />}
              </span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
