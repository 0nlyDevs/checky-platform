import type { Item, Status, Verdict } from "@fanilo/shared";
import {
  CircleCheck,
  CircleDashed,
  CircleHelp,
  CircleX,
  Radio,
  ShieldCheck,
  Timer,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import { t } from "@/lib/i18n/fr";
import { cn } from "@/lib/utils";

export const VERDICT_META: Record<
  Verdict,
  { label: string; icon: LucideIcon; fill: string; on: string; soft: string; ink: string }
> = {
  true: {
    label: t.verdict.true,
    icon: CircleCheck,
    fill: "bg-verdict-true",
    on: "text-verdict-true-on",
    soft: "bg-verdict-true-soft",
    ink: "text-verdict-true-ink",
  },
  misleading: {
    label: t.verdict.misleading,
    icon: TriangleAlert,
    fill: "bg-verdict-misleading",
    on: "text-verdict-misleading-on",
    soft: "bg-verdict-misleading-soft",
    ink: "text-verdict-misleading-ink",
  },
  false: {
    label: t.verdict.false,
    icon: CircleX,
    fill: "bg-verdict-false",
    on: "text-verdict-false-on",
    soft: "bg-verdict-false-soft",
    ink: "text-verdict-false-ink",
  },
  unverifiable: {
    label: t.verdict.unverifiable,
    icon: CircleHelp,
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
};

function isVerdict(v: unknown): v is Verdict {
  return typeof v === "string" && v in VERDICT_META;
}

/** Item fields that live in `data` (the day-one flexible part) read back with types. */
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
  };
}

/** The confirmed verdict, or the AI suggestion marked as such. Never colour alone. */
export function VerdictBadge({ claim, className }: { claim: ClaimView; className?: string }) {
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
      {suggested && <span className="font-normal opacity-80">· {t.verdict.suggested}</span>}
    </span>
  );
}

// Status is workflow, not truth: ink icons only, so it never reads as a verdict colour.
const STATUS_ICON: Record<Status, LucideIcon> = {
  to_check: CircleDashed,
  in_progress: Timer,
  verified: ShieldCheck,
  published: Radio,
};

export function StatusLabel({ status }: { status: Status }) {
  const Icon = STATUS_ICON[status] ?? CircleDashed;
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
