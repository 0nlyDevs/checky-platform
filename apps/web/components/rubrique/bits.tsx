import Link from "next/link";
import { IconChatCircle, IconFolderOpen, IconNewspaper, IconPaperPlaneTilt, IconRadio, type Icon } from "@/lib/icons";
import { VerdictChip } from "@/components/claims/verdict";
import { t } from "@/lib/i18n/fr";
import { formatTime } from "@/lib/time";
import { cn } from "@/lib/utils";
import type { Checked, Kind } from "./types";

const r = t.rubrique;
const dayFmt = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short" });

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

/** A section of the page: a heading on a ruled line, newspaper style, meta under it. */
export function Section({
  title,
  lead,
  action,
  children,
  className,
  id,
}: {
  title: string;
  lead?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section aria-labelledby={id} className={cn("border-t-2 border-foreground pt-3", className)}>
      <div className="flex items-start justify-between gap-3">
        <h2 id={id} className="font-display text-xl leading-tight font-bold">
          {title}
        </h2>
        {action}
      </div>
      {lead && <p className="mt-1 text-sm text-pretty text-muted-foreground">{lead}</p>}
      <div className="mt-3">{children}</div>
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
