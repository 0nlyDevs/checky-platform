import Link from "next/link";
import { IconChatCircle, IconFolderOpen, IconNewspaper, IconPaperPlaneTilt, IconRadio, type Icon } from "@/lib/icons";
import { VerdictChip } from "@/components/claims/verdict";
import { dateFormat, t } from "@/lib/i18n/live";
import { formatTime } from "@/lib/time";
import { cn } from "@/lib/utils";
import type { Checked, Kind } from "./types";

const r = t.rubrique;
const dayFmt = dateFormat({ day: "numeric", month: "short" });

export const KIND_ICON: Record<Kind, Icon> = {
  item: IconFolderOpen,
  tip: IconPaperPlaneTilt,
  sms: IconChatCircle,
  clip: IconRadio,
  press: IconNewspaper,
};

/** "07:30" today, "1 nov., 07:30" before. */
export function when(at: string | Date, now = new Date()) {
  const d = typeof at === "string" ? new Date(at) : at;
  return d.toDateString() === now.toDateString() ? formatTime(d) : `${dayFmt.format(d)}, ${formatTime(d)}`;
}

/** How loud a section speaks. `lead`: the one a page exists for, a large heading and no rule (the
 *  page header's rule is right above it). `main`: a heading on an ink rule, newspaper style.
 *  `aside`: a smaller heading on a hairline, for the context column. */
export type SectionTone = "lead" | "main" | "aside";

const TONE: Record<SectionTone, { box: string; heading: string; lead: string; body: string }> = {
  lead: { box: "", heading: "text-2xl leading-none font-extrabold tracking-tight sm:text-3xl", lead: "mt-2", body: "mt-5" },
  main: { box: "border-t border-foreground pt-3", heading: "text-xl leading-tight font-bold", lead: "mt-1", body: "mt-3" },
  aside: { box: "border-t border-border pt-3", heading: "text-lg leading-tight font-bold", lead: "mt-0.5", body: "mt-3" },
};

/** A section of the page: a heading on a ruled line, newspaper style, meta under it. */
export function Section({
  title,
  lead,
  action,
  children,
  className,
  id,
  tone = "main",
}: {
  title: string;
  lead?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  id?: string;
  tone?: SectionTone;
}) {
  const s = TONE[tone];
  return (
    <section aria-labelledby={id} className={cn(s.box, className)}>
      <div className="flex items-start justify-between gap-3">
        <h2 id={id} className={cn("font-display text-balance", s.heading)}>
          {title}
        </h2>
        {action}
      </div>
      {lead && <p className={cn("text-sm text-pretty text-muted-foreground", s.lead)}>{lead}</p>}
      <div className={s.body}>{children}</div>
    </section>
  );
}

export function DemoTag({ className }: { className?: string }) {
  return <span className={cn("inline-block rounded-sm border border-border px-1.5 py-px text-xs whitespace-nowrap text-muted-foreground", className)}>{r.demo}</span>;
}

export function KindLabel({ kind, className }: { kind: Kind; className?: string }) {
  const Icon = KIND_ICON[kind];
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-sm font-bold whitespace-nowrap", className)}>
      <Icon className="size-4" aria-hidden />
      {r.kinds[kind]}
    </span>
  );
}

/** « Déjà vérifié »: the verdict a journalist signed (ours, or a public newsroom's), linked when ours. */
export function CheckedLine({ checked, ws }: { checked: Checked; ws: string }) {
  const body = (
    <>
      <span className="font-bold">{t.rubrique.circulating.already}</span>
      <VerdictChip verdict={checked.verdict} />
      <span className="text-muted-foreground">{checked.mine ? r.ours : r.verdictOf(checked.newsroom)}</span>
    </>
  );
  return checked.mine ? (
    <Link href={`/w/${ws}/affirmations/${checked.id}` as never} className="relative z-10 inline-flex flex-wrap items-center gap-2 text-sm hover:underline">
      {body}
    </Link>
  ) : (
    <span className="inline-flex flex-wrap items-center gap-2 text-sm">{body}</span>
  );
}

export function LoadFailed({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="mx-4 rounded-md border border-border bg-card p-6 lg:mx-0">
      <p className="font-bold">{r.loadFailed}</p>
      <button type="button" onClick={onRetry} className="mt-2 font-bold underline underline-offset-4">
        {r.retry}
      </button>
    </div>
  );
}
