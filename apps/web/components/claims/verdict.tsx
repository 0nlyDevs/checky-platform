import type { Item, Status, Verdict } from "@checky/shared";
import { IconBroadcast, IconCheckCircle, IconCircleDashed, IconQuestion, IconShieldCheck, IconTimer, IconWarning, IconXCircle, type Icon } from "@/lib/icons";
import { t } from "@/lib/i18n/live";
import { cn } from "@/lib/utils";

export const VERDICT_META: Record<
  Verdict,
  { label: string; icon: Icon; fill: string; on: string; soft: string; ink: string }
> = {
  true: {
    get label() { return t.verdict.true; },
    icon: IconCheckCircle,
    fill: "bg-verdict-true",
    on: "text-verdict-true-on",
    soft: "bg-verdict-true-soft",
    ink: "text-verdict-true-ink",
  },
  misleading: {
    get label() { return t.verdict.misleading; },
    icon: IconWarning,
    fill: "bg-verdict-misleading",
    on: "text-verdict-misleading-on",
    soft: "bg-verdict-misleading-soft",
    ink: "text-verdict-misleading-ink",
  },
  false: {
    get label() { return t.verdict.false; },
    icon: IconXCircle,
    fill: "bg-verdict-false",
    on: "text-verdict-false-on",
    soft: "bg-verdict-false-soft",
    ink: "text-verdict-false-ink",
  },
  unverifiable: {
    get label() { return t.verdict.unverifiable; },
    icon: IconQuestion,
    fill: "bg-verdict-unverifiable",
    on: "text-verdict-unverifiable-on",
    soft: "bg-verdict-unverifiable-soft",
    ink: "text-verdict-unverifiable-ink",
  },
};

export type ClaimView = {
  item: Item;
  ref: string;
  firstSeen: Date | null;
  origin: string | null;
  verdict: Verdict | null;
  suggested: Verdict | null;
  sources: number;
  status: Status;
  assigneeId: string | null;
};

function isVerdict(v: unknown): v is Verdict {
  return typeof v === "string" && v in VERDICT_META;
}

/** Item fields that live in `data` (the flexible part) read back with types. */
export function toClaim(item: Item): ClaimView {
  const d = item.data as Record<string, unknown>;
  const seen = typeof d.first_seen_at === "string" ? new Date(d.first_seen_at) : null;
  return {
    item,
    ref: typeof d.ref === "string" ? d.ref : `FAN-${item.id.slice(0, 4).toUpperCase()}`,
    firstSeen: seen && !Number.isNaN(seen.getTime()) ? seen : null,
    origin: typeof d.origin === "string" ? d.origin : null,
    verdict: isVerdict(d.verdict) ? d.verdict : null,
    suggested: isVerdict(d.verdict_suggested) ? d.verdict_suggested : null,
    sources: typeof d.source_count === "number" ? d.source_count : 0,
    status: item.status as Status,
    assigneeId: typeof d.assignee_id === "string" ? d.assignee_id : null,
  };
}

/** A confirmed verdict as a small badge: icon plus word, on its soft ground. */
export function VerdictChip({ verdict, className }: { verdict: Verdict; className?: string }) {
  const m = VERDICT_META[verdict];
  const Icon = m.icon;
  return (
    <span className={cn("inline-flex flex-none items-center gap-1.5 rounded-sm px-2 py-0.5 text-sm font-bold whitespace-nowrap", m.soft, m.ink, className)}>
      <Icon className="size-3.5" aria-hidden />
      {m.label}
    </span>
  );
}

/** The confirmed verdict, or the AI suggestion marked as such. Never colour alone. */
/** `compact` drops the visible "suggéré" (the dashed outline already says it) but keeps it for screen readers. */
export function VerdictBadge({ claim, className, compact = false }: { claim: ClaimView; className?: string; compact?: boolean }) {
  const v = claim.verdict ?? claim.suggested;
  if (!v) {
    return <span className={cn("text-sm text-muted-foreground", className)}>{t.verdict.none}</span>;
  }
  const m = VERDICT_META[v];
  const Icon = m.icon;
  const suggested = !claim.verdict;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm px-2 py-0.5 text-sm font-medium whitespace-nowrap",
        suggested ? "border border-dashed border-current bg-transparent" : m.soft,
        m.ink,
        className,
      )}
    >
      <Icon className="size-3.5 shrink-0" aria-hidden />
      {m.label}
      {suggested && (
        <span className={cn("font-normal", compact && "sr-only")}>· {t.verdict.suggested}</span>
      )}
    </span>
  );
}

export function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

export function Avatar({ name, className }: { name: string; className?: string }) {
  return (
    <span
      title={name}
      className={cn(
        "grid size-6 shrink-0 place-items-center rounded-full bg-secondary font-display text-xs font-semibold text-secondary-foreground ring-1 ring-border",
        className,
      )}
    >
      {initials(name)}
    </span>
  );
}

// Status is workflow, not truth: ink icons only, so it never reads as a verdict colour.
export const STATUS_ICON: Record<Status, Icon> = {
  to_check: IconCircleDashed,
  in_progress: IconTimer,
  verified: IconShieldCheck,
  published: IconBroadcast,
};

export function StatusLabel({ status }: { status: Status }) {
  const Icon = STATUS_ICON[status] ?? IconCircleDashed;
  return (
    <span className="inline-flex items-center gap-2 text-sm whitespace-nowrap">
      <Icon
        className={cn("size-4 shrink-0", status === "to_check" ? "text-muted-foreground" : "text-foreground")}
        aria-hidden
      />
      {t.status[status] ?? status}
    </span>
  );
}
